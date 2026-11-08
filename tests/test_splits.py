"""Splits are deterministic, balanced and leak-free."""

from collections import Counter

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from synth import splits
from synth.splits import TEST, TRAIN, VAL, Assignment


def test_hashed_split_is_deterministic_and_roughly_80_10_10() -> None:
    groups = [f"user{i}" for i in range(5000)]
    first = [splits.hashed_split(g) for g in groups]
    assert first == [splits.hashed_split(g) for g in groups]
    share = Counter(first)
    assert 0.77 < share[TRAIN] / 5000 < 0.83
    assert 0.08 < share[VAL] / 5000 < 0.12
    assert 0.08 < share[TEST] / 5000 < 0.12


def test_salt_changes_the_assignment() -> None:
    groups = [f"user{i}" for i in range(200)]
    a = [splits.hashed_split(g, salt="a") for g in groups]
    b = [splits.hashed_split(g, salt="b") for g in groups]
    assert a != b


@pytest.mark.parametrize(("fold", "split"), [(1, TRAIN), (3, TRAIN), (4, VAL), (5, TEST)])
def test_esc50_folds(fold: int, split: str) -> None:
    assert splits.esc50("1-100-A-1.wav", fold).split == split


@pytest.mark.parametrize(
    ("subset", "split"), [("train-clean-100", TRAIN), ("dev-clean", VAL), ("test-clean", TEST)]
)
def test_librispeech_uses_official_subsets(subset: str, split: str) -> None:
    a = splits.librispeech(f"data/LibriSpeech/{subset}/84/121123/84-121123-0000.flac")
    assert a.split == split
    assert a.group == "librispeech-spk84"


def test_freesound_groups_by_uploader_case_insensitively() -> None:
    a = splits.freesound("1.ogg", "Alice")
    b = splits.freesound("2.ogg", "alice")
    assert a.group == b.group
    assert a.split == b.split


def test_test_set_uploaders_are_forced_into_test() -> None:
    assert splits.freesound("1.ogg", "Bob", test_set_uploaders=["bob"]).split == TEST


def test_rir_rooms_group_together() -> None:
    a = splits.rir("RIRS_NOISES/simulated_rirs/smallroom/Room001/Room001-00001.wav")
    b = splits.rir("RIRS_NOISES/simulated_rirs/smallroom/Room001/Room001-00002.wav")
    c = splits.rir("RIRS_NOISES/simulated_rirs/smallroom/Room002/Room002-00001.wav")
    assert a.group == b.group != c.group
    real1 = splits.rir(
        "RIRS_NOISES/real_rirs_isotropic_noises/RVB2014_type1_rir_largeroom1_near_angla.wav"
    )
    real2 = splits.rir(
        "RIRS_NOISES/real_rirs_isotropic_noises/RVB2014_type1_rir_largeroom1_far_angla.wav"
    )
    assert real1.group == real2.group


@settings(max_examples=60)
@given(
    st.lists(
        st.tuples(
            st.sampled_from(["alice", "bob", "carol", "dave", "erin"]), st.integers(0, 10**6)
        ),
        min_size=1,
        max_size=200,
    ),
    st.sets(st.sampled_from(["alice", "bob", "carol", "dave", "erin"]), max_size=2),
)
def test_no_uploader_ever_spans_two_splits(
    clips: list[tuple[str, int]], test_users: set[str]
) -> None:
    assigned = [splits.freesound(f"{n}.ogg", user, test_users) for user, n in clips]
    assert splits.leaks(assigned) == {}
    assert splits.test_set_uploader_leaks(assigned, test_users) == []


def test_leak_checker_catches_a_planted_leak() -> None:
    planted = [
        Assignment("a", "freesound", "freesound-user:alice", TRAIN),
        Assignment("b", "freesound", "freesound-user:alice", TEST),
        Assignment("c", "freesound", "freesound-user:bob", VAL),
    ]
    assert splits.leaks(planted) == {"freesound-user:alice": {TRAIN, TEST}}
    assert splits.test_set_uploader_leaks(planted, ["alice"]) == ["a"]


def test_counts_table() -> None:
    table = splits.counts([splits.esc50("a", 1), splits.esc50("b", 5), splits.musan("m/x.wav")])
    assert table["esc50"] == {TRAIN: 1, VAL: 0, TEST: 1}
    assert sum(table["musan"].values()) == 1
