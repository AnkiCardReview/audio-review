"""Where Audio Review keeps its files, and the pairing with the phone.

Standard library only, so both Anki and the helper can use it.

Everything lives in one folder, `CarReview` in your home folder (set CAR_REVIEW_HOME to use
another one, e.g. for testing). Deleting that folder removes Audio Review's voice, audio and
pairing completely; your Anki collection is never stored there.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from pathlib import Path

from .pairing import Pairing

HOME = Path(os.environ.get("CAR_REVIEW_HOME") or Path.home() / "CarReview")
CACHE = HOME / "audio-cache"         # voiced clips, kept permanently
STATUS = HOME / "status.json"        # the helper's last progress report
PAIRING = HOME / "pairing.json"      # the secret shared with the phone
INBOX = HOME / "inbox"               # decrypted grade files waiting to be applied
PACK = HOME / "outbox" / "pack.json"  # the latest audio list, for the helper to send
VENV = HOME / "venv"                 # the helper's own Python (made by voice setup)
VOICE_DIR = HOME / "voice"           # the voice model files

# CAR_REVIEW_RELAY points tests at a local `wrangler dev` relay.
RELAY = os.environ.get("CAR_REVIEW_RELAY") or "https://car-review-relay.ankicardreview.workers.dev/v1"
APP_URL = "https://ankicardreview.github.io/audio-review/"


def load_pairing(create: bool = True) -> Pairing:
    if PAIRING.exists():
        return Pairing.from_code(json.loads(PAIRING.read_text())["code"])
    if not create:
        raise SystemExit("not paired yet")
    pairing = Pairing.new()
    HOME.mkdir(parents=True, exist_ok=True)
    PAIRING.write_text(json.dumps({"code": pairing.code, "created": int(time.time())}))
    return pairing


def pairing_link(pairing: Pairing) -> str:
    # The secret goes after "#", which browsers never send to any server.
    return f"{APP_URL}#pair={pairing.code}"


# What the last send assumed: its fingerprints, and the phone's last list of clips (helper.py).
LIST_SENT = HOME / "list-sent.json"
HAVE_CACHE = HOME / "have.json"
# What the mailbox looked like the last time this computer looked (a send or a check for phone
# answers), for the bar on Anki's main screen. Never fetched on its own: no extra requests.
PHONE = HOME / "phone.json"


def note_phone(files: dict, uploaded_files: int = 0, uploaded_bytes: int = 0) -> None:
    """Record from one mailbox listing (name -> {size, updated}): audio the phone hasn't
    downloaded yet, its phone answers waiting here, and when it last reported its clips."""
    try:
        audio = [f for n, f in files.items() if n.startswith("audio/")]
        grades = [f for n, f in files.items() if n.startswith("grades/")]
        have = files.get("have") or {}
        HOME.mkdir(parents=True, exist_ok=True)
        PHONE.write_text(json.dumps({
            "checked": int(time.time()),
            "waiting": len(audio) + uploaded_files,
            "waiting_bytes": sum(f.get("size", 0) for f in audio) + uploaded_bytes,
            "grades": len(grades),
            "grades_at": max((f.get("updated", 0) for f in grades), default=0) // 1000,
            "have_at": (have.get("updated") or 0) // 1000,
        }))
    except (OSError, TypeError, ValueError):
        pass


def forget_what_phone_has() -> None:
    """A phone (re)pairing starts with no audio: make the next send check and send what's missing,
    instead of skipping because nothing changed on this computer."""
    for path in (LIST_SENT, HAVE_CACHE, PHONE):
        path.unlink(missing_ok=True)


def voice_options() -> dict:
    """How to run the voice, from Audio Review's Settings in Anki (saved in morning.json for the
    helper): processor threads (0: the gentle default) and whether to use the graphics card."""
    try:
        saved = json.loads((HOME / "morning.json").read_text())
    except (OSError, ValueError):
        saved = {}
    return {"threads": int(saved.get("voice_threads") or 0), "gpu": bool(saved.get("voice_gpu"))}


# This computer's measured voicing speed, for time estimates (written as clips are made).
VOICE_SPEED = HOME / "voice-speed.json"


def voice_speed() -> float | None:
    """Average seconds per clip on this computer, or None before any audio has been made."""
    try:
        data = json.loads(VOICE_SPEED.read_text())
        return data["secs"] / data["clips"] if data.get("clips", 0) >= 5 else None
    except (OSError, ValueError, KeyError, ZeroDivisionError):
        return None


def pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = ctypes.c_void_p
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        k32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
        k32.CloseHandle(ctypes.c_void_p(handle))
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
