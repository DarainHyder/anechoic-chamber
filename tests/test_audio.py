"""Shared audio helpers, and that the audio tools are installed."""

import os
from pathlib import Path

import numpy as np
import pytest

from synth import audio

IN_CI = os.environ.get("CI") == "true"


def test_libraries_import() -> None:
    from importlib.metadata import version

    import soundfile

    assert soundfile.__libsndfile_version__
    for package in ("matplotlib", "numpy", "pyloudnorm", "scipy", "soundfile"):
        assert version(package)


def test_ffmpeg_is_available_in_ci() -> None:
    if not IN_CI and audio.find_ffmpeg() is None:
        pytest.skip("ffmpeg not installed locally; CI and Kaggle have it")
    assert audio.find_ffmpeg() is not None


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    tone = (0.5 * np.sin(2 * np.pi * 440 * np.arange(16000) / 16000)).astype(np.float32)
    audio.save(tmp_path / "tone.wav", tone)
    loaded = audio.load(tmp_path / "tone.wav")
    assert loaded.shape == tone.shape
    assert np.max(np.abs(loaded - tone)) < 1e-3


def test_load_resamples_and_downmixes(tmp_path: Path) -> None:
    import soundfile as sf

    stereo = np.zeros((48000, 2), dtype=np.float32)
    stereo[:, 0] = 0.2
    sf.write(str(tmp_path / "stereo.wav"), stereo, 48000)
    loaded = audio.load(tmp_path / "stereo.wav")
    assert loaded.shape == (16000,)
    assert abs(float(np.median(loaded)) - 0.1) < 1e-3


def test_levels() -> None:
    full_scale_square = np.ones(1600, dtype=np.float32)
    assert audio.rms_db(full_scale_square) == pytest.approx(0.0)
    assert audio.rms_db(0.1 * full_scale_square) == pytest.approx(-20.0)
    assert audio.rms_db(np.zeros(10, dtype=np.float32)) == pytest.approx(-120.0)


def test_frame_powers_cover_partial_frames() -> None:
    signal = np.ones(170, dtype=np.float32)
    powers = audio.frame_powers(signal)
    assert powers.shape == (2,)
    assert powers[0] == pytest.approx(1.0)
    assert powers[1] == pytest.approx(10 / 160)
