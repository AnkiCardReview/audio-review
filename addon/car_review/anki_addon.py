"""Anki side of Audio Review.

Automatic:
- First run: the setup wizard (settings.py) opens by itself, once.
- When Anki opens (after its opening sync): if there are phone answers, show what they'd do,
  with an Apply button. Then remind you if upcoming cards still need audio.
- While Anki is open, like Anki's own sync, nothing runs on a timer: after each Anki sync phone
  grades are picked up the same way and a fresh list goes to the phone if your cards changed;
  after a review session on the laptop a fresh list goes out, so the phone never replays cards
  you've already done here.
- When Anki closes: send the audio list (today plus the next few days, and the next day's exact
  cards) to your phone. This is quick: only cards that already have audio are sent. If
  "auto_voice" is on and the laptop is plugged in, missing audio is made too, after Anki has closed.

Anki's main screen has an Audio Review bar (main_bar.py): what was last sent and what the phone has
picked up, with Send to phone, Make audio and send, Check phone and Settings buttons.

Tools ▸ Audio Review menu: Settings, Send to phone, Prepare audio, Make audio for whole decks,
Apply phone answers, Pair phone, Status, Audio stats, Help.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from anki.collection import OpChanges
from aqt import gui_hooks, mw
from aqt.operations import CollectionOp, QueryOp
from aqt.qt import QAction, QCheckBox, QDialog, QDialogButtonBox, QLabel, QMenu, QMessageBox, QScrollArea, QTimer, QVBoxLayout
from aqt.utils import askUser, openLink, showInfo, showText, showWarning, tooltip

from . import main_bar, voice_setup
from .apply import Plan, apply_plan, plan_grades
from .builder import build_pack
from .common import CACHE, HOME, INBOX, PACK, STATUS, voice_speed
from .power import on_charger
from .settings import DEFAULTS, HELP_URL, open_settings

ADDON_DIR = Path(__file__).resolve().parent


def setting(key: str):
    return (mw.addonManager.getConfig(__name__) or {}).get(key, DEFAULTS[key])


# ---------- Running the helper ----------

def helper_python(windowless: bool = False) -> Path:
    if setting("python"):
        return Path(setting("python"))
    return voice_setup.helper_python(windowless)


def helper_command(*args: str, windowless: bool = False) -> list[str]:
    python = helper_python(windowless)
    if not python.exists():
        raise RuntimeError("Audio Review's voice isn't set up on this computer yet. "
                           "Open Tools ▸ Audio Review ▸ Settings ▸ Voice and press “Set up the voice”.")
    # The add-on's folder is "car_review" when copied from GitHub, or a number when installed from AnkiWeb.
    return [str(python), "-m", f"{ADDON_DIR.name}.helper", *args]


def _flags(detached: bool) -> int:
    if sys.platform != "win32":
        return 0
    return subprocess.CREATE_NO_WINDOW | (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if detached else 0)


def run_helper(*args: str) -> subprocess.CompletedProcess:
    """Run a short helper command and wait for it (safe to call from a background op)."""
    return subprocess.run(helper_command(*args), capture_output=True, text=True, timeout=180,
                          cwd=str(ADDON_DIR.parent), creationflags=_flags(False))


def start_helper(*args: str) -> None:
    """Start the helper on its own; it keeps running after Anki closes. Always pythonw.exe: the
    venv's python.exe is a launcher that starts the real Python, which, detached from any
    console, would open a blank console window of its own."""
    subprocess.Popen(helper_command(*args, windowless=True), cwd=str(ADDON_DIR.parent), creationflags=_flags(True),
                     start_new_session=sys.platform != "win32")


# ---------- Sending ----------

def missing_audio(pack: dict) -> int:
    return sum(1 for c in pack["cards"]
               if not (CACHE / f"{c['q_audio']}.mp3").exists() or not (CACHE / f"{c['a_audio']}.mp3").exists())


_last_sent_mod = None  # the collection's modified time when the last list was sent


def start_send(pack: dict, voice: bool) -> None:
    """Hand the list to the helper. A window only appears when there's audio to make; a quick
    send (a few seconds) runs without one."""
    global _last_sent_mod
    pack["voice_missing"] = voice
    PACK.parent.mkdir(parents=True, exist_ok=True)
    PACK.write_text(json.dumps(pack), encoding="utf-8")
    quiet = not (voice and missing_audio(pack))
    start_helper("send", "--pack", str(PACK), *(["--no-window"] if quiet else []))
    try:
        _last_sent_mod = mw.col.mod if mw.col else None
    except Exception:
        _last_sent_mod = None
    remember_settings()


def remember_settings() -> None:
    """Save what the helper needs to make the next day's list from a copy of the collection, and
    remove the 4:30 am task that earlier versions added."""
    from . import morning

    try:
        morning.save_settings(
            profile=mw.pm.name,
            collection=mw.pm.collectionPath(),
            decks=setting("decks"),
            days_ahead=int(setting("days_ahead")),
            auto_voice=bool(setting("auto_voice")),
            rollover=int(mw.col.get_config("rollover", 4)),
            voice_threads=int(setting("voice_threads") or 3),
            voice_gpu=bool(setting("voice_gpu")),
        )
        marker = HOME / "morning-task.json"
        if marker.exists():
            run_helper("unschedule")
            marker.unlink()
    except Exception as err:  # never let this get in the way of sending
        print(f"Audio Review: couldn't save the settings for the next day's list: {err}")


def build(col) -> dict:
    return build_pack(col, setting("decks"), days_ahead=int(setting("days_ahead")))


def need_setup() -> bool:
    """True (after offering the settings window) while decks or the voice are still missing."""
    if not setting("decks"):
        if askUser("Choose which decks to hear as audio first. Open Audio Review settings?"):
            open_settings("Decks")
        return True
    if not helper_python().exists():
        if askUser("The voice isn't set up on this computer yet (a one-time download). Set it up now?"):
            open_settings("Voice")
        return True
    return False


def no_cards_message(pack: dict) -> str:
    skipped = pack.get("skipped") or {}
    if skipped.get("not a cloze card"):
        return ("No cards to send: Audio Review only plays cloze cards, and the chosen decks have none due. "
                "Choose other decks in Tools ▸ Audio Review ▸ Settings.")
    return "No cards are due in your audio decks today or in the next few days."


def send_to_car() -> None:
    """Quick send: only cards that already have audio."""
    if need_setup():
        return

    def done(pack: dict) -> None:
        if not pack["cards"]:
            showInfo(no_cards_message(pack))
            return
        start_send(pack, voice=False)
        missing = missing_audio(pack)
        tooltip(f"Sending {len(pack['cards']) - missing} cards to your phone."
                + (f" {missing} still need audio (Tools ▸ Audio Review ▸ Prepare audio)." if missing else ""),
                period=8000)

    QueryOp(parent=mw, op=build, success=done).with_progress("Building the card list…").run_in_background()


def prepare_audio() -> None:
    """Make missing audio for the coming days, then send everything."""
    if need_setup():
        return
    if not on_charger() and not askUser(
            "Your computer is on battery. Audio is only made while it's plugged in, so it will wait "
            "until you plug in. Start anyway?"):
        return

    def done(pack: dict) -> None:
        if not pack["cards"]:
            showInfo(no_cards_message(pack))
            return
        missing = missing_audio(pack)
        start_send(pack, voice=True)
        tooltip(f"Making audio for {missing} cards, then sending {len(pack['cards'])} to your phone. "
                "Progress shows in its own window.", period=8000)

    QueryOp(parent=mw, op=build, success=done).with_progress("Building the card list…").run_in_background()


def missing_clips(cards: list[dict]) -> int:
    """Clips these cards need that aren't made yet (shared clips counted once)."""
    names = {c[k] for c in cards for k in ("q_audio", "a_audio")}
    return sum(1 for n in names if not (CACHE / f"{n}.mp3").exists())


def how_long(clips: int) -> str:
    """'about 6 h 50 min on this computer', from its measured speed."""
    secs = voice_speed()
    if secs is None:
        return ("this computer's speed isn't known yet (it's measured as audio is made; as a guide, "
                "a slow laptop takes about 5 seconds a clip, a fast desktop under 1)")
    total = clips * secs
    if total < 3600:
        return f"about {max(1, round(total / 60))} min on this computer"
    return f"about {int(total // 3600)} h {round(total % 3600 / 60)} min on this computer"


def prepare_whole_decks() -> None:
    """Make audio for every card in the audio decks, the ones needed soonest first (Tools ▸ Audio
    Review ▸ Make audio for whole decks). Only when asked: on a slow computer it takes hours."""
    if need_setup():
        return
    from .builder import whole_deck_cards

    def done(cards: list[dict]) -> None:
        active = [c for c in cards if not c["suspended"]]
        suspended = [c for c in cards if c["suspended"]]
        todo = missing_clips(active)
        extra = missing_clips(active + suspended) - todo
        box = QMessageBox(mw)
        box.setWindowTitle("Audio Review: make audio for whole decks")
        box.setText(
            f"Your audio decks have {len(active):,} cards that work as audio. "
            + (f"<b>{todo:,} clips</b> still need audio: {how_long(todo)}." if todo else "All of them already have audio.")
            + "<br><br>Cards are done in the order you'll need them: the next reviews first, then later ones, "
            "then cards you haven't started yet. It runs in the background at low priority and only while "
            "plugged in. You can pause or stop it, and it carries on where it stopped next time.")
        include = None
        if extra:
            include = QCheckBox(f"Also suspended cards: {len(suspended):,} cards, {extra:,} clips ({how_long(extra)})")
            box.setCheckBox(include)
        start = box.addButton("Start", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not start:
            return
        chosen = active + (suspended if include and include.isChecked() else [])
        if not missing_clips(chosen):
            tooltip("Audio Review: all those cards already have audio.")
            return
        if not on_charger() and not askUser("Your computer is on battery. Audio is only made while it's "
                                            "plugged in, so it will wait until you plug in. Start anyway?"):
            return
        remember_settings()  # so the helper uses the current voice settings
        path = HOME / "outbox" / "whole-decks.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"cards": chosen}), encoding="utf-8")
        start_helper("prepare", "--pack", str(path))
        tooltip("Making audio for your whole decks. Progress shows in its own window.", period=8000)

    QueryOp(parent=mw, op=lambda col: whole_deck_cards(col, setting("decks"), include_suspended=True),
            success=done).with_progress("Counting cards…").run_in_background()


def on_close() -> None:
    """Send the list when Anki closes. Never blocks closing for more than the few seconds the
    list takes to build, and never raises."""
    try:
        if not setting("decks") or not mw.col or not helper_python().exists():
            return
        pack = build(mw.col)
        start_send(pack, voice=bool(setting("auto_voice")) and on_charger())
    except Exception as err:  # closing Anki must never fail because of Audio Review
        print(f"Audio Review: couldn't send on close: {err}")


# ---------- When Anki opens ----------

_startup_pending = False


def on_profile_open() -> None:
    global _startup_pending
    config = mw.addonManager.getConfig(__name__) or {}
    if not config.get("decks") and not config.get("setup_done"):
        # First run: open the setup wizard once Anki has settled. Only once; after that it's in
        # Tools ▸ Audio Review ▸ Settings.
        config["setup_done"] = True
        mw.addonManager.writeConfig(__name__, config)
        QTimer.singleShot(3_000, first_run)
        return
    _startup_pending = True
    # If Anki syncs on open, wait for that sync so phone reviews are known; otherwise go now.
    syncs_on_open = mw.pm.auto_syncing_enabled() and bool(mw.pm.sync_auth())
    QTimer.singleShot(60_000 if syncs_on_open else 2_000, startup_check)


def first_run() -> None:
    open_settings(first_run=True)


def on_sync_finished() -> None:
    if _startup_pending:
        startup_check()
    else:
        keep_in_step_soon()


# ---------- Keeping the phone in step while Anki stays open ----------

_keep_timer: QTimer | None = None
_busy = False


def keep_in_step_soon(delay_ms: int = 5_000) -> None:
    """Pick up phone answers and send a fresh list shortly (calls close together count once)."""
    global _keep_timer
    if _keep_timer is None:
        _keep_timer = QTimer(mw)
        _keep_timer.setSingleShot(True)
        _keep_timer.timeout.connect(keep_in_step)
    _keep_timer.start(delay_ms)


def keep_in_step() -> None:
    global _busy
    if _busy or _startup_pending or not mw.col or not setting("decks") or not helper_python().exists():
        return
    if mw.state == "review":  # never change cards under you while you review
        keep_in_step_soon(120_000)
        return
    _busy = True

    def finished() -> None:
        global _busy
        _busy = False
        send_if_changed()

    check_grades(mode="auto", then=finished)


def send_if_changed() -> None:
    """Send a fresh list if the collection changed since the last one (reviews on the laptop,
    applied phone answers, a sync). Quick and windowless unless there's audio to make."""
    if not mw.col or mw.col.mod == _last_sent_mod:
        return

    def done(pack: dict) -> None:
        if not pack["cards"]:
            return
        voice = bool(setting("auto_voice")) and on_charger()
        missing = missing_audio(pack) if voice else 0
        start_send(pack, voice=voice)
        if missing:
            tooltip(f"Audio Review: making audio for {missing} cards in the background, then sending.", period=6000)

    QueryOp(parent=mw, op=build, success=done).failure(lambda err: print(f"Audio Review: {err}")).run_in_background()


def on_state_change(new_state: str, old_state: str) -> None:
    # After reviewing on the laptop, a fresh list so the phone doesn't play those cards again.
    # Phone answers are only picked up when Anki syncs, opens or closes (like Anki's own sync).
    if old_state == "review" and new_state != "review":
        QTimer.singleShot(5_000, send_if_changed)


def startup_check() -> None:
    global _startup_pending
    if not _startup_pending:
        return
    _startup_pending = False
    if not setting("decks") or not helper_python().exists():
        return
    check_grades(mode="startup")


def remind_about_audio() -> None:
    if setting("auto_voice"):
        return  # made automatically when Anki closes while plugged in

    def done(pack: dict) -> None:
        missing = missing_audio(pack)
        if missing:
            tooltip(f"Audio Review: {missing} cards in the next {int(setting('days_ahead')) + 1} days have no audio yet. "
                    "When plugged in: Tools ▸ Audio Review ▸ Prepare audio.", period=12000)

    QueryOp(parent=mw, op=build, success=done).run_in_background()


# ---------- Applying phone answers ----------

_declined: set = set()  # grade sets you pressed Cancel on: not offered again by the automatic checks


def check_grades(mode: str = "manual", then=None) -> None:
    """mode: "startup" (Anki just opened), "auto" (while open, quietly) or "manual" (the menu)."""
    on_startup = mode != "manual"
    finish = then or (lambda: None)
    def fetch_and_plan(col):
        result = run_helper("fetch-grades")
        if result.returncode != 0:
            detail = (result.stderr.strip().splitlines() or [""])[-1][:300]
            raise RuntimeError("Couldn't download your phone answers. Check your internet connection, then try "
                               f"Tools ▸ Audio Review ▸ Apply phone answers.\n\nDetails: {detail}")
        names = json.loads(result.stdout.strip() or "[]")
        files = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(INBOX.glob("*.json"))]
        return (plan_grades(col, files) if files else None), names

    def after() -> None:
        if mode == "startup":
            remind_about_audio()
        finish()

    def done(result) -> None:
        plan, names = result
        if plan is None or (not plan.cards and not plan.skip_tags):
            if names:
                start_helper("delete-grades", *names)
            if mode == "manual":
                tooltip("No phone answers waiting. After a session, check that the phone shows “✓ all” "
                        "next to Grades uploaded.", period=8000)
            after()
            return
        key = (tuple(names), plan.grade_count)
        if on_startup and setting("auto_apply") and not plan.late_days:
            apply_now(plan, names, allow_late=False, then=after)
        elif mode == "auto" and key in _declined:
            finish()  # you said Cancel to exactly these; Tools ▸ Audio Review ▸ Apply phone answers offers them again
        else:
            confirm_apply(plan, names, then=after, on_cancel=lambda: _declined.add(key))

    def failed(err: Exception) -> None:
        if mode == "startup":
            tooltip("Audio Review: couldn't check for phone answers (are you offline?). "
                    "Try Tools ▸ Audio Review ▸ Apply phone answers later.", period=8000)
        if mode == "manual":
            showWarning(str(err))
        else:
            print(f"Audio Review: {err}")
        finish()

    op = QueryOp(parent=mw, op=fetch_and_plan, success=done).failure(failed)
    (op if on_startup else op.with_progress("Checking phone answers…")).run_in_background()


def apply_car_grades() -> None:
    if need_setup():
        return
    check_grades(mode="manual")


def confirm_apply(plan: Plan, names: list[str], then=None, on_cancel=None) -> None:
    goods = sum(1 for c in plan.cards for g in c.grades if g["rating"] == 3)
    agains = plan.grade_count - goods

    dialog = QDialog(mw)
    dialog.setWindowTitle("Audio Review: apply phone answers")
    layout = QVBoxLayout(dialog)
    lines = [f"<b>{plan.grade_count} answers from the phone for {len(plan.cards)} cards</b> ({goods} Good, {agains} Again)."]
    if plan.skip_tags:
        lines.append(f"{len(plan.skip_tags)} card(s) you skipped as not audio-friendly will be tagged "
                     "<i>audio-review::skip</i> and left out of future audio lists.")
    if plan.skipped:
        lines.append("Not applied: " + ", ".join(f"{v} {k}" for k, v in plan.skipped.items()) + ".")
    lines.append("Anki makes a backup first, and <b>Edit ▸ Undo</b> reverts all of it in one step.")
    text = QLabel("<br><br>".join(lines))
    text.setWordWrap(True)
    layout.addWidget(text)

    preview = QLabel("<br>".join(f"{c.preview}" for c in plan.cards[:40])
                     + (f"<br>… and {len(plan.cards) - 40} more" if len(plan.cards) > 40 else ""))
    scroll = QScrollArea()
    scroll.setWidget(preview)
    scroll.setMaximumHeight(220)
    layout.addWidget(QLabel("First answer for each card (what Anki will do):"))
    layout.addWidget(scroll)

    late = None
    if plan.late_days:
        late = QCheckBox("Some answers are from an earlier day. Apply them anyway "
                         "(their next interval is counted from today, so it lands about a day later).")
        late.setChecked(False)
        layout.addWidget(late)

    buttons = QDialogButtonBox()
    apply_button = buttons.addButton("Apply", QDialogButtonBox.ButtonRole.AcceptRole)
    buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    apply_button.setDefault(True)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        if on_cancel:
            on_cancel()
        if then:
            then()
        return
    apply_now(plan, names, allow_late=bool(late and late.isChecked()), then=then)


def apply_now(plan: Plan, names: list[str], allow_late: bool, then=None) -> None:
    report_box: dict = {}

    def op(col):
        mw.create_backup_now()  # waits until the backup is written
        report = apply_plan(col, plan, allow_late=allow_late)
        report_box["report"] = report
        return report.changes or OpChanges()  # nothing changed when late grades were held back

    def done(_changes) -> None:
        r = report_box["report"]
        summary = [f"Applied {sum(r.applied.values())} phone answers to {r.cards} cards "
                   f"({r.applied.get('Good', 0)} Good, {r.applied.get('Again', 0)} Again)."]
        if r.tagged:
            summary.append(f"Tagged {r.tagged} card(s) as not audio-friendly.")
        if r.skipped:
            summary.append("Not applied: " + ", ".join(f"{v} {k}" for k, v in r.skipped.items()) + ".")
        if r.mismatches or r.failures:
            summary.append("\nProblems (please report these):\n" + "\n".join(r.mismatches + r.failures))
            showWarning("\n".join(summary))
        else:
            tooltip("<br>".join(summary) + "<br>Edit ▸ Undo reverts it. Sync when you're ready.", period=10000)
        if not r.failures and not (plan.late_days and not allow_late):
            start_helper("delete-grades", *names)
        if then:
            then()

    CollectionOp(parent=mw, op=op).success(done).run_in_background()


# ---------- Pair phone ----------

def pair_phone() -> None:
    open_settings("Phone")


# ---------- Status ----------

def show_status() -> None:
    if not STATUS.exists():
        showInfo("Nothing has been sent to your phone yet. Close Anki (or use Tools ▸ Audio Review ▸ Send to phone) "
                 "to send your cards.")
        return
    s = json.loads(STATUS.read_text())
    if s.get("state") == "error":
        showWarning(f"The last send stopped with an error:\n\n{s.get('error')}\n\n"
                    f"Try again with Tools ▸ Audio Review ▸ Send to phone. Details are in {HOME / 'helper.log'}")
        return
    mins = round(s.get("elapsed", 0) / 60)
    lines = [f"Last run: {s.get('state', '?')}."]
    if "ready" in s:
        lines.append(f"Cards on the phone: {s.get('ready', 0)} of {s.get('total', 0)}")
    if s.get("unvoiced"):
        lines.append(f"Cards still without audio: {s['unvoiced']} (Tools ▸ Audio Review ▸ Prepare audio)")
    lines.append(f"New audio made: {s.get('made', 0)} clips in {mins} min")
    lines.append("Every list also holds the next day's cards, made by Anki's scheduler, and the phone "
                 "switches to them when Anki's day changes. Sync or close Anki after your last review of the day.")
    showInfo("\n".join(lines))


# ---------- Audio stats ----------

def show_stats() -> None:
    """Your sessions, audio vs Anki retention per deck, and where the time went (stats.py)."""
    if not mw.col:
        return
    from .stats import report_html

    def done(text: str) -> None:
        showText(text, type="html", title="Audio Review: audio stats", minWidth=720, minHeight=560)

    QueryOp(parent=mw, op=lambda col: report_html(col, list(setting("decks") or [])),
            success=done).failure(lambda err: showWarning(f"Couldn't make the audio stats: {err}")).run_in_background()


# ---------- Setup ----------

def open_settings_menu() -> None:
    open_settings()


def setup() -> None:
    menu = QMenu("Audio Review", mw)
    days = int(setting("days_ahead"))
    for label, fn in (("Settings…", open_settings_menu),
                      (None, None),
                      ("Send to phone", send_to_car),
                      (f"Prepare audio (next {days} days)", prepare_audio),
                      ("Make audio for whole decks…", prepare_whole_decks),
                      ("Apply phone answers…", apply_car_grades),
                      ("Pair phone…", pair_phone),
                      ("Status", show_status),
                      ("Audio stats", show_stats),
                      (None, None),
                      ("Help", lambda: openLink(HELP_URL))):
        if label is None:
            menu.addSeparator()
            continue
        action = QAction(label, mw)
        action.triggered.connect(fn)
        menu.addAction(action)
    mw.form.menuTools.addMenu(menu)
    # Tools ▸ Add-ons ▸ Config opens the settings window instead of the raw JSON.
    mw.addonManager.setConfigAction(__name__, open_settings_menu)
    gui_hooks.profile_did_open.append(on_profile_open)
    gui_hooks.sync_did_finish.append(on_sync_finished)
    gui_hooks.profile_will_close.append(on_close)
    gui_hooks.state_did_change.append(on_state_change)
    main_bar.setup({"send": send_to_car, "prepare": prepare_audio, "check": apply_car_grades,
                    "settings": open_settings_menu, "pair": pair_phone}, setting)
    # No timer: like Anki itself, Audio Review syncs when Anki syncs, opens and closes, so a laptop
    # left open all day makes no requests in between.


setup()
