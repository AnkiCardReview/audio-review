"""The Audio Review bar on Anki's main screen (under the deck list).

It shows what the laptop last sent to the phone and what the phone has picked up, with buttons
for the things you'd otherwise find in Tools ▸ Audio Review. Everything it shows comes from files
the helper already writes (status.json, phone.json): the bar itself never contacts the relay.
"Check phone" does, once, when pressed (the same request as checking for phone answers).

While the deck list is on screen, a light timer looks at those files' times every few seconds
and redraws the bar in place when one changes, so a send shows its progress and result.
"""

from __future__ import annotations

import html
import json
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from aqt import gui_hooks, mw
from aqt.qt import QTimer

from .common import HOME, PAIRING, PHONE, STATUS, pid_alive

LOCK = HOME / "helper.lock"
BAR_ID = "car-review-bar"

_actions: dict[str, Callable[[], None]] = {}
_setting: Callable[[str], Any] = lambda key: None
_timer: QTimer | None = None
_drawn: tuple | None = None


def _read(path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _when(ts: float) -> str:
    """'just now', '12:41', 'yesterday 21:03' or 'Mon 3 Nov 08:10'."""
    if not ts:
        return "never"
    if time.time() - ts < 60:
        return "just now"
    then, now = datetime.fromtimestamp(ts), datetime.now()
    clock = then.strftime("%H:%M")
    if then.date() == now.date():
        return f"today {clock}"
    if then.date() == (now - timedelta(days=1)).date():
        return f"yesterday {clock}"
    return f"{then.strftime('%a')} {then.day} {then.strftime('%b')} {clock}"


def _helper_running() -> bool:
    try:
        return LOCK.exists() and pid_alive(int(LOCK.read_text()))
    except (OSError, ValueError):
        return False


def _sent_line() -> str:
    """Laptop → phone: the last send, or the one running now."""
    s = _read(STATUS)
    state = s.get("state", "")
    ready, total = s.get("ready", 0), s.get("total", 0)
    made = s.get("made", 0)
    if not s:
        return "<b>Nothing sent yet.</b> Press Send to phone, or sync or close Anki."
    if state == "error":
        return (f"<b class=crb-warn>⚠ The last send stopped</b> ({_when(s.get('updated', 0))}): "
                f"{html.escape(str(s.get('error', ''))[:160])}")
    if state == "preparing audio ahead":
        return (f"<b>Making audio</b>: {made:,} of {total:,} clips"
                + (" (running now)" if _helper_running() else f" ({_when(s.get('updated', 0))})"))
    if state.startswith("paused"):
        return f"<b>Paused: plug in</b> to make audio ({ready:,} of {total:,} cards on the phone so far)."
    if state == "sending" and _helper_running():
        return (f"<b>Sending now…</b> {ready:,} of {total:,} cards ready"
                + (f", {made:,} new clips made" if made else ""))
    if state == "sending":  # the helper stopped without saying (closed, crashed)
        return f"<b>The last send didn't finish</b> ({_when(s.get('updated', 0))}). Press Send to phone."
    unvoiced = s.get("unvoiced", 0)
    line = (f"<b>{'Up to date' if s.get('unchanged') else 'Sent'} {_when(s.get('updated', 0))}</b>: "
            f"{ready:,} of {total:,} cards ready on the phone")
    if unvoiced:
        line += f", {unvoiced:,} without audio yet"
    if state == "stopped":
        line += " (stopped early)"
    if _helper_running():
        line += ". Still working…"
    return line + "."


def _phone_line() -> str:
    """What the phone had picked up, as of the last time this computer looked."""
    p = _read(PHONE)
    if not p:
        return "Phone: not checked yet. Press Check phone."
    parts = []
    if p.get("waiting"):
        mb = p.get("waiting_bytes", 0) / 1e6
        parts.append(f"<b>hasn't downloaded {p['waiting']} audio file{'s' if p['waiting'] != 1 else ''} yet</b> "
                     f"({mb:.0f} MB). Open Audio Review on the phone and tap Sync")
    else:
        parts.append("<b>has everything that was sent</b>")
    if p.get("grades"):
        parts.append(f"<b>phone answers waiting</b> (from {_when(p.get('grades_at', 0))}): Check phone applies them")
    if p.get("have_at"):
        parts.append(f"last took new audio {_when(p['have_at'])}")
    return "Phone " + "; ".join(parts) + f". <span class=crb-dim>(Checked {_when(p.get('checked', 0))}.)</span>"


def _button(action: str, label: str, title: str) -> str:
    return (f"<button onclick=\"pycmd('carreview:{action}');return false;\" title=\"{html.escape(title)}\">"
            f"{html.escape(label)}</button>")


def bar_html() -> str:
    if not _setting("decks"):
        body = "Choose which decks to hear as audio to get started."
        buttons = _button("settings", "Set up Audio Review…", "Choose decks, set up the voice and pair your phone")
    elif not PAIRING.exists():
        body = "No phone is paired with this computer yet."
        buttons = _button("pair", "Pair phone…", "Show the QR code to scan with your iPhone")
    else:
        body = f"<div>{_sent_line()}</div><div>{_phone_line()}</div>"
        buttons = (_button("send", "Send to phone", "Send today's and tomorrow's cards that already have audio")
                   + _button("prepare", "Make audio and send",
                             "Make the missing audio for the coming days (while plugged in), then send")
                   + _button("check", "Check phone",
                             "See what the phone has downloaded, and pick up its phone answers")
                   + _button("settings", "Settings…", "Audio Review settings"))
    return f"""
<div id="{BAR_ID}">
<style>
#{BAR_ID} {{ max-width: 46em; margin: 1.2em auto 0; padding: .7em 1em; text-align: left;
  border: 1px solid rgba(128,128,128,.35); border-radius: 8px; font-size: .92em; line-height: 1.45; }}
#{BAR_ID} .crb-title {{ font-weight: 600; margin-bottom: .25em; }}
#{BAR_ID} .crb-dim {{ opacity: .65; }}
#{BAR_ID} .crb-warn {{ color: #c0392b; }}
#{BAR_ID} .crb-buttons {{ margin-top: .55em; display: flex; flex-wrap: wrap; gap: .4em; }}
#{BAR_ID} .crb-hint {{ margin-top: .5em; font-size: .85em; opacity: .65; }}
</style>
<div class="crb-title">🎧 Audio Review</div>
{body}
<div class="crb-buttons">{buttons}</div>
<div class="crb-hint">Sends by itself when Anki syncs, opens or closes (only if your cards changed).
The phone downloads when you tap Sync, when Anki's day changes, and after Stop.</div>
</div>"""


def _signature() -> tuple:
    def mtime(path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0

    # The minute too, so "just now" and "today" stay right.
    return (mtime(STATUS), mtime(PHONE), mtime(LOCK), PAIRING.exists(), bool(_setting("decks")),
            int(time.time() // 60))


def on_render(deck_browser, content) -> None:
    global _drawn
    if not _setting("main_bar"):
        return
    content.stats += bar_html()
    _drawn = _signature()


def refresh() -> None:
    """Redraw the bar in place (no page reload) if something it shows has changed."""
    global _drawn
    if not _setting("main_bar") or mw.state != "deckBrowser" or not getattr(mw, "deckBrowser", None):
        return
    sig = _signature()
    if sig == _drawn:
        return
    _drawn = sig
    mw.deckBrowser.web.eval(
        f"(function(){{var e=document.getElementById('{BAR_ID}');if(e)e.outerHTML={json.dumps(bar_html())};}})();")


def redraw() -> None:
    """After a settings change: the whole deck list again, with or without the bar."""
    if mw.state == "deckBrowser" and getattr(mw, "deckBrowser", None):
        mw.deckBrowser.refresh()


def on_js_message(handled: tuple[bool, Any], message: str, context: Any) -> tuple[bool, Any]:
    if not message.startswith("carreview:"):
        return handled
    action = _actions.get(message.split(":", 1)[1])
    if action:
        action()
        QTimer.singleShot(1_500, refresh)
    return (True, None)


def setup(actions: dict[str, Callable[[], None]], setting: Callable[[str], Any]) -> None:
    global _setting, _timer
    _actions.update(actions)
    _setting = setting
    gui_hooks.deck_browser_will_render_content.append(on_render)
    gui_hooks.webview_did_receive_js_message.append(on_js_message)
    # Only file times are looked at (no network), and only while the deck list is showing.
    _timer = QTimer(mw)
    _timer.timeout.connect(refresh)
    _timer.start(3_000)
