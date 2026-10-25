"""Local speech-to-text via whisper.cpp (pywhispercpp bindings)."""

import numpy as np
from pywhispercpp.model import Model

import config

_JUNK_MARKERS = {"[BLANK_AUDIO]", "[NO_SPEECH]", "(silence)", "[SILENCE]", "[MUSIC]"}


class Transcriber:
    def __init__(self):
        self._model = Model(
            config.WHISPER_MODEL_PATH,
            n_threads=config.WHISPER_THREADS,
            print_progress=False,
            print_realtime=False,
        )

    def transcribe(self, samples: np.ndarray) -> str:
        if samples.size < config.SAMPLE_RATE // 10:  # under 100ms of audio
            return ""
        segments = self._model.transcribe(samples)
        parts = []
        for seg in segments:
            text = seg.text.strip()
            if text and text not in _JUNK_MARKERS:
                parts.append(text)
        return " ".join(parts).strip()
