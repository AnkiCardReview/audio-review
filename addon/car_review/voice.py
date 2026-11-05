"""The Kokoro "Heart" voice, used by the helper to make audio clips.

Two engines give the same voice, so clips made by either are interchangeable (the audio cache
is keyed by the spoken text and voice, not by engine):

- "onnx": kokoro-onnx on ONNX Runtime with misaki's pronunciation rules. This is what voice
  setup installs: about a third of the size of the PyTorch version and no slower on a laptop
  processor. Model files live in CarReview/voice.
- "torch": the original PyTorch `kokoro` package, kept for computers set up by hand before
  voice setup existed.

The engine is picked automatically: ONNX when its files are there, otherwise PyTorch.
"""

from __future__ import annotations

import json
import os
import re
import time

from .common import HOME, VOICE_DIR, voice_options

RATE = 24000
VOICE = "af_heart"
GENTLE_THREADS = 3  # the default: leaves the rest of the processor free while studying
# Graphics-card engines the voice runs on. DirectML (onnxruntime-directml, Windows) can't: it
# fails on the model's ConvTranspose layer (tested 2026-11-05, fp16, fp16-gpu and fp32 models).
# CUDA (onnxruntime-gpu, NVIDIA) should; not installed by voice setup yet.
GPU_PROVIDERS = ("CUDAExecutionProvider",)
DEVICE_FILE = HOME / "voice-device.json"  # what the voice last ran on, for Settings to show


def threads() -> int:
    """Processor threads for making audio: the Settings choice, up to every core."""
    cores = os.cpu_count() or 4
    return max(1, min(cores, voice_options()["threads"] or GENTLE_THREADS))
MODEL_FILE = "kokoro-v1.0.fp16.onnx"
VOICES_FILE = "voices-v1.0.bin"


def available_engine() -> str | None:
    """Which engine this Python can run, without loading it."""
    import importlib.util

    if importlib.util.find_spec("kokoro_onnx") and (VOICE_DIR / MODEL_FILE).exists() and (VOICE_DIR / VOICES_FILE).exists():
        return "onnx"
    if importlib.util.find_spec("kokoro"):
        return "torch"
    return None


class Voice:
    """Kokoro Heart, loaded on first use."""

    def __init__(self, gpu: bool | None = None) -> None:
        self.engine = available_engine()
        self._speak = None
        self.gpu = voice_options()["gpu"] if gpu is None else gpu
        self.device = "processor"

    @property
    def label(self) -> str:
        """'onnx on the graphics card' or 'onnx on 3 processor threads' (speeds are kept per label)."""
        on = "the graphics card" if self.device == "graphics card" else f"{threads()} processor threads"
        return f"{self.engine} on {on}"

    @property
    def loaded(self) -> bool:
        return self._speak is not None

    def load(self) -> None:
        if self.engine == "onnx":
            self._speak, self.device = _onnx_engine(self.gpu)
        elif self.engine == "torch":
            self._speak = _torch_engine()
        else:
            raise RuntimeError("The voice isn't set up on this computer yet (Tools ▸ Car Review ▸ Settings ▸ Voice).")

    def samples(self, text: str):
        """The spoken text as float samples at 24 kHz."""
        import numpy as np

        if self._speak is None:
            self.load()
        chunks = self._speak(text)
        return np.concatenate(chunks) if chunks else np.zeros(RATE // 10, dtype=np.float32)

    def mp3(self, text: str) -> bytes:
        import lameenc
        import numpy as np

        audio = self.samples(text)
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
        enc = lameenc.Encoder()
        enc.set_bit_rate(48)
        enc.set_in_sample_rate(RATE)
        enc.set_channels(1)
        enc.set_quality(2)
        return enc.encode(pcm) + enc.flush()


def _torch_engine():
    import torch
    from kokoro import KPipeline

    torch.set_num_threads(threads())
    pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    return lambda text: [a.numpy() for _, _, a in pipeline(text, voice=VOICE, speed=1.0)]


def _onnx_engine(gpu: bool = False):
    """(speak, device). With gpu, tries the graphics card first and checks it can really make a
    clip; if not (no such engine, an old card, a driver problem), the processor is used."""
    import numpy as np
    import onnxruntime as ort
    from kokoro_onnx import Kokoro
    from misaki import en, espeak

    # The same pronunciation rules (and settings) as the PyTorch pipeline for American English.
    g2p = en.G2P(trf=False, british=False, fallback=espeak.EspeakFallback(british=False), unk="")

    def model_on(provider: str):
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads()
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(VOICE_DIR / MODEL_FILE), options, providers=[provider, "CPUExecutionProvider"])
        return Kokoro.from_session(session, str(VOICE_DIR / VOICES_FILE))

    model, device, provider, note = None, "processor", None, ""
    if gpu:
        provider = next((p for p in GPU_PROVIDERS if p in ort.get_available_providers()), None)
        if provider is None:
            note = "no graphics-card engine installed"
        else:
            try:
                model = model_on(provider)
                model.create(g2p("Ready.")[0], voice=VOICE, speed=1.0, is_phonemes=True)  # can it really?
                device = "graphics card"
            except Exception as err:  # noqa: BLE001 - any failure: use the processor instead
                model, note = None, f"the graphics card couldn't run the voice ({str(err)[:160]})"
    if model is None:
        model = model_on("CPUExecutionProvider")
    try:
        DEVICE_FILE.write_text(json.dumps({"device": device, "provider": provider if device != "processor" else None,
                                           "note": note, "threads": threads(), "at": int(time.time())}))
    except OSError:
        pass

    def speak(text: str):
        out = []
        # Like the PyTorch pipeline: each line is said on its own, which gives a short pause.
        for line in re.split(r"\n+", text.strip()):
            if not line.strip():
                continue
            phonemes, _ = g2p(line)
            if phonemes:
                audio, _ = model.create(phonemes, voice=VOICE, speed=1.0, is_phonemes=True)
                out.append(np.asarray(audio, dtype=np.float32))
        return out

    return speak, device
