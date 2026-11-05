"""Where Car Review keeps its files, and the pairing with the phone.

Standard library only, so both Anki and the helper can use it.

Everything lives in one folder, `CarReview` in your home folder (set CAR_REVIEW_HOME to use
another one, e.g. for testing). Deleting that folder removes Car Review's voice, audio and
pairing completely; your Anki collection is never stored there.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .pairing import Pairing

HOME = Path(os.environ.get("CAR_REVIEW_HOME") or Path.home() / "CarReview")
CACHE = HOME / "audio-cache"         # voiced clips, kept permanently
STATUS = HOME / "status.json"        # the helper's last progress report
PAIRING = HOME / "pairing.json"      # the secret shared with the phone
INBOX = HOME / "inbox"               # decrypted grade files waiting to be applied
PACK = HOME / "outbox" / "pack.json"  # the latest car list, for the helper to send
VENV = HOME / "venv"                 # the helper's own Python (made by voice setup)
VOICE_DIR = HOME / "voice"           # the voice model files

# CAR_REVIEW_RELAY points tests at a local `wrangler dev` relay.
RELAY = os.environ.get("CAR_REVIEW_RELAY") or "https://car-review-relay.ankicardreview.workers.dev/v1"
APP_URL = "https://ankicardreview.github.io/car-review/"


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


def forget_what_phone_has() -> None:
    """A phone (re)pairing starts with no audio: make the next send check and send what's missing,
    instead of skipping because nothing changed on this computer."""
    for path in (LIST_SENT, HAVE_CACHE):
        path.unlink(missing_ok=True)


def voice_options() -> dict:
    """How to run the voice, from Car Review's Settings in Anki (saved in morning.json for the
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
