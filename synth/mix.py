"""Mixture generator: speech bed plus trigger events, with room echo and compression.

Every mixture is reproducible from (seed, index), so training can mix on the fly
without storing data. The exact trigger signal is always returned alongside the
mixture, with a trigger-active label for every 10 ms.

Trigger-to-bed ratio (TBR) is measured only where the trigger is active: the
trigger's power in its active frames divided by the bed's power in those same
frames. That matches how loud a trigger sounds against what is playing under it.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pyloudnorm
from numpy.typing import NDArray
from scipy.signal import fftconvolve

from synth import audio
from synth.audio import FRAME, SAMPLE_RATE, Audio


@dataclass(frozen=True)
class MixConfig:
    seconds: float = 4.0
    event_count_probs: tuple[float, float, float] = (0.2, 0.5, 0.3)  # 0, 1 or 2 events
    tbr_db: tuple[float, float] = (-5.0, 15.0)
    event_seconds: tuple[float, float] = (0.3, 3.0)
    speakers: tuple[int, int] = (1, 2)
    second_speaker_db: tuple[float, float] = (-5.0, 5.0)
    music_prob: float = 0.4
    music_db: tuple[float, float] = (-20.0, -5.0)
    noise_prob: float = 0.5
    noise_db: tuple[float, float] = (-30.0, -10.0)
    bed_lufs: tuple[float, float] = (-32.0, -18.0)
    rir_prob: float = 0.7
    reverb_tail_seconds: float = 0.3
    codec_prob: float = 0.7
    opus_kbps: tuple[int, ...] = (16, 24, 32, 48, 64)
    aac_kbps: tuple[int, ...] = (48, 64, 96, 128)
    peak_limit: float = 0.98
    require_codec: bool = False

    @property
    def length(self) -> int:
        return int(round(self.seconds * SAMPLE_RATE))

    @property
    def frames(self) -> int:
        return int(np.ceil(self.length / FRAME))


@dataclass(frozen=True)
class ClipRef:
    """A clip in a pool: a file path, or in-memory audio for tests."""

    clip_id: str
    path: Path | None = None
    data: Audio | None = field(default=None, compare=False, repr=False)

    def load(self) -> Audio:
        if self.data is not None:
            return self.data
        if self.path is None:
            raise ValueError(f"clip {self.clip_id} has neither data nor path")
        return _load_cached(str(self.path))


@lru_cache(maxsize=1024)
def _load_cached(path: str) -> Audio:
    return audio.load(path)


@dataclass(frozen=True)
class Pools:
    speech: Sequence[ClipRef]
    triggers: Mapping[str, Sequence[ClipRef]]
    music: Sequence[ClipRef] = ()
    noise: Sequence[ClipRef] = ()
    rirs: Sequence[ClipRef] = ()


@dataclass(frozen=True)
class EventSpec:
    trigger: str
    clip_id: str
    start_s: float
    length_s: float
    target_tbr_db: float
    measured_tbr_db: float


@dataclass(frozen=True)
class MixSpec:
    seed: int
    index: int
    speech_ids: tuple[str, ...]
    music_id: str | None
    noise_id: str | None
    rir_id: str | None
    bed_lufs: float
    events: tuple[EventSpec, ...]
    codec: str | None
    kbps: int | None
    peak_gain: float


@dataclass(frozen=True)
class Mixture:
    mixture: Audio
    trigger: Audio
    bed: Audio
    labels: NDArray[np.bool_]
    spec: MixSpec


# ---- maths -----------------------------------------------------------------


def active_frames(
    signal: NDArray[np.floating], relative_db: float = 30.0, floor_db: float = -80.0
) -> NDArray[np.bool_]:
    """Frames within relative_db of the loudest frame.

    The threshold is relative only, so scaling a signal never changes its active
    frames; floor_db just treats near-silence as having no active frames at all.
    """
    powers = audio.frame_powers(signal)
    if not powers.size or powers.max() <= 10 ** (floor_db / 10):
        return np.zeros(powers.shape, dtype=bool)
    return np.asarray(powers >= powers.max() * 10 ** (-relative_db / 10), dtype=bool)


def _active_samples(mask: NDArray[np.bool_], length: int) -> NDArray[np.bool_]:
    return np.repeat(mask, FRAME)[:length]


def tbr_db(trigger: NDArray[np.floating], bed: NDArray[np.floating]) -> float:
    """Trigger-to-bed ratio over the trigger's active samples, in dB."""
    samples = _active_samples(active_frames(trigger), len(trigger))
    if not samples.any():
        return float("-inf")
    return audio.db(audio.power(trigger[samples])) - audio.db(audio.power(bed[samples]))


def scale_to_tbr(trigger: Audio, bed: Audio, target_db: float) -> Audio:
    current = tbr_db(trigger, bed)
    if not np.isfinite(current):
        return trigger
    gain = 10 ** ((target_db - current) / 20)
    return (trigger * gain).astype(np.float32)


def set_relative_level(signal: Audio, reference: Audio, relative_db: float) -> Audio:
    """Scale signal so its RMS sits relative_db from the reference RMS."""
    current = audio.rms_db(signal) - audio.rms_db(reference)
    return (signal * 10 ** ((relative_db - current) / 20)).astype(np.float32)


def normalise_lufs(signal: Audio, target_lufs: float) -> Audio:
    loudness = float(pyloudnorm.Meter(SAMPLE_RATE).integrated_loudness(signal.astype(np.float64)))
    if not np.isfinite(loudness):
        return signal
    return (signal * 10 ** ((target_lufs - loudness) / 20)).astype(np.float32)


def crop(signal: Audio, length: int, rng: np.random.Generator) -> Audio:
    """Random window of exactly length samples, zero-padding short clips at a random offset."""
    if len(signal) >= length:
        start = int(rng.integers(0, len(signal) - length + 1))
        return signal[start : start + length].astype(np.float32)
    out = np.zeros(length, dtype=np.float32)
    offset = int(rng.integers(0, length - len(signal) + 1))
    out[offset : offset + len(signal)] = signal
    return out


def reverb(signal: Audio, rir: Audio, tail: int = 0) -> Audio:
    """Convolve with a room response aligned to its direct path; keep len + tail samples."""
    if not rir.size or not np.any(rir):
        return signal
    direct = int(np.argmax(np.abs(rir)))
    response = rir[direct:] / np.max(np.abs(rir))
    wet = fftconvolve(signal, response)[: len(signal) + tail]
    return np.asarray(wet, dtype=np.float32)


def place(segment: Audio, length: int, start: int) -> Audio:
    out = np.zeros(length, dtype=np.float32)
    end = min(length, start + len(segment))
    out[start:end] = segment[: end - start]
    return out


def peak_gain(signal: NDArray[np.floating], limit: float) -> float:
    peak = float(np.max(np.abs(signal))) if signal.size else 0.0
    return limit / peak if peak > limit else 1.0


# ---- compression -------------------------------------------------------------


CODEC_ARGS = {
    "opus": ["-c:a", "libopus", "-f", "ogg"],
    "aac": ["-c:a", "aac", "-f", "adts"],
}


def align(decoded: Audio, reference: Audio, max_lag: int = 4096) -> Audio:
    """Remove codec delay by cross-correlation, returning exactly len(reference) samples."""
    window = min(len(reference), 4 * SAMPLE_RATE)
    probe = decoded[: window + max_lag]
    correlation = fftconvolve(probe, reference[:window][::-1], mode="full")
    lags = correlation[window - 1 : window - 1 + max_lag + 1]
    lag = int(np.argmax(lags)) if lags.size else 0
    out = np.zeros(len(reference), dtype=np.float32)
    chunk = decoded[lag : lag + len(reference)]
    out[: len(chunk)] = chunk
    return out


def codec_roundtrip(signal: Audio, codec: str, kbps: int, ffmpeg: str) -> Audio:
    """Encode and decode through ffmpeg in memory, like streaming or call audio."""
    quiet = [ffmpeg, "-hide_banner", "-loglevel", "error"]
    raw = ["-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", "1"]
    encoded = subprocess.run(
        [*quiet, *raw, "-i", "pipe:0", *CODEC_ARGS[codec], "-b:a", f"{kbps}k", "pipe:1"],
        input=signal.astype("<f4").tobytes(),
        capture_output=True,
        check=True,
    ).stdout
    decoded = subprocess.run(
        [*quiet, "-i", "pipe:0", *raw, "pipe:1"], input=encoded, capture_output=True, check=True
    ).stdout
    return align(np.frombuffer(decoded, dtype="<f4").astype(np.float32), signal)


# ---- sampler -----------------------------------------------------------------


class MixtureSampler:
    """Deterministic mixtures: sample(i) always returns the same mixture for a seed."""

    def __init__(self, pools: Pools, config: MixConfig | None = None, seed: int = 0) -> None:
        if not pools.speech:
            raise ValueError("speech pool is empty")
        if not any(pools.triggers.values()):
            raise ValueError("trigger pools are empty")
        self.pools = pools
        self.config = config or MixConfig()
        self.seed = seed
        self.ffmpeg = audio.find_ffmpeg()
        if self.config.require_codec and self.ffmpeg is None:
            raise RuntimeError("ffmpeg is required for codec simulation but was not found")
        self.trigger_names = sorted(name for name, clips in pools.triggers.items() if clips)

    @staticmethod
    def _pick(pool: Sequence[ClipRef], rng: np.random.Generator) -> ClipRef:
        return pool[int(rng.integers(0, len(pool)))]

    def _uniform(self, bounds: tuple[float, float], rng: np.random.Generator) -> float:
        return float(rng.uniform(bounds[0], bounds[1]))

    def sample(self, index: int) -> Mixture:
        cfg, pools = self.config, self.pools
        rng = np.random.default_rng([self.seed, index])
        n = cfg.length

        # Bed: speakers, optional music and noise, all in one room.
        count = int(rng.integers(cfg.speakers[0], cfg.speakers[1] + 1))
        speakers = [self._pick(pools.speech, rng) for _ in range(count)]
        speech = crop(speakers[0].load(), n, rng)
        for extra in speakers[1:]:
            voice = crop(extra.load(), n, rng)
            speech = speech + set_relative_level(
                voice, speech, self._uniform(cfg.second_speaker_db, rng)
            )
        rir_clip = (
            self._pick(pools.rirs, rng) if pools.rirs and rng.random() < cfg.rir_prob else None
        )
        rir = rir_clip.load() if rir_clip else None
        tail = int(cfg.reverb_tail_seconds * SAMPLE_RATE)
        if rir is not None:
            speech = reverb(speech, rir)
        bed = speech.copy()
        music_id = noise_id = None
        if pools.music and rng.random() < cfg.music_prob:
            clip = self._pick(pools.music, rng)
            music_id = clip.clip_id
            bed += set_relative_level(
                crop(clip.load(), n, rng), speech, self._uniform(cfg.music_db, rng)
            )
        if pools.noise and rng.random() < cfg.noise_prob:
            clip = self._pick(pools.noise, rng)
            noise_id = clip.clip_id
            bed += set_relative_level(
                crop(clip.load(), n, rng), speech, self._uniform(cfg.noise_db, rng)
            )
        bed_lufs = self._uniform(cfg.bed_lufs, rng)
        bed = normalise_lufs(bed, bed_lufs)

        # Trigger events, each scaled to its own target ratio against the bed.
        events: list[EventSpec] = []
        trigger = np.zeros(n, dtype=np.float32)
        event_count = int(rng.choice(3, p=np.array(cfg.event_count_probs)))
        for _ in range(event_count):
            name = self.trigger_names[int(rng.integers(0, len(self.trigger_names)))]
            clip = self._pick(pools.triggers[name], rng)
            source = clip.load()
            seconds = self._uniform(cfg.event_seconds, rng)
            segment = crop(source, min(len(source), int(seconds * SAMPLE_RATE)), rng)
            if rir is not None:
                segment = reverb(segment, rir, tail)
            start = int(rng.integers(0, max(1, n - len(segment))))
            event = place(segment, n, start)
            target = self._uniform(cfg.tbr_db, rng)
            event = scale_to_tbr(event, bed, target)
            measured = tbr_db(event, bed)
            if not np.isfinite(measured):
                continue
            trigger += event
            events.append(
                EventSpec(
                    name,
                    clip.clip_id,
                    start / SAMPLE_RATE,
                    len(segment) / SAMPLE_RATE,
                    target,
                    measured,
                )
            )

        # Keep headroom: one gain for every part, so the ratios stay exact.
        mixture = bed + trigger
        gain = peak_gain(mixture, cfg.peak_limit)
        bed, trigger, mixture = bed * gain, trigger * gain, mixture * gain

        codec = kbps = None
        if self.ffmpeg is not None and rng.random() < cfg.codec_prob:
            codec = "opus" if rng.random() < 0.5 else "aac"
            choices = cfg.opus_kbps if codec == "opus" else cfg.aac_kbps
            kbps = int(choices[int(rng.integers(0, len(choices)))])
            mixture = codec_roundtrip(mixture, codec, kbps, self.ffmpeg)
            after = peak_gain(mixture, cfg.peak_limit)
            bed, trigger, mixture = bed * after, trigger * after, mixture * after
            gain *= after

        labels = active_frames(trigger) if events else np.zeros(cfg.frames, dtype=bool)
        spec = MixSpec(
            seed=self.seed,
            index=index,
            speech_ids=tuple(clip.clip_id for clip in speakers),
            music_id=music_id,
            noise_id=noise_id,
            rir_id=rir_clip.clip_id if rir_clip else None,
            bed_lufs=bed_lufs,
            events=tuple(events),
            codec=codec,
            kbps=kbps,
            peak_gain=float(gain),
        )
        return Mixture(
            mixture.astype(np.float32),
            trigger.astype(np.float32),
            bed.astype(np.float32),
            labels[: cfg.frames],
            spec,
        )
