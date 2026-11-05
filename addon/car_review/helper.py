"""Car Review background helper: makes missing audio, encrypts, and uploads the car list.

Runs in the Car Review Python environment (it needs the Kokoro voice and `cryptography`),
started by the add-on so it can keep going after Anki closes:

    python -m car_review.helper send   --pack pack.json
    python -m car_review.helper overnight   # after closing Anki: wait for the next day's list
    python -m car_review.helper status

Audio is cached on this computer by fingerprint, so each clip is only ever made once. Only
clips the phone doesn't have yet are uploaded (the phone lists what it holds in "have"), packed
into a few bundle files that the phone deletes once it has them. The phone gets a partial list
every 25 cards, so on a big first run it can start with the cards that are already ready.
Progress is written to status.json for the add-on to show.
"""

from __future__ import annotations

import argparse
import ctypes
import gzip
import hashlib
import json
import os
import secrets
import sys
import time
import traceback
from pathlib import Path

import requests

from .common import (CACHE, HAVE_CACHE, HOME, INBOX, LIST_SENT, PACK, PAIRING, PHONE, RELAY, STATUS, VOICE_SPEED, note_phone, pid_alive,
                     forget_what_phone_has, load_pairing, pairing_link)
from .pairing import Pairing
from .power import on_charger
from .ui import Progress, Stopped, run_with_window
from .voice import Voice, available_engine

BATCH = 25
BUNDLE_BYTES = 1_800_000          # one relay file (the relay's limit is 1.9 MB)
BUNDLES = HOME / "bundles.json"   # bundle name -> clip names, for bundles the phone hasn't fetched
MAILBOX_BUDGET = 80_000_000       # audio waiting for the phone, at most (the relay allows 100 MB)
RESEND_AFTER = 36 * 3600          # the relay deletes files after 3 days: refresh an unchanged list before
# Clips stay in the cache for good: they're small next to a deck's media, and a card that comes
# back never needs voicing again.


def write_status(**fields) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    fields["updated"] = int(time.time())
    STATUS.write_text(json.dumps(fields))


_caffeinate = None


def keep_awake(on: bool) -> None:
    """Ask the computer not to sleep while working (closing the lid still sleeps)."""
    global _caffeinate
    if sys.platform == "win32":
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
    elif sys.platform == "darwin":
        import os
        import subprocess

        if on and _caffeinate is None:
            # Stays awake while this process runs, and stops by itself if it ends.
            _caffeinate = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        elif not on and _caffeinate is not None:
            _caffeinate.terminate()
            _caffeinate = None


def be_gentle() -> None:
    """Run at low priority (and the voice on 3 cores), so studying and anything else stay smooth."""
    if sys.platform == "win32":
        BELOW_NORMAL_PRIORITY_CLASS = 0x4000
        k32 = ctypes.windll.kernel32
        # Handles are pointer-sized: without these types the 64-bit handle gets truncated.
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
    else:
        import os

        os.nice(10)


def wait_for_charger(progress: Progress | None = None, **status) -> None:
    """Pause while on battery; carry on when plugged back in."""
    if on_charger():
        return
    keep_awake(False)  # let the laptop sleep normally while unplugged
    write_status(state="paused (on battery)", **status)
    if progress:
        progress.note = "Paused: the laptop is on battery. Plug it in to continue."
        progress.event("On battery: paused until you plug in.", "warn")
    while not on_charger() and not (progress and progress.stopped):
        time.sleep(1)
    if progress:
        progress.note = ""
        if not progress.stopped:
            progress.event("Plugged in: carrying on.")
    keep_awake(True)


def make_clip(voice: Voice, text: str, progress: Progress) -> bytes:
    """One clip as mp3, loading the voice first if needed. Raises Stopped as soon as Stop is
    pressed, without waiting for the clip (or the voice) to finish."""
    if not voice.loaded:
        progress.phase = "Loading the voice…"
        progress.event("Loading the voice (on a slow laptop this takes about a minute).", "quiet")
        started = time.time()
        progress.run(voice.load)
        progress.phase = ""
        progress.event(f"Voice ready ({voice.label}, {time.time() - started:.0f} s).")
    started = time.time()
    clip = progress.run(voice.mp3, text)
    note_speed(time.time() - started, voice.label)
    return clip


def note_speed(secs: float, engine: str) -> None:
    """Add one clip's time to this computer's measured speed (for the estimates in Anki). The
    recent clips count most, so a new computer or engine settles in after a few dozen clips."""
    try:
        data = json.loads(VOICE_SPEED.read_text())
    except (OSError, ValueError):
        data = {}
    if data.get("engine") != engine:
        data = {"engine": engine, "secs": 0.0, "clips": 0}
    keep = min(1.0, 199 / max(1, data["clips"]))  # about the last 200 clips
    data["secs"] = data["secs"] * keep + secs
    data["clips"] = data["clips"] * keep + 1
    try:
        VOICE_SPEED.write_text(json.dumps(data))
    except OSError:
        pass


def snippet(text: str, n: int = 48) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


class Relay:
    def __init__(self, pairing: Pairing) -> None:
        self.p = pairing
        self.box = f"{RELAY}/{pairing.box_id}"
        self.session = requests.Session()
        self.session.headers["X-Write-Key"] = pairing.write_key

    def _retry(self, fn):
        for attempt in range(6):
            try:
                r = fn()
                if r.status_code < 500:
                    return r
            except requests.RequestException:
                pass
            time.sleep(min(60, 2 ** attempt))
        raise RuntimeError("relay unreachable")

    def files(self, prefix: str = "") -> dict[str, dict]:
        """The mailbox's files (name -> size, updated), in one request."""
        r = self._retry(lambda: self.session.get(self.box, params={"prefix": prefix}, timeout=60))
        return {f["name"]: f for f in r.json().get("files", [])} if r.ok else {}

    def names(self, prefix: str) -> set[str]:
        return set(self.files(prefix))

    def put(self, name: str, data: bytes) -> int:
        """Encrypt and upload a file; returns its size as stored."""
        blob = self.p.encrypt(name, data)
        r = self._retry(lambda: self.session.put(f"{self.box}/{name}", data=blob, timeout=120))
        if r.status_code == 413 and "full" in r.text:
            raise MailboxFull(name)
        if not r.ok:
            raise RuntimeError(f"upload of {name} failed: {r.status_code} {r.text[:200]}")
        return len(blob)

    def get(self, name: str) -> bytes | None:
        r = self._retry(lambda: self.session.get(f"{self.box}/{name}", timeout=60))
        return self.p.decrypt(name, r.content) if r.ok else None


class MailboxFull(RuntimeError):
    """The relay holds as much of this user's data as it allows; more goes once the phone fetches."""


def read_json(data: bytes):
    """A JSON file from the relay, gzipped or not."""
    return json.loads(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def pack_bundle(clips: list[tuple[str, bytes]]) -> bytes:
    """Many clips in one file: b"CRB1", a 4-byte header length, the JSON header
    [[name, size], ...], then the clips back to back."""
    header = json.dumps([[n, len(d)] for n, d in clips], separators=(",", ":")).encode()
    return b"CRB1" + len(header).to_bytes(4, "big") + header + b"".join(d for _, d in clips)


class Outbox:
    """Gets clips to the phone: only the ones it doesn't hold yet, in as few uploads as possible.
    The phone uploads "have" (the clips it holds) when it syncs, and deletes each bundle once its
    clips are stored, so a bundle still in the mailbox is one the phone hasn't fetched yet. If the
    phone loses its audio, "have" shrinks and the missing clips are simply sent again."""

    def __init__(self, relay: Relay, progress: Progress | None = None) -> None:
        self.relay = relay
        self.progress = progress
        # One request for everything in the mailbox; "have" is downloaded only if the phone has
        # uploaded a new one since the last time.
        files = relay.files()
        self.listing = files  # for note_phone once the send is done
        cached = read_file_json(HAVE_CACHE)
        have = files.get("have")
        if have and cached.get("updated") == have["updated"]:
            self.have = set(cached.get("clips", []))
        else:
            try:
                data = relay.get("have") if have else None
                self.have = set(read_json(data)["clips"]) if data else set()
            except (ValueError, KeyError, OSError):
                self.have = set()
            if have:
                HAVE_CACHE.write_text(json.dumps({"updated": have["updated"], "clips": sorted(self.have)}))
        try:
            known = json.loads(BUNDLES.read_text())
        except (OSError, ValueError):
            known = {}
        self.bundles = {b: clips for b, clips in known.items() if b in files}
        self.sizes = {b: files[b]["size"] for b in self.bundles}
        # Audio already waiting for the phone (any bundle, known here or not) counts toward the budget.
        self.waiting = sum(f["size"] for n, f in files.items() if n.startswith("audio/"))
        self.uploaded_bytes = 0
        self.full = False
        self.coming = {n for clips in self.bundles.values() for n in clips}
        self.pending: list[tuple[str, bytes]] = []
        self.pending_names: set[str] = set()
        self.size = 0
        self.uploads = 0
        self._save()

    def reachable(self, name: str) -> bool:
        return name in self.have or name in self.coming

    def add(self, name: str, path: Path) -> bool:
        """Queue a clip for the phone. False when the mailbox already holds as much audio as it
        should: the phone fetches that first, and the rest goes at a later send (nearest due first)."""
        if self.reachable(name) or name in self.pending_names:
            return True
        data = path.read_bytes()
        if self.full or self.waiting + self.size + len(data) > MAILBOX_BUDGET:
            self.full = True
            return False
        if self.pending and self.size + len(data) > BUNDLE_BYTES:
            self.flush()
            if self.full:
                return False
        self.pending.append((name, data))
        self.pending_names.add(name)
        self.size += len(data)
        return True

    def flush(self) -> None:
        if not self.pending:
            return
        name = "audio/b-" + secrets.token_hex(8)
        try:
            stored = self.relay.put(name, pack_bundle(self.pending))
        except MailboxFull:
            self.full = True  # these clips go at a later send, once the phone has fetched
            self.pending, self.pending_names, self.size = [], set(), 0
            return
        self.bundles[name] = [n for n, _ in self.pending]
        self.sizes[name] = stored  # as the mailbox lists it, so the phone list doesn't change
        self.waiting += stored
        self.uploaded_bytes += stored
        self.coming |= self.pending_names
        self.uploads += 1
        if self.progress:
            self.progress.stats["uploads"] = self.uploads
            self.progress.event(f"Uploaded {len(self.pending):,} clips in one file ({self.size / 1e6:.1f} MB).",
                                to_log=False)
        self.pending, self.pending_names, self.size = [], set(), 0
        self._save()

    def _save(self) -> None:
        HOME.mkdir(parents=True, exist_ok=True)
        BUNDLES.write_text(json.dumps(self.bundles))


def phone_list(pack: dict, cards: list[dict], pairing: Pairing, pending: int, unvoiced: int = 0,
               bundles: dict[str, int] | None = None, nxt: dict | None = None, ready_next: set | None = None) -> dict:
    """The list the phone downloads (gzipped): clips named by their relay name, plus the bundles
    to fetch them from, and the next day's list (nxt) for the phone to switch to at the rollover."""
    ready_next = ready_next or set()
    bundles = bundles or {}
    out = dict(pack, cards=[], pending=pending, unvoiced=unvoiced, bundles=sorted(bundles), bundle_bytes=bundles)
    # Cards not on the phone yet still count as siblings for the phone's fallback: [note, day].
    sent = {c["cid"] for c in cards}
    out["held_back"] = [[c["nid"], c["due_day"]] for c in pack["cards"] if c["cid"] not in sent]
    for c in cards:
        c = dict(c)
        c["q_audio"] = pairing.audio_name(c["q_audio"])
        c["a_audio"] = pairing.audio_name(c["a_audio"])
        out["cards"].append(c)
    if pack.get("announce"):
        rename = lambda a: dict(a, audio=pairing.audio_name(a["audio"]))  # noqa: E731
        out["announce"] = {"blocks": [rename(a) for a in pack["announce"]["blocks"]],
                           "end": rename(pack["announce"]["end"])}
    out.pop("next", None)
    out.pop("voice_missing", None)
    if nxt:
        # The next day's list. A card this list already has (with the same audio) only carries
        # what changes ("same": the phone fills in the rest); the others come whole. Cards whose
        # audio isn't on the phone yet are left out, as in the list itself.
        here = {c["cid"]: c for c in cards}
        entries = []
        for c in nxt["cards"]:
            mine = here.get(c["cid"])
            if mine and (mine["q_audio"], mine["a_audio"]) == (c["q_audio"], c["a_audio"]):
                entries.append({k: c[k] for k in NEXT_DAY_FIELDS if k in c} | {"same": 1})
            elif c["cid"] in ready_next:
                entries.append(dict(c, q_audio=pairing.audio_name(c["q_audio"]), a_audio=pairing.audio_name(c["a_audio"])))
        out["next"] = {k: nxt[k] for k in ("anki_today", "next_day_at", "review_limits", "learn_ahead_secs", "made_at")}
        out["next"]["cards"] = entries
    return out


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def list_fingerprint(phone: dict) -> str:
    """The phone list without when it was made, and with cards in a fixed order: Anki's order
    drifts a little during the day, which isn't worth an upload."""
    by_cid = lambda cards: sorted(cards, key=lambda c: c["cid"])  # noqa: E731
    same = dict(phone, made_at=None, cards=by_cid(phone["cards"]))
    if phone.get("next"):
        same["next"] = dict(phone["next"], made_at=None, cards=by_cid(phone["next"]["cards"]))
    return fingerprint(same)


def pack_fingerprint(pack: dict, nxt: dict | None) -> str:
    """The same for what Anki handed over (before any audio or mailbox work)."""
    by_cid = lambda cards: sorted(cards, key=lambda c: c["cid"])  # noqa: E731
    return fingerprint({"pack": dict(pack, made_at=None, voice_missing=None, cards=by_cid(pack["cards"])),
                        "next": dict(nxt, made_at=None, cards=by_cid(nxt["cards"])) if nxt else None})


def read_file_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


# What can differ between a card in today's list and the same card in the next day's list.
NEXT_DAY_FIELDS = ("cid", "kind", "block", "deck", "due_day", "due_at", "again_secs", "good_secs", "learn_steps",
                   "relearn_steps", "remaining_steps", "is_relearning")


def announce_clips(pack: dict) -> list[dict]:
    """The spoken cues in a list: "<deck> done." per block and "All decks done."."""
    a = pack.get("announce") or {}
    return [*a.get("blocks", []), *([a["end"]] if a.get("end") else [])]


LOCK = HOME / "helper.lock"
LAST_SENT = HOME / "last-sent.json"  # the Anki day of the last list that reached the phone


def take_lock(lock: Path = LOCK) -> bool:
    """Only one send runs at a time. A later request just leaves a newer pack for it to pick up."""
    import os

    if lock.exists():
        try:
            if pid_alive(int(lock.read_text())):
                return False
        except ValueError:
            pass
    lock.write_text(str(os.getpid()))
    return True


def log(text: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}", flush=True)


def next_day(pack: dict) -> dict | None:
    """The next Anki day's list, made now from Anki's own scheduler on a copy of the collection
    (morning.py), for the phone to switch to when Anki's day changes. Only that day's cards."""
    from . import morning

    started = time.time()
    try:
        nxt = morning.build_next_day_pack()
    except Exception as err:  # the phone then falls back to this list's reviews
        log(f"next day's list: not made ({err})")
        return None
    if nxt["anki_today"] != pack["anki_today"] + 1:
        log(f"next day's list: skipped (it's for day {nxt['anki_today']}, the list is for day {pack['anki_today']})")
        return None
    nxt["cards"] = [c for c in nxt["cards"] if c["due_day"] <= nxt["anki_today"]]
    log(f"next day's list: {len(nxt['cards'])} cards for day {nxt['anki_today']} ({time.time() - started:.0f} s)")
    return nxt


def send(pack_path: Path, progress: Progress) -> None:
    """Upload the car list. Voices missing cards first if the pack asks for it (and only while
    plugged in); otherwise sends just the cards that already have audio. If a newer pack is
    saved while this runs, it switches to the newer one."""
    if not PAIRING.exists():
        # No phone paired with this computer (yet): there's nobody to send to, so only make the
        # audio if asked (it's kept for when a phone is paired), instead of filling a new mailbox.
        if json.loads(pack_path.read_text(encoding="utf-8")).get("voice_missing"):
            prepare(pack_path, progress)
        else:
            progress.auto_close = True
            progress.finish("No phone is paired with this computer, so nothing was sent "
                            "(Tools ▸ Car Review ▸ Pair phone).")
        return
    if not take_lock():
        progress.finish("Another Car Review send is already running; it will pick up this newer list.")
        return
    pairing = load_pairing()
    relay = Relay(pairing)
    voice = Voice()
    CACHE.mkdir(parents=True, exist_ok=True)
    be_gentle()
    keep_awake(True)
    started = time.time()
    made = 0
    voicing = False
    try:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        loaded_at = pack_path.stat().st_mtime
        # The next day's list, so the phone has it in the morning without this computer on.
        progress.phase = "Making tomorrow's list from Anki's scheduler…"
        nxt = next_day(pack)
        progress.phase = ""
        sent = read_file_json(LIST_SENT)
        if (sent.get("pack") == pack_fingerprint(pack, nxt) and sent.get("complete")
                and time.time() - sent.get("list_at", 0) < RESEND_AFTER):
            # Nothing changed since the last send, and the phone got all of it: no requests at all.
            log("unchanged since the last send: nothing sent")
            write_status(**dict(read_file_json(STATUS), state="done", unchanged=True))
            progress.auto_close = True
            progress.finish("Nothing changed since the last send, so there was nothing to send. Done ✓")
            return
        progress.phase = "Checking what your phone already has…"
        outbox = Outbox(relay, progress)
        progress.phase = ""
        progress.event(f"Your phone has {len(outbox.have):,} clips"
                       + (f"; {len(outbox.bundles):,} audio files are waiting for it in the mailbox." if outbox.bundles
                          else "."), to_log=False)
        names: dict[str, str] = {}

        def relay_name(fp: str) -> str:
            if fp not in names:
                names[fp] = pairing.audio_name(fp)
            return names[fp]

        def put_list(pack: dict, ready: list[dict], **counts) -> None:
            outbox.flush()  # the list only names clips the phone can already get
            ready_next = {c["cid"] for c in ready if c.get("next_only")}
            ready = [c for c in ready if not c.get("next_only")]
            phone = phone_list(pack, ready, pairing, bundles={b: outbox.sizes.get(b, 0) for b in outbox.bundles},
                               nxt=nxt, ready_next=ready_next, **counts)
            progress.stats["ready"] = len(ready)
            fp = list_fingerprint(phone)
            sent = read_file_json(LIST_SENT)
            if fp == sent.get("list") and time.time() - sent.get("list_at", 0) < RESEND_AFTER:
                progress.event(f"Phone list unchanged ({len(ready):,} cards ready): not sent again.", "ok", to_log=False)
                return
            relay.put("list", gzip.compress(json.dumps(phone, separators=(",", ":")).encode(), mtime=0))
            LIST_SENT.write_text(json.dumps(dict(sent, list=fp, list_at=int(time.time()), complete=False)))
            progress.event(f"Phone list updated: {len(ready):,} of {len(pack['cards']):,} cards ready.",
                           "ok", to_log=False)

        first = True
        while True:
            if not first:
                loaded_at = pack_path.stat().st_mtime
                pack = json.loads(pack_path.read_text(encoding="utf-8"))
                nxt = next_day(pack)
            first = False
            # The next day's cards that this list doesn't have (or has with other audio) get audio too.
            here = {c["cid"]: (c["q_audio"], c["a_audio"]) for c in pack["cards"]}
            extra = [dict(c, next_only=1) for c in (nxt["cards"] if nxt else [])
                     if here.get(c["cid"]) != (c["q_audio"], c["a_audio"])]
            cards = pack["cards"] + extra
            # Once asked to make audio (Prepare audio), a newer quick list (closing Anki) keeps it going.
            voicing = voicing or pack.get("voice_missing", True)
            progress.title = "Car Review: making audio and sending" if voicing else "Car Review: sending to your car"

            # The few spoken cues first: made when voicing, sent whenever they're ready.
            for cue in announce_clips(pack):
                path = CACHE / f"{cue['audio']}.mp3"
                if not path.exists() and voicing and on_charger() and not progress.stopped:
                    try:
                        path.write_bytes(make_clip(voice, cue["text"], progress))
                    except Stopped:
                        continue
                    made += 1
                    progress.stats["made"] = made
                if path.exists():
                    outbox.add(relay_name(cue["audio"]), path)

            def clips(card: dict) -> tuple:
                return (card["q_audio"], card["question"]), (card["a_audio"], card["answer"])

            def cached(card: dict) -> bool:
                return all((CACHE / f"{fp}.mp3").exists() for fp, _ in clips(card))

            def reachable(card: dict) -> bool:
                return all(outbox.reachable(relay_name(fp)) for fp, _ in clips(card))

            # Cards the phone can already play go in every list sent from here on, so a partial
            # list or a Stop never leaves the phone with fewer cards than it had.
            ready_idx = {i for i, c in enumerate(cards) if cached(c) and reachable(c)}
            to_voice = {i for i, c in enumerate(cards) if not cached(c)} if voicing else set()
            to_upload = {i for i, c in enumerate(cards) if i not in ready_idx and cached(c)}
            # Voice the nearest due days first; the phone list keeps Anki's play order.
            order = sorted(to_voice | to_upload, key=lambda i: (cards[i]["due_day"], i))
            # Count what takes the time: the cards needing audio, or else the cards to upload.
            progress.unit = "cards needing audio" if to_voice else "cards to upload"
            work_total, work_done = len(to_voice) or len(order), 0
            progress.step(0, work_total)
            if progress.stats["ready"] is None:
                progress.stats["ready"] = len(ready_idx)
            progress.event(f"{len(cards):,} cards in the list: {len(ready_idx):,} already on the phone"
                           + (f", {len(to_voice):,} need audio" if to_voice else "")
                           + (f", {len(to_upload):,} to upload" if to_upload else "") + ".")
            if to_voice and ready_idx:
                # Voicing takes a while: the phone gets this list's ready cards straight away.
                ready = [cards[j] for j in sorted(ready_idx)]
                put_list(pack, ready, pending=len(cards) - len(ready))
                write_status(state="sending", ready=len(ready), total=len(cards), made=made,
                             elapsed=int(time.time() - started), made_at=pack["made_at"])
            newer = False
            for i in order:
                if not progress.checkpoint():
                    break  # stopped by the user: the phone keeps every card that's ready
                if pack_path.stat().st_mtime != loaded_at:
                    newer = True
                    progress.event("Anki saved a newer list; switching to it (audio made so far is kept).")
                    break
                card_started, card_made, sent_ok = time.time(), 0, True
                try:
                    for fp, text in clips(cards[i]):
                        path = CACHE / f"{fp}.mp3"
                        if not path.exists():
                            wait_for_charger(progress, ready=len(ready_idx), total=len(cards), made=made)
                            if progress.stopped:
                                raise Stopped
                            path.write_bytes(make_clip(voice, text, progress))
                            made += 1
                            card_made += 1
                            progress.stats["made"] = made
                        sent_ok = outbox.add(relay_name(fp), path) and sent_ok
                except Stopped:
                    break  # the clip being made is dropped; the phone keeps every card that's ready
                if sent_ok:
                    ready_idx.add(i)
                elif not voicing:
                    break  # the mailbox is full and there's nothing to make: the rest goes next time
                if card_made:
                    progress.event(f"Audio made: “{snippet(cards[i]['question'])}” "
                                   f"({time.time() - card_started:.0f} s)", "quiet", to_log=False)
                if i not in to_voice and to_voice:
                    continue
                work_done += 1
                progress.step(work_done, work_total)
                if work_done % BATCH == 0 and work_done < work_total and to_voice:
                    ready = [cards[j] for j in sorted(ready_idx)]
                    put_list(pack, ready, pending=len(cards) - len(ready))
                    write_status(state="sending", ready=len(ready), total=len(cards), made=made,
                                 elapsed=int(time.time() - started), made_at=pack["made_at"])
            if newer:
                continue  # start over with the newer list; finished clips are reused
            ready = [cards[j] for j in sorted(ready_idx)]
            unvoiced = len(cards) - len(ready)
            put_list(pack, ready, pending=0, unvoiced=unvoiced)
            ready = [c for c in ready if not c.get("next_only")]
            held = len(pack["cards"]) - len(ready) if outbox.full else 0
            log(f"sent: {len(ready)} cards, {outbox.uploads} audio bundles uploaded, "
                f"{len(outbox.have)} clips already on the phone"
                + (f"; {held} cards' audio waits until the phone fetches what's in the mailbox" if held else ""))
            sent = read_file_json(LIST_SENT)
            LIST_SENT.write_text(json.dumps(dict(sent, pack=pack_fingerprint(pack, nxt),
                                                 complete=not unvoiced and not outbox.full and not progress.stopped)))
            LAST_SENT.write_text(json.dumps({"anki_today": pack["anki_today"], "made_at": pack["made_at"],
                                             "sent": int(time.time())}))
            note_phone(outbox.listing, outbox.uploads, outbox.uploaded_bytes)
            break
        state = "stopped" if progress.stopped else "done"
        write_status(state=state, ready=len(ready), total=len(pack["cards"]), made=made, unvoiced=unvoiced,
                     elapsed=int(time.time() - started), made_at=pack["made_at"])
        message = f"{len(ready):,} cards ready on your phone" + (f" ({made:,} new clips made)" if made else "") + "."
        if outbox.full:
            message += (" The rest of the audio goes once your phone has downloaded what's waiting "
                        "(open Car Review and sync), at your next sync or close of Anki.")
        elif unvoiced:
            message += (f" {unvoiced:,} cards have no audio yet: plug in and use "
                        "Tools ▸ Car Review ▸ Prepare audio.")
        progress.auto_close = True  # the result is also in Tools ▸ Car Review ▸ Status
        progress.finish(message + (" Stopped early." if progress.stopped else " Done ✓"))
    except Exception as err:
        write_status(state="error", error=str(err), detail=traceback.format_exc()[-2000:])
        progress.finish(f"Stopped by an error: {err}", failed=True)
        raise
    finally:
        keep_awake(False)
        LOCK.unlink(missing_ok=True)


def prepare(pack_path: Path, progress: Progress) -> None:
    """Make audio ahead of time (nearest due date first) without uploading anything."""
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    cards = sorted(pack["cards"], key=lambda c: c["due_day"])
    todo: dict[str, str] = {}
    for c in cards:
        for fp, text in ((c["q_audio"], c["question"]), (c["a_audio"], c["answer"])):
            if fp not in todo and not (CACHE / f"{fp}.mp3").exists():
                todo[fp] = text
    voice = Voice()
    CACHE.mkdir(parents=True, exist_ok=True)
    be_gentle()
    keep_awake(True)
    started = time.time()
    total = len(todo)
    progress.unit = "clips"
    made = 0
    try:
        progress.event(f"{len(cards):,} cards in the list; {total:,} clips still need audio.")
        for fp, text in todo.items():
            if not progress.checkpoint():
                break
            wait_for_charger(progress, made=made, total=total)
            clip_started = time.time()
            try:
                (CACHE / f"{fp}.mp3").write_bytes(make_clip(voice, text, progress))
            except Stopped:
                break  # the clip being made is dropped; the ones before it are kept
            made += 1
            progress.stats["made"] = made
            progress.event(f"Audio made: “{snippet(text)}” ({time.time() - clip_started:.0f} s)", "quiet",
                           to_log=False)
            progress.step(made, total)
            if made % 20 == 0:
                write_status(state="preparing audio ahead", made=made, total=total, cards=len(cards),
                             elapsed=int(time.time() - started))
        state = "stopped" if progress.stopped else "prepared"
        write_status(state=state, made=made, total=total, cards=len(cards), elapsed=int(time.time() - started))
        progress.finish(f"{made:,} of {total:,} clips made." + (" Stopped early; it carries on next time." if progress.stopped else " Done ✓"))
    except Exception as err:
        write_status(state="error", error=str(err), detail=traceback.format_exc()[-2000:])
        progress.finish(f"Stopped by an error: {err}", failed=True)
        raise
    finally:
        keep_awake(False)


def keep_timing(name: str, data: bytes) -> None:
    """Keep the phone's clip timings (times only, no card text) for tools/timing_report.py.
    The inbox is cleared on every fetch, so they're copied out; the last 14 days are kept."""
    try:
        timing = json.loads(data).get("timing")
    except ValueError:
        return
    if not timing:
        return
    folder = HOME / "timing"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (name.replace("/", "_") + ".json")).write_text(json.dumps(timing), encoding="utf-8")
    for old in sorted(folder.glob("*.json"), key=lambda f: f.stat().st_mtime)[:-14]:
        old.unlink()


def main() -> None:
    # Started with pythonw.exe (no console window), Python has nowhere to print; keep a log instead.
    if sys.stderr is None or sys.stdout is None:
        HOME.mkdir(parents=True, exist_ok=True)
        log = open(HOME / "helper.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
    ap = argparse.ArgumentParser(prog="car_review.helper")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send", help="make missing audio, encrypt and upload a car list")
    s.add_argument("--pack", type=Path, required=True)
    s.add_argument("--no-window", action="store_true", help="don't show the progress window")
    pr = sub.add_parser("prepare", help="make audio ahead of time for a list (no upload)")
    pr.add_argument("--pack", type=Path, required=True)
    pr.add_argument("--no-window", action="store_true", help="don't show the progress window")
    sub.add_parser("status", help="print the last progress report")
    sub.add_parser("link", help="print the phone pairing link")
    sub.add_parser("repair", help="forget the old phone: delete its box and make a new pairing")
    sub.add_parser("engine", help="print which voice engine is installed (onnx, torch or none)")
    vc = sub.add_parser("voice-check", help="make one short clip to check the voice works")
    vc.add_argument("--gpu", action="store_true", help="try the graphics card, and time a few clips")
    sub.add_parser("fetch-grades", help="download and decrypt the phone's grades into the inbox folder")
    # Retired: the 4:30 am task (its runs now just remove it) and the overnight wait.
    sub.add_parser("morning", help="(retired) removes the old 4:30 am task")
    o = sub.add_parser("overnight", help="(retired) does nothing")
    o.add_argument("--pack", type=Path, default=PACK)
    sub.add_parser("unschedule", help="remove the old 4:30 am task")
    sub.add_parser("next-day", help="print a summary of the next day's list (for checking)")
    d = sub.add_parser("delete-grades", help="delete grade files from the relay once they're applied")
    d.add_argument("names", nargs="+")
    args = ap.parse_args()
    if args.cmd in ("send", "prepare"):
        title = "Car Review: sending to your car" if args.cmd == "send" else "Car Review: making audio ahead"
        progress = Progress(title)
        work = (lambda p: send(args.pack, p)) if args.cmd == "send" else (lambda p: prepare(args.pack, p))
        if args.no_window:
            work(progress)
        else:
            run_with_window(progress, work)
        # A clip given up on by Stop may still be running on a side thread: don't wait for it.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    elif args.cmd == "status":
        print(STATUS.read_text() if STATUS.exists() else "{}")
    elif args.cmd == "link":
        forget_what_phone_has()  # a phone may be (re)pairing, with no audio yet
        print(pairing_link(load_pairing()))
    elif args.cmd == "engine":
        print(available_engine() or "none")
    elif args.cmd == "voice-check":
        voice = Voice(gpu=True if args.gpu else None)
        started = time.time()
        clip = voice.mp3("Car Review is ready. Drive safely.")
        result = {"engine": voice.engine, "device": voice.device, "bytes": len(clip), "secs": round(time.time() - started, 1)}
        if args.gpu:  # a few more clips, timed, once the voice is loaded
            started = time.time()
            for line in ("The first line treatment for absence seizures is ethosuximide.",
                         "Beta blockers lower heart rate and blood pressure.",
                         "The most common cause of community acquired pneumonia is Streptococcus pneumoniae."):
                voice.mp3(line)
            result["secs_per_clip"] = round((time.time() - started) / 3, 2)
            from .voice import DEVICE_FILE
            result["note"] = json.loads(DEVICE_FILE.read_text()).get("note", "") if DEVICE_FILE.exists() else ""
        print(json.dumps(result))
    elif args.cmd == "repair":
        if PAIRING.exists():
            old = load_pairing(create=False)
            requests.delete(f"{RELAY}/{old.box_id}", headers={"X-Write-Key": old.write_key}, timeout=60)
            PAIRING.unlink()
        load_pairing()
        print("new pairing made; scan the new QR code on your phone")
    elif args.cmd == "fetch-grades":
        relay = Relay(load_pairing(create=False))
        INBOX.mkdir(parents=True, exist_ok=True)
        for old in INBOX.glob("*.json"):
            old.unlink()
        files = relay.files()  # the whole mailbox in the same one request, for Anki's main screen
        note_phone(files)
        names = sorted(n for n in files if n.startswith("grades/"))
        for name in names:
            data = relay.get(name)
            if data is not None:
                (INBOX / (name.replace("/", "_") + ".json")).write_bytes(data)
                keep_timing(name, data)
        print(json.dumps(names))
    elif args.cmd == "delete-grades":
        relay = Relay(load_pairing(create=False))
        for name in args.names:
            relay.session.delete(f"{relay.box}/{name}", timeout=60)
        seen = read_file_json(PHONE)
        if seen:
            PHONE.write_text(json.dumps(dict(seen, grades=max(0, seen.get("grades", 0) - len(args.names)))))
    elif args.cmd == "morning":
        from . import morning

        morning.unschedule()
        log("the 4:30 am task isn't needed any more (the next day's list goes with every send): removed it")
    elif args.cmd == "overnight":
        pass
    elif args.cmd == "next-day":
        pack = json.loads(PACK.read_text(encoding="utf-8"))
        nxt = next_day(pack)
        if nxt:
            print(json.dumps({"anki_today": nxt["anki_today"], "cards": len(nxt["cards"]),
                              "kinds": {k: sum(c["kind"] == k for c in nxt["cards"]) for k in ("review", "learn", "new")}}))
    elif args.cmd == "unschedule":
        from . import morning

        morning.unschedule()


if __name__ == "__main__":
    main()
