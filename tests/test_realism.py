"""Realism checks with a fake tagger, gate maths, and spectrogram images."""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from synth import realism
from synth.mix import MixConfig, MixtureSampler
from synth.realism import TAG_GROUPS, Detection, MixtureCheck
from tests.test_mix import NO_CODEC, pools

ALL_LABELS = sorted(
    {name for group in TAG_GROUPS.values() for name in group} | {"Music", "Silence"}
)


class FakeTagger:
    """Hears speech always; hears a trigger when the window is loud."""

    labels: Sequence[str] = ALL_LABELS

    def __init__(self, trigger_label: str = "Clicking", loud_rms: float = 0.05) -> None:
        self.trigger_label = trigger_label
        self.loud_rms = loud_rms
        self.calls = 0

    def __call__(self, signal: np.ndarray) -> np.ndarray:
        self.calls += 1
        probs = np.zeros(len(self.labels), dtype=np.float32)
        probs[self.labels.index("Speech")] = 0.9
        probs[self.labels.index("Music")] = 0.5
        probs[self.labels.index("Silence")] = 0.4
        rms = float(np.sqrt(np.mean(np.square(signal))))
        if rms > self.loud_rms:
            probs[self.labels.index(self.trigger_label)] = 0.3
        return probs


def test_expected_labels_exist_in_audioset() -> None:
    assert realism.missing_labels(ALL_LABELS) == []
    assert realism.missing_labels(["Speech"]) != []


def test_mouse_is_not_used_because_it_means_the_animal() -> None:
    assert all("Mouse" not in group for group in TAG_GROUPS.values())


def test_detection_by_threshold_or_top_k() -> None:
    labels = ["Speech", "Clicking", "Music", "Tick"]
    probs = np.array([0.9, 0.02, 0.5, 0.01])
    assert Detection(threshold=0.1, top_k=2).hears(probs, labels, "speech")
    assert not Detection(threshold=0.1, top_k=2).hears(probs, labels, "clicks")
    assert Detection(threshold=0.1, top_k=3).hears(probs, labels, "clicks")
    assert Detection(threshold=0.01, top_k=1).hears(probs, labels, "clicks")


def test_structure_checks_without_a_tagger() -> None:
    m = MixtureSampler(pools(), NO_CODEC, seed=1).sample(0)
    result = realism.check(m, NO_CODEC)
    assert not result.clipped
    assert result.tbr_in_range
    assert result.speech_heard is None


def test_tagger_checks_fill_in_presence() -> None:
    sampler = MixtureSampler(pools(), NO_CODEC, seed=2)
    tagger = FakeTagger(loud_rms=0.0)
    checks = [
        realism.check(sampler.sample(i), NO_CODEC, tagger, Detection(0.1, 1)) for i in range(40)
    ]
    assert all(c.speech_heard for c in checks)
    with_events = [c for c in checks if c.events]
    without = [c for c in checks if not c.events]
    assert with_events and without
    assert all(c.false_trigger is not None for c in without)
    assert all(c.trigger_heard is not None for c in with_events)


def make_check(**overrides: object) -> MixtureCheck:
    base: dict[str, object] = dict(
        index=0,
        clipped=False,
        peak=0.5,
        events=1,
        tbr_in_range=True,
        strongest_trigger="clicks",
        strongest_tbr_db=10.0,
        speech_heard=True,
        speech_score=0.9,
        trigger_heard=True,
        trigger_score=0.4,
    )
    base.update(overrides)
    return MixtureCheck(**base)  # type: ignore[arg-type]


def test_summary_rates_and_gate() -> None:
    checks = (
        [make_check(index=i) for i in range(6)]
        + [make_check(index=10 + i, trigger_heard=False) for i in range(4)]
        + [make_check(index=20, strongest_tbr_db=0.0, trigger_heard=False)]
        + [
            make_check(
                index=30 + i,
                events=0,
                strongest_trigger=None,
                strongest_tbr_db=None,
                trigger_heard=None,
                false_trigger=i == 0,
            )
            for i in range(10)
        ]
    )
    summary = realism.summarise(checks)
    assert summary["mixtures"] == 21
    assert summary["trigger_detect_count"] == 10  # the 0 dB event is excluded
    assert summary["trigger_detect_rate"] == pytest.approx(0.6)
    assert summary["false_trigger_rate"] == pytest.approx(0.1)
    assert summary["speech_detect_rate"] == 1.0
    gate = summary["gate"]
    assert gate["trigger_detect_rate"]["passed"] is True
    assert gate["false_trigger_rate"]["passed"] is True
    assert gate["clipped_count"]["passed"] is True


def test_gate_fails_on_clipping_and_out_of_range_ratios() -> None:
    summary = realism.summarise(
        [make_check(clipped=True, peak=1.0), make_check(tbr_in_range=False)]
    )
    assert summary["gate"]["clipped_count"]["passed"] is False
    assert summary["gate"]["tbr_in_range_rate"]["passed"] is False


def test_missing_measurements_are_not_passes() -> None:
    summary = realism.summarise([make_check(speech_heard=None, trigger_heard=None)])
    assert summary["gate"]["speech_detect_rate"]["passed"] is None


def test_event_window_stays_inside_the_mixture() -> None:
    m = MixtureSampler(pools(), NO_CODEC, seed=3).sample(1)
    assert len(realism.event_window(m, 0.0, 0.1)) == 32000
    assert len(realism.event_window(m, 3.9, 0.1)) == 32000


def test_spectrogram_image_is_written(tmp_path: Path) -> None:
    m = MixtureSampler(pools(), MixConfig(codec_prob=0.0), seed=4).sample(0)
    path = tmp_path / "spec.png"
    realism.render_spectrogram(m, path, "test")
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert path.stat().st_size > 10_000
