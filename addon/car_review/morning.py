"""The morning list: shortly after Anki's day starts, ask Anki's own scheduler for the exact queue
for the new day and send it to the phone, so the car never plays a card Anki wouldn't show.

Runs as a silent scheduled task (Windows Task Scheduler) without Anki open. It opens a temporary
COPY of the collection with Anki's engine (the `anki` package, same version as your Anki), so the
real collection is never touched. Anki writes `morning.json` (profile, collection path, decks)
every time it sends a list, so the job always uses your current settings.

Many laptops can't wake themselves for a scheduled task (wake timers off, Modern Standby). So when
Anki closes on the charger in the evening, `helper overnight` also keeps the laptop awake until
just after the task's time and sends the list itself if the task hasn't.

    python -m car_review.helper morning
    python -m car_review.helper schedule      # create or update the daily task
    python -m car_review.helper unschedule
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from .common import HOME

SETTINGS = HOME / "morning.json"
TASK_NAME = "Car Review morning list"
TASK_VERSION = 2  # bump when the task's settings change, so existing installs re-register it


def save_settings(**fields) -> None:
    """Called by the add-on with profile, collection path, decks, days_ahead, auto_voice, rollover."""
    HOME.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(fields))


def _settings() -> dict:
    if not SETTINGS.exists():
        raise RuntimeError("Car Review hasn't sent a list from Anki yet, so the morning job doesn't know your decks.")
    return json.loads(SETTINGS.read_text())


def _open_copy(source: Path, tmp: str, shift_days: int = 0):
    """A copy of the collection (with its write-ahead log) opened with Anki's engine. With
    shift_days, the copy's creation date moves back that many days first, so Anki's "today" on the
    copy is that many days later; due dates themselves don't change."""
    try:
        from anki.collection import Collection  # Anki's own engine, same version as your Anki
    except ImportError as err:
        raise RuntimeError("The morning list needs Anki's engine in Car Review's Python.") from err
    path = Path(tmp) / "collection.anki2"
    for suffix in ("", "-wal"):
        if Path(str(source) + suffix).exists():
            shutil.copy2(str(source) + suffix, str(path) + suffix)
    if shift_days:
        db = sqlite3.connect(path)
        db.execute("update col set crt = crt - ?", (86400 * shift_days,))
        db.commit()
        db.close()
    return Collection(str(path))


def build_morning_pack() -> dict:
    """Today's exact list from a copy of the collection, plus the next days for preloading audio."""
    settings = _settings()
    from .builder import build_pack

    with tempfile.TemporaryDirectory() as tmp:
        col = _open_copy(Path(settings["collection"]), tmp)
        try:
            pack = build_pack(col, settings["decks"], days_ahead=int(settings.get("days_ahead", 3)))
            try:
                check_prediction(pack, col)
            except Exception as err:  # a test must never stop the morning list
                _check_log(f"day {pack['anki_today']}: check failed ({err})")
            return pack
        finally:
            col.close(downgrade=False)


# ---------- Tomorrow's list, made the evening before (being tested) ----------
# The idea: make the morning list when Anki closes in the evening, so the laptop needn't be on at
# 4:30. On a copy of the collection, Anki's "today" moves one day on (unburying, daily limits and
# due cards then work exactly as at the new day), every card's last-review time moves back by the
# time from now to 4:30 tomorrow (FSRS retrievability, and with it the review order and which of
# two due siblings is shown, is then as at 4:30), and intraday learning cards move back by the
# length of tomorrow, so the ones due before the next rollover are the same. Anki's own queue on
# that copy is tomorrow's list as the 4:30 job would make it, unless you review again after.
# For now it's only saved on this computer, and the 4:30 list is compared with it.
PREDICTION = HOME / "predicted.json"
CHECK_LOG = HOME / "prediction-checks.log"
CHECK_FILE = HOME / "prediction-check.json"
TASK_DELAY = 30 * 60  # the morning task runs half an hour after Anki's rollover


def _next_rollover(after: float) -> float:
    """The same local time one calendar day later (23 or 25 hours across a clock change)."""
    return (datetime.fromtimestamp(after) + timedelta(days=1)).timestamp()


def build_next_day_pack(now: float | None = None) -> dict:
    """The list for the Anki day that starts at the next rollover, as the morning job would make
    it then. Never changes the real collection."""
    now = time.time() if now is None else now
    settings = _settings()
    from .builder import build_pack

    with tempfile.TemporaryDirectory() as tmp:
        col = _open_copy(Path(settings["collection"]), tmp, shift_days=1)
        try:
            starts = col.sched.day_cutoff  # the real next rollover: the shifted copy's day begins here
            ends = int(_next_rollover(starts))
            learning_shift = ends - starts
            col.db.execute(f"update cards set due = due - {learning_shift} where queue = 1")
            col.db.execute(
                "update cards set data = json_set(data, '$.lrt', json_extract(data, '$.lrt') - ?) "
                "where json_extract(data, '$.lrt') is not null", int(starts + TASK_DELAY - now))
            pack = build_pack(col, settings["decks"], days_ahead=int(settings.get("days_ahead", 3)), now=now)
        finally:
            col.close(downgrade=False)
    for card in pack["cards"]:
        if card.get("due_at"):
            card["due_at"] += learning_shift
    pack["next_day_at"] = ends
    pack["predicted"] = {"made_at": int(now), "day_starts": starts}
    return pack


def save_prediction(now: float | None = None) -> dict:
    pack = build_next_day_pack(now)
    PREDICTION.write_text(json.dumps(pack), encoding="utf-8")
    return pack


def _check_log(line: str) -> None:
    with open(CHECK_LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M')} {line}\n")


def check_prediction(pack: dict, col) -> str | None:
    """Compare the morning list with last evening's prediction for the same Anki day, card by
    card, and log the result (card ids only)."""
    if not PREDICTION.exists():
        return None
    guess = json.loads(PREDICTION.read_text(encoding="utf-8"))
    day = pack["anki_today"]
    if guess.get("anki_today") != day:
        _check_log(f"day {day}: no prediction for this day (the last one was for day {guess.get('anki_today')})")
        return None
    made_at = guess["predicted"]["made_at"]
    reviewed_since = col.db.scalar("select count() from revlog where id > ?", made_at * 1000)

    def today(p, kind=None):
        return [c for c in p["cards"] if c["due_day"] <= day and (kind is None or c["kind"] == kind)]

    real_ids = [c["cid"] for c in today(pack)]
    guess_ids = [c["cid"] for c in today(guess)]
    only_real = sorted(set(real_ids) - set(guess_ids))
    only_guess = sorted(set(guess_ids) - set(real_ids))
    real_rev = [c["cid"] for c in today(pack, "review")]
    guess_rev = [c["cid"] for c in today(guess, "review")]
    order_same = real_rev == guess_rev
    moved = sum(1 for a, b in zip(real_rev, guess_rev) if a != b)
    by_id = {c["cid"]: c for c in today(guess)}
    learn_due_diff = [c["cid"] for c in today(pack, "learn") if c["cid"] in by_id and c.get("due_at") != by_id[c["cid"]].get("due_at")]
    secs_diff = [c["cid"] for c in today(pack) if c["cid"] in by_id
                 and (c["again_secs"], c["good_secs"]) != (by_id[c["cid"]]["again_secs"], by_id[c["cid"]]["good_secs"])]
    later_same = ({c["cid"] for c in pack["cards"] if c["due_day"] > day}
                  == {c["cid"] for c in guess["cards"] if c["due_day"] > day})
    exact = not only_real and not only_guess and order_same and not learn_due_diff
    summary = (f"day {day}: {'EXACT MATCH' if exact else 'DIFFERENT'}: {len(real_ids)} cards today "
               f"(predicted {len(guess_ids)}), only in the 4:30 list {len(only_real)}, only predicted {len(only_guess)}, "
               f"review order {'same' if order_same else f'{moved} positions differ'}, "
               f"learning due times differ {len(learn_due_diff)}, Again/Good times differ {len(secs_diff)}, "
               f"later days {'same' if later_same else 'differ'}; reviews done after the prediction: {reviewed_since}")
    _check_log(summary)
    CHECK_FILE.write_text(json.dumps({
        "day": day, "summary": summary, "predicted_at": made_at, "checked_at": int(time.time()),
        "reviewed_since": reviewed_since, "only_real": only_real, "only_predicted": only_guess,
        "real_review_order": real_rev, "predicted_review_order": guess_rev,
        "learning_due_differs": learn_due_diff, "again_good_differs": secs_diff,
    }))
    return summary


def task_time() -> str:
    """Half an hour after Anki's day starts (its rollover hour, 4 am by default)."""
    rollover = 4
    if SETTINGS.exists():
        rollover = int(json.loads(SETTINGS.read_text()).get("rollover", 4))
    return f"{rollover:02d}:30"


def schedule(python: Path, workdir: Path) -> str:
    """Create or update the daily task. Windows only for now. It may make audio for the new day
    (auto_voice), which can take an hour on a slow laptop, so Windows may run it for up to 4 hours."""
    if sys.platform != "win32":
        raise RuntimeError("The morning job is only set up automatically on Windows so far.")
    pythonw = python.with_name("pythonw.exe") if python.with_name("pythonw.exe").exists() else python
    script = f"""
$a = New-ScheduledTaskAction -Execute '{pythonw}' -Argument '-m car_review.helper morning' -WorkingDirectory '{workdir}'
$t = New-ScheduledTaskTrigger -Daily -At '{task_time()}'
$s = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 4)
Register-ScheduledTask -TaskName '{TASK_NAME}' -Description 'Sends today''s Car Review list to your phone (made by the Car Review Anki add-on).' -Action $a -Trigger $t -Settings $s -Force | Out-Null
"""
    run = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, timeout=60)
    if run.returncode != 0:
        raise RuntimeError(run.stderr.strip()[-500:])
    return f"daily at {task_time()}"


def unschedule() -> None:
    if sys.platform == "win32":
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue"],
                       capture_output=True, text=True, timeout=60)
