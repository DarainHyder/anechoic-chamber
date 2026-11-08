"""Shared audio helpers: loading, resampling, levels and ffmpeg discovery."""

from __future__ import annotations

import os
import shutil
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf
from numpy.typing import NDArray
from scipy.signal import resample_poly

SAMPLE_RATE = 16_000
FRAME_SECONDS = 0.01
FRAME = int(SAMPLE_RATE * FRAME_SECONDS)  # 160 samples = 10 ms
EPS = 1e-12

Audio = NDArray[np.float32]


def to_mono(audio: NDArray[np.floating]) -> Audio:
    """Average channels into one float32 channel."""
    data = np.asarray(audio, dtype=np.float32)
    return data.mean(axis=1, dtype=np.float32) if data.ndim == 2 else data


def resample(audio: Audio, source_rate: int, target_rate: int = SAMPLE_RATE) -> Audio:
    """Resample with a polyphase filter; returns the input unchanged if rates match."""
    if source_rate == target_rate:
        return audio.astype(np.float32, copy=False)
    ratio = Fraction(target_rate, source_rate).limit_denominator(1000)
    out = resample_poly(audio, ratio.numerator, ratio.denominator)
    return np.asarray(out, dtype=np.float32)


def load(path: Path | str, target_rate: int = SAMPLE_RATE) -> Audio:
    """Read any file libsndfile supports as mono float32 at the target rate."""
    data, rate = sf.read(str(path), dtype="float32", always_2d=False)
    return resample(to_mono(data), int(rate), target_rate)


def save(path: Path | str, audio: Audio, rate: int = SAMPLE_RATE) -> None:
    """Write 16-bit PCM WAV, creating parent folders."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.clip(audio, -1.0, 1.0), rate, subtype="PCM_16")


def power(audio: NDArray[np.floating]) -> float:
    return float(np.mean(np.square(audio, dtype=np.float64))) if audio.size else 0.0


def db(value: float) -> float:
    """Power ratio in decibels, with a floor so silence is finite."""
    return float(10.0 * np.log10(max(value, EPS)))


def rms_db(audio: NDArray[np.floating]) -> float:
    return db(power(audio))


def frame_powers(audio: NDArray[np.floating], frame: int = FRAME) -> NDArray[np.float64]:
    """Mean power of each full or partial frame."""
    count = int(np.ceil(len(audio) / frame)) if len(audio) else 0
    padded = np.zeros(count * frame, dtype=np.float64)
    padded[: len(audio)] = audio
    return np.asarray(np.square(padded).reshape(count, frame).mean(axis=1), dtype=np.float64)


def find_ffmpeg() -> str | None:
    """Return the ffmpeg path from FFMPEG_BINARY or PATH, or None."""
    configured = os.environ.get("FFMPEG_BINARY")
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("ffmpeg")
