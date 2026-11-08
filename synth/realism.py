"""Automated realism checks for generated mixtures.

Structure checks (clipping, ratio ranges) need no model. Presence checks use an
independent AudioSet tagger (PANNs on Kaggle) that is never used in training:
it should hear speech in mixtures with speech, the trigger near loud trigger
events, and no trigger in trigger-free mixtures.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from synth import audio
from synth.audio import SAMPLE_RATE, Audio
from synth.mix import MixConfig, Mixture

TAG_GROUPS: dict[str, tuple[str, ...]] = {
    "speech": (
        "Speech",
        "Male speech, man speaking",
        "Female speech, woman speaking",
        "Child speech, kid speaking",
        "Conversation",
        "Narration, monologue",
    ),
    "chewing_eating": ("Chewing, mastication", "Biting", "Crunch"),
    "sniffing_breathing": ("Sniff", "Breathing", "Snort", "Gasp", "Pant", "Wheeze"),
    "clicks": ("Clicking", "Tick", "Tap", "Clickety-clack"),
    "typing": ("Typing", "Computer keyboard", "Typewriter", "Clickety-clack"),
}
TRIGGER_GROUPS = ("chewing_eating", "sniffing_breathing", "clicks", "typing")

GATE = {
    "clipped_count": 0,
    "tbr_in_range_rate": 1.0,
    "speech_detect_rate": 0.90,
    "trigger_detect_rate": 0.60,
    "false_trigger_rate": 0.10,
}
DETECTION_MIN_TBR_DB = 5.0
EVENT_WINDOW_SECONDS = 2.0


class Tagger(Protocol):
    labels: Sequence[str]

    def __call__(self, signal: Audio) -> NDArray[np.floating]:
        """Clip-level probabilities for 16 kHz audio, aligned with labels."""
        ...


def missing_labels(labels: Sequence[str]) -> list[str]:
    known = set(labels)
    return sorted({name for group in TAG_GROUPS.values() for name in group} - known)


def group_score(probs: NDArray[np.floating], labels: Sequence[str], group: str) -> float:
    index = {name: i for i, name in enumerate(labels)}
    scores = [float(probs[index[name]]) for name in TAG_GROUPS[group] if name in index]
    return max(scores, default=0.0)


def in_top_k(probs: NDArray[np.floating], labels: Sequence[str], group: str, k: int) -> bool:
    top = {labels[i] for i in np.argsort(probs)[::-1][:k]}
    return bool(top.intersection(TAG_GROUPS[group]))


@dataclass(frozen=True)
class Detection:
    threshold: float = 0.1
    top_k: int = 10

    def hears(self, probs: NDArray[np.floating], labels: Sequence[str], group: str) -> bool:
        return group_score(probs, labels, group) >= self.threshold or in_top_k(
            probs, labels, group, self.top_k
        )


@dataclass(frozen=True)
class MixtureCheck:
    index: int
    clipped: bool
    peak: float
    events: int
    tbr_in_range: bool
    strongest_trigger: str | None
    strongest_tbr_db: float | None
    speech_heard: bool | None = None
    speech_score: float | None = None
    trigger_heard: bool | None = None
    trigger_score: float | None = None
    false_trigger: bool | None = None
    codec: str | None = None


def event_window(m: Mixture, start_s: float, length_s: float) -> Audio:
    centre = int((start_s + length_s / 2) * SAMPLE_RATE)
    half = int(EVENT_WINDOW_SECONDS * SAMPLE_RATE / 2)
    lo = max(0, min(centre - half, len(m.mixture) - 2 * half))
    return m.mixture[lo : lo + 2 * half]


def check(
    m: Mixture,
    config: MixConfig,
    tagger: Tagger | None = None,
    detection: Detection | None = None,
    tolerance_db: float = 0.1,
) -> MixtureCheck:
    peak = float(np.max(np.abs(m.mixture)))
    low, high = config.tbr_db
    in_range = all(
        low - tolerance_db <= e.measured_tbr_db <= high + tolerance_db for e in m.spec.events
    )
    strongest = max(m.spec.events, key=lambda e: e.measured_tbr_db, default=None)
    result = MixtureCheck(
        index=m.spec.index,
        clipped=peak >= 1.0,
        peak=peak,
        events=len(m.spec.events),
        tbr_in_range=in_range,
        strongest_trigger=strongest.trigger if strongest else None,
        strongest_tbr_db=strongest.measured_tbr_db if strongest else None,
        codec=m.spec.codec,
    )
    if tagger is None:
        return result
    detection = detection or Detection()

    labels = tagger.labels
    whole = tagger(m.mixture)
    speech_score = group_score(whole, labels, "speech")
    values: dict[str, Any] = {
        "speech_heard": detection.hears(whole, labels, "speech"),
        "speech_score": speech_score,
    }
    if strongest is not None:
        window = tagger(event_window(m, strongest.start_s, strongest.length_s))
        values["trigger_score"] = group_score(window, labels, strongest.trigger)
        values["trigger_heard"] = detection.hears(window, labels, strongest.trigger)
    else:
        values["false_trigger"] = any(detection.hears(whole, labels, g) for g in TRIGGER_GROUPS)
    return MixtureCheck(**{**asdict(result), **values})


def _rate(flags: Iterable[bool]) -> float | None:
    values = list(flags)
    return sum(values) / len(values) if values else None


def summarise(checks: Sequence[MixtureCheck]) -> dict[str, Any]:
    """Metrics and a pass/fail for each gate target."""
    with_events = [c for c in checks if c.events]
    loud = [
        c
        for c in with_events
        if c.strongest_tbr_db is not None
        and c.strongest_tbr_db >= DETECTION_MIN_TBR_DB
        and c.trigger_heard is not None
    ]
    quiet = [c for c in checks if not c.events and c.false_trigger is not None]
    tagged = [c for c in checks if c.speech_heard is not None]
    metrics: dict[str, Any] = {
        "mixtures": len(checks),
        "with_trigger": len(with_events),
        "without_trigger": len(checks) - len(with_events),
        "clipped_count": sum(c.clipped for c in checks),
        "max_peak": max((c.peak for c in checks), default=0.0),
        "tbr_in_range_rate": _rate(c.tbr_in_range for c in with_events),
        "speech_detect_rate": _rate(bool(c.speech_heard) for c in tagged),
        "trigger_detect_rate": _rate(bool(c.trigger_heard) for c in loud),
        "trigger_detect_count": len(loud),
        "false_trigger_rate": _rate(bool(c.false_trigger) for c in quiet),
        "false_trigger_count": len(quiet),
    }
    by_trigger: dict[str, list[bool]] = {}
    for c in loud:
        by_trigger.setdefault(str(c.strongest_trigger), []).append(bool(c.trigger_heard))
    metrics["trigger_detect_rate_by_trigger"] = {k: _rate(v) for k, v in sorted(by_trigger.items())}
    metrics["gate"] = gate_results(metrics)
    return metrics


def gate_results(metrics: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for name, target in GATE.items():
        actual = metrics.get(name)
        if actual is None:
            passed = None
        elif name in {"clipped_count", "false_trigger_rate"}:
            passed = actual <= target
        else:
            passed = actual >= target
        results[name] = {"target": target, "actual": actual, "passed": passed}
    return results


def render_spectrogram(m: Mixture, path: Path, title: str) -> None:
    """Mixture, trigger and bed spectrograms with the 10 ms labels, for visual review."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(4, 1, figsize=(10, 9), sharex=True)
    for axis, (name, signal) in zip(
        axes[:3], (("mixture", m.mixture), ("trigger", m.trigger), ("bed", m.bed)), strict=True
    ):
        axis.set_ylabel(f"{name}\nHz")
        if np.max(np.abs(signal)) < 1e-6:
            axis.set_facecolor("black")
            axis.text(
                0.5, 0.5, "silent", color="white", ha="center", va="center",
                transform=axis.transAxes,
            )  # fmt: skip
            continue
        dither = np.random.default_rng(0).standard_normal(len(signal)) * 1e-7
        spectrum, _, _, image = axis.specgram(
            signal + dither, NFFT=512, Fs=SAMPLE_RATE, noverlap=384, cmap="magma"
        )
        top = 10 * np.log10(max(float(np.max(spectrum)), 1e-20))
        image.set_clim(top - 80, top)  # 80 dB range below each panel's loudest point
    times = np.arange(len(m.labels)) * audio.FRAME_SECONDS
    axes[3].fill_between(times, m.labels.astype(float), step="post")
    axes[3].set_ylim(-0.05, 1.05)
    axes[3].set_ylabel("trigger\nactive")
    axes[3].set_xlabel("seconds")
    figure.suptitle(title, fontsize=10)
    figure.tight_layout()
    figure.savefig(path, dpi=90)
    plt.close(figure)


class PannsTagger:  # pragma: no cover - runs on Kaggle with a GPU and internet
    """PANNs Cnn14 (32 kHz) via the panns-inference package."""

    sample_rate = 32_000

    def __init__(self, device: str = "cuda") -> None:
        from panns_inference import AudioTagging, labels

        self.model = AudioTagging(checkpoint_path=None, device=device)
        self.labels: Sequence[str] = list(labels)
        missing = missing_labels(self.labels)
        if missing:
            raise RuntimeError(f"tagger is missing expected labels: {missing}")

    def __call__(self, signal: Audio) -> NDArray[np.floating]:
        upsampled = audio.resample(signal, SAMPLE_RATE, self.sample_rate)
        clipwise, _ = self.model.inference(upsampled[None, :])
        return np.asarray(clipwise[0], dtype=np.float32)
