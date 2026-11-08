"""Mixture maths and the sampler, on synthetic signals."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from synth import audio, mix
from synth.audio import FRAME, SAMPLE_RATE
from synth.mix import ClipRef, MixConfig, MixtureSampler, Pools

RNG = np.random.default_rng(0)
N = 4 * SAMPLE_RATE


def noise(seconds: float, seed: int, level: float = 0.1) -> np.ndarray:
    return (level * np.random.default_rng(seed).standard_normal(int(seconds * SAMPLE_RATE))).astype(
        np.float32
    )


def burst(seed: int, seconds: float = 0.5) -> np.ndarray:
    """A click train: short decaying bursts, like a pen or keyboard."""
    out = np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)
    rng = np.random.default_rng(seed)
    for start in range(0, len(out) - 400, 1600):
        out[start : start + 400] = rng.standard_normal(400) * np.exp(-np.arange(400) / 60)
    return out


def speechlike(seconds: float, seed: int) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 4 * t + seed)
    return (noise(seconds, seed, 0.1) * envelope).astype(np.float32)


def room(seed: int) -> np.ndarray:
    length = int(0.4 * SAMPLE_RATE)
    rng = np.random.default_rng(seed)
    rir = rng.standard_normal(length) * np.exp(-np.arange(length) / (0.05 * SAMPLE_RATE))
    rir[:20] = 0
    rir[20] = 3.0
    return rir.astype(np.float32)


def pools() -> Pools:
    return Pools(
        speech=[ClipRef(f"s{i}", data=speechlike(6, i)) for i in range(4)],
        triggers={
            "clicks": [ClipRef(f"c{i}", data=burst(i, 1.0)) for i in range(3)],
            "chewing_eating": [ClipRef(f"e{i}", data=noise(2.0, 100 + i, 0.3)) for i in range(3)],
        },
        music=[ClipRef("m0", data=noise(5, 50, 0.05))],
        noise=[ClipRef("n0", data=noise(5, 60, 0.02))],
        rirs=[ClipRef(f"r{i}", data=room(i)) for i in range(2)],
    )


NO_CODEC = MixConfig(codec_prob=0.0)


# ---- maths -------------------------------------------------------------------


def test_active_frames_finds_the_burst_only() -> None:
    signal = np.zeros(N, dtype=np.float32)
    signal[16000:24000] = noise(0.5, 1)
    frames = mix.active_frames(signal)
    assert frames.shape == (N // FRAME,)
    assert frames[100:150].all()
    assert not frames[:99].any() and not frames[151:].any()


def test_active_frames_of_silence_is_empty() -> None:
    assert not mix.active_frames(np.zeros(N, dtype=np.float32)).any()


@settings(max_examples=80, deadline=None)
@given(
    target=st.floats(-5, 15),
    start=st.integers(0, N - 8000),
    bed_level=st.floats(0.001, 0.5),
    seed=st.integers(0, 10_000),
)
def test_scale_to_tbr_hits_target_within_0_1_db(
    target: float, start: int, bed_level: float, seed: int
) -> None:
    bed = noise(4, seed, bed_level)
    trigger = mix.place(burst(seed + 1), N, start)
    scaled = mix.scale_to_tbr(trigger, bed, target)
    assert mix.tbr_db(scaled, bed) == pytest.approx(target, abs=0.1)


def test_tbr_is_measured_only_where_the_trigger_is_active() -> None:
    bed = np.full(N, 0.1, dtype=np.float32)
    bed[:8000] = 0.5  # loud bed far from the trigger must not count
    trigger = np.zeros(N, dtype=np.float32)
    trigger[32000:36000] = 0.1
    assert mix.tbr_db(trigger, bed) == pytest.approx(0.0, abs=0.01)


def test_set_relative_level() -> None:
    a, b = noise(1, 1, 0.3), noise(1, 2, 0.1)
    scaled = mix.set_relative_level(a, b, -6.0)
    assert audio.rms_db(scaled) - audio.rms_db(b) == pytest.approx(-6.0, abs=1e-3)


def test_normalise_lufs() -> None:
    import pyloudnorm

    out = mix.normalise_lufs(speechlike(4, 3), -23.0)
    measured = pyloudnorm.Meter(SAMPLE_RATE).integrated_loudness(out.astype(np.float64))
    assert measured == pytest.approx(-23.0, abs=0.1)


def test_crop_pads_short_clips_and_cuts_long_ones() -> None:
    rng = np.random.default_rng(1)
    assert mix.crop(np.ones(10, dtype=np.float32), 100, rng).sum() == 10
    assert len(mix.crop(np.ones(500, dtype=np.float32), 100, rng)) == 100


def test_reverb_keeps_the_direct_path_aligned() -> None:
    impulse = np.zeros(1000, dtype=np.float32)
    impulse[100] = 1.0
    wet = mix.reverb(impulse, room(0))
    assert len(wet) == 1000
    assert int(np.argmax(np.abs(wet))) == 100


def test_peak_gain() -> None:
    assert mix.peak_gain(np.array([0.5, -2.0]), 0.98) == pytest.approx(0.49)
    assert mix.peak_gain(np.array([0.5]), 0.98) == 1.0


# ---- sampler -----------------------------------------------------------------


def test_mixture_shapes_and_sum_without_codec() -> None:
    m = MixtureSampler(pools(), NO_CODEC, seed=1).sample(0)
    assert m.mixture.shape == m.trigger.shape == m.bed.shape == (N,)
    assert m.labels.shape == (N // FRAME,)
    np.testing.assert_allclose(m.mixture, m.bed + m.trigger, atol=1e-6)


def test_same_seed_and_index_give_the_same_mixture() -> None:
    a = MixtureSampler(pools(), NO_CODEC, seed=7).sample(3)
    b = MixtureSampler(pools(), NO_CODEC, seed=7).sample(3)
    c = MixtureSampler(pools(), NO_CODEC, seed=7).sample(4)
    np.testing.assert_array_equal(a.mixture, b.mixture)
    assert a.spec == b.spec
    assert not np.array_equal(a.mixture, c.mixture)


def test_200_mixtures_never_clip_and_ratios_stay_in_range() -> None:
    sampler = MixtureSampler(pools(), NO_CODEC, seed=2)
    for index in range(200):
        m = sampler.sample(index)
        assert np.max(np.abs(m.mixture)) <= 0.98 + 1e-6
        for event in m.spec.events:
            assert -5.0 - 0.1 <= event.measured_tbr_db <= 15.0 + 0.1
            assert event.measured_tbr_db == pytest.approx(event.target_tbr_db, abs=0.1)


def test_about_20_percent_have_no_trigger() -> None:
    sampler = MixtureSampler(pools(), NO_CODEC, seed=3)
    empty = sum(1 for i in range(500) if not sampler.sample(i).spec.events)
    assert 70 <= empty <= 130  # binomial(500, 0.2) within about 3 standard deviations


def test_labels_follow_the_trigger() -> None:
    sampler = MixtureSampler(pools(), NO_CODEC, seed=4)
    checked = 0
    for index in range(60):
        m = sampler.sample(index)
        if not m.spec.events:
            assert not m.labels.any()
            assert not m.trigger.any()
            continue
        # A clip can start in a quiet gap, so labels may begin after the event start,
        # but never before it, and they always match where the trigger has energy.
        first = min(event.start_s for event in m.spec.events)
        assert int(np.argmax(m.labels)) >= int(first * SAMPLE_RATE) // FRAME
        assert not m.trigger[: int(first * SAMPLE_RATE)].any()
        np.testing.assert_array_equal(m.labels, mix.active_frames(m.trigger))
        checked += 1
    assert checked > 30


def test_loud_inputs_are_protected_from_clipping() -> None:
    loud = Pools(
        speech=[ClipRef("s", data=noise(6, 1, 0.9))],
        triggers={"clicks": [ClipRef("c", data=burst(1) * 50)]},
    )
    cfg = MixConfig(codec_prob=0.0, bed_lufs=(-5.0, -5.0), tbr_db=(15.0, 15.0))
    sampler = MixtureSampler(loud, cfg, seed=0)
    for index in range(20):
        assert np.max(np.abs(sampler.sample(index).mixture)) <= 0.98 + 1e-6


def test_empty_pools_are_rejected() -> None:
    with pytest.raises(ValueError):
        MixtureSampler(Pools(speech=[], triggers={"x": [ClipRef("c", data=burst(1))]}))
    with pytest.raises(ValueError):
        MixtureSampler(Pools(speech=[ClipRef("s", data=noise(1, 1))], triggers={"x": []}))


# ---- compression (needs ffmpeg; always runs in CI) -----------------------------

needs_ffmpeg = pytest.mark.skipif(audio.find_ffmpeg() is None, reason="ffmpeg not installed")


@needs_ffmpeg
@pytest.mark.parametrize(("codec", "kbps"), [("opus", 24), ("aac", 64)])
def test_codec_roundtrip_keeps_length_and_alignment(codec: str, kbps: int) -> None:
    signal = speechlike(4, 9)
    ffmpeg = audio.find_ffmpeg()
    assert ffmpeg is not None
    out = mix.codec_roundtrip(signal, codec, kbps, ffmpeg)
    assert out.shape == signal.shape
    correlation = np.corrcoef(out, signal)[0, 1]
    assert correlation > 0.9
    assert not np.array_equal(out, signal)


@needs_ffmpeg
def test_sampler_with_codec_stays_in_bounds() -> None:
    sampler = MixtureSampler(pools(), MixConfig(codec_prob=1.0, require_codec=True), seed=5)
    for index in range(10):
        m = sampler.sample(index)
        assert m.spec.codec in {"opus", "aac"}
        assert np.max(np.abs(m.mixture)) <= 0.98 + 1e-6
        assert m.mixture.shape == (N,)


def test_require_codec_without_ffmpeg_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audio, "find_ffmpeg", lambda: None)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        MixtureSampler(pools(), MixConfig(require_codec=True))
