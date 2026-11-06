"""The next day's list: made from Anki's own scheduler whenever a list is sent, so the phone has
the new day's exact queue in the morning without the computer being on.

It opens a temporary COPY of the collection with Anki's engine (the `anki` package, same version
as your Anki), so the real collection is never touched. Anki writes `morning.json` (profile,
collection path, decks) every time it sends a list, so this always uses your current settings.

On the copy, Anki's "today" moves one day on (unburying, daily limits and due cards then work
exactly as at the new day), every card's last-review time moves back by the time from now to
half an hour after the next rollover (FSRS retrievability, and with it the review order and which
of two due siblings is shown, is then as early in the new day), and intraday learning cards move
back by the length of that day, so the ones due before the following rollover are the same.
Anki's own queue on that copy is the next day's list. Checked against the real morning list on
2026-10-30 to 11-03: the same cards whenever no reviews were done in between.

Earlier versions sent the new day's list from a 4:30 am scheduled task instead; `unschedule`
removes that task from computers that still have it.
"""

from __future__ import annotations

import json
import os
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
TASK_NAME = "Car Review morning list"  # the retired 4:30 am task (its real name in Windows: keep)
EARLY_IN_THE_DAY = 30 * 60  # the next day's list is as Anki would make it this long after the rollover


def save_settings(**fields) -> None:
    """Called by the add-on with profile, collection path, decks, days_ahead, auto_voice, rollover."""
    HOME.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(fields))


def _settings() -> dict:
    if not SETTINGS.exists():
        raise RuntimeError("Audio Review hasn't sent a list from Anki yet, so it doesn't know your decks.")
    return json.loads(SETTINGS.read_text())


def _stamp(source: Path) -> tuple:
    """Sizes and times of the collection and its write-ahead log: if they change while copying,
    Anki was writing (for example closing), and the copy is made again."""
    out = []
    for suffix in ("", "-wal"):
        try:
            st = os.stat(str(source) + suffix)
            out.append((st.st_size, st.st_mtime_ns))
        except OSError:
            out.append(None)
    return tuple(out)


def _open_copy(source: Path, tmp: str, shift_days: int = 0):
    """A copy of the collection (with its write-ahead log) opened with Anki's engine. With
    shift_days, the copy's creation date moves back that many days first, so Anki's "today" on the
    copy is that many days later; due dates themselves don't change."""
    try:
        from anki.collection import Collection  # Anki's own engine, same version as your Anki
    except ImportError as err:
        raise RuntimeError("The next day's list needs Anki's engine in Audio Review's Python.") from err
    path = Path(tmp) / "collection.anki2"
    for _attempt in range(10):
        before = _stamp(source)
        for suffix in ("-wal", ""):
            Path(str(path) + suffix).unlink(missing_ok=True)
            if Path(str(source) + suffix).exists():
                shutil.copy2(str(source) + suffix, str(path) + suffix)
        if _stamp(source) == before:
            break
        time.sleep(2)  # Anki was writing the collection: copy again once it's done
    else:
        raise RuntimeError("the collection kept changing while it was copied")
    if shift_days:
        db = sqlite3.connect(path)
        db.execute("update col set crt = crt - ?", (86400 * shift_days,))
        db.commit()
        db.close()
    return Collection(str(path))


def _next_rollover(after: float) -> float:
    """The same local time one calendar day later (23 or 25 hours across a clock change)."""
    return (datetime.fromtimestamp(after) + timedelta(days=1)).timestamp()


def build_next_day_pack(now: float | None = None) -> dict:
    """The list for the Anki day that starts at the next rollover, as Anki would make it early that
    day. Never changes the real collection."""
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
                "where json_extract(data, '$.lrt') is not null", int(starts + EARLY_IN_THE_DAY - now))
            pack = build_pack(col, settings["decks"], days_ahead=0, now=now)
        finally:
            col.close(downgrade=False)
    for card in pack["cards"]:
        if card.get("due_at"):
            card["due_at"] += learning_shift
    pack["next_day_at"] = ends
    pack["starts_at"] = starts
    return pack


def unschedule() -> None:
    """Remove the 4:30 am task that earlier versions added (Windows)."""
    if sys.platform == "win32":
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue"],
                       capture_output=True, text=True, timeout=60)
