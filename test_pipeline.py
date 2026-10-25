"""End-to-end pipeline test on a synthetic wav: STT -> Haiku cleanup.

Usage: python test_pipeline.py [model_path]
"""

import sys
import time
import wave

import numpy as np

import cleanup
import config

if len(sys.argv) > 1:
    config.WHISPER_MODEL_PATH = sys.argv[1]

import transcribe  # noqa: E402  (reads config at class init)


def load_wav(path):
    with wave.open(path, "rb") as w:
        assert w.getframerate() == config.SAMPLE_RATE, w.getframerate()
        assert w.getnchannels() == 1
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def main():
    cleanup.require_api_key()
    samples = load_wav("test.wav")
    print(f"audio: {len(samples)/config.SAMPLE_RATE:.1f}s")

    t0 = time.perf_counter()
    transcriber = transcribe.Transcriber()
    load_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    transcript = transcriber.transcribe(samples)
    stt_s = time.perf_counter() - t0
    print(f"model load: {load_s:.2f}s | transcription: {stt_s:.2f}s")
    print(f"RAW: {transcript}")

    t0 = time.perf_counter()
    cleaned = cleanup.Cleaner().clean(transcript)
    llm_s = time.perf_counter() - t0
    print(f"cleanup: {llm_s:.2f}s")
    print(f"CLEAN: {cleaned}")


if __name__ == "__main__":
    main()
