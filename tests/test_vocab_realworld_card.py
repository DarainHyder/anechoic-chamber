"""Vocabulary, the locked real-world test set, and the data card."""

import json
from pathlib import Path

import pytest

from eval import realworld
from eval.realworld import LockError, RealWorldClip
from synth import data_card, vocab
from synth.freesound import ClipRecord
from synth.sources import SOURCES

# ---- vocabulary ----------------------------------------------------------------


def test_vocabulary_file_is_valid() -> None:
    rows = vocab.load()
    assert vocab.problems(rows) == []
    assert len(rows) == 300


def test_vocabulary_problems_are_reported() -> None:
    rows = [("clicks", "Pen Clicking"), ("clicks", "pen clicking"), ("nope", "a b c d e f g")]
    found = vocab.problems(rows)
    assert any("expected 300" in p for p in found)
    assert any("unknown group" in p for p in found)
    assert any("too long" in p for p in found)
    assert any("lowercase" in p for p in found)


# ---- real-world test set -----------------------------------------------------------


def clip(
    i: int,
    scene: str = "eating_with_speech",
    user: str = "u",
    score: float = 0.5,
    licence: str = "CC0-1.0",
) -> RealWorldClip:
    return RealWorldClip(
        i, user, licence, f"https://freesound.org/s/{i}/", scene, "ab" * 32, 10.0, score, score
    )


def test_select_caps_uploaders_and_rotates_scenes() -> None:
    candidates = [clip(i, "eating_with_speech", "busy", 0.9) for i in range(10)]
    candidates += [clip(100 + i, "typing_with_speech", f"t{i}", 0.5) for i in range(10)]
    chosen = realworld.select(candidates, size=6, max_per_uploader=2)
    assert len(chosen) == 6
    assert sum(1 for c in chosen if c.username == "busy") == 2
    assert {c.scene for c in chosen} == {"eating_with_speech", "typing_with_speech"}


def test_select_prefers_clear_clips_and_drops_non_release_licences() -> None:
    candidates = [
        clip(1, user="a", score=0.2),
        clip(2, user="b", score=0.9),
        clip(3, user="c", score=0.99, licence="CC-BY-NC-4.0"),
    ]
    chosen = realworld.select(candidates, size=1)
    assert [c.freesound_id for c in chosen] == [2]


def test_select_is_deterministic() -> None:
    candidates = [clip(i, user=f"u{i % 5}", score=(i % 7) / 7) for i in range(40)]
    assert realworld.select(candidates, 20) == realworld.select(list(reversed(candidates)), 20)


def test_lock_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    path = tmp_path / "lock.json"
    realworld.write_lock([clip(2, user="b"), clip(1, user="a")], path, "2026-11-08")
    loaded = realworld.load_lock(path)
    assert [c.freesound_id for c in loaded] == [1, 2]
    assert realworld.uploaders(loaded) == {"a", "b"}
    data = json.loads(path.read_text())
    data["clips"][0]["scene"] = "typing_with_speech"
    path.write_text(json.dumps(data))
    with pytest.raises(LockError, match="changed"):
        realworld.load_lock(path)


def test_lock_refuses_empty_or_non_release_sets(tmp_path: Path) -> None:
    with pytest.raises(LockError):
        realworld.write_lock([], tmp_path / "x.json", "2026-11-08")
    with pytest.raises(LockError, match="CC0 or CC BY"):
        realworld.write_lock([clip(1, licence="CC-BY-NC-4.0")], tmp_path / "x.json", "d")


def test_the_committed_lock_is_untouched() -> None:
    if not realworld.LOCK_PATH.is_file():
        pytest.skip("test set not locked yet (created from Kaggle K1 output)")
    clips = realworld.load_lock()
    assert clips


def test_every_scene_maps_to_a_trigger() -> None:
    assert set(realworld.SCENES) == set(realworld.SCENE_TRIGGER)


# ---- data card -----------------------------------------------------------------


def record(i: int, licence: str = "CC0-1.0", group: str = "clicks") -> ClipRecord:
    return ClipRecord(
        i,
        f"clip|{i}",
        f"user{i % 3}",
        licence,
        "",
        [],
        2.0,
        f"https://freesound.org/s/{i}/",
        group,
        "search:x",
        f"{group}/{i}.ogg",
        "cd" * 32,
    )


def test_data_card_lists_sources_licences_counts_and_gaps() -> None:
    card = data_card.build(
        SOURCES,
        {"librispeech": {"train": 100, "val": 10, "test": 12}},
        [record(1), record(2, "CC-BY-4.0", "typing")],
        [clip(5, user="z")],
        "2026-11-08",
    )
    assert "| LibriSpeech | speech | CC-BY-4.0 | 122 | 100 / 10 / 12 |" in card
    assert "| CC-BY-4.0 | 1 |" in card
    assert "2 clips from 2 uploaders" in card
    assert "1 clips, locked" in card
    assert "Urdu" in card and "No local recordings" in card


def test_attribution_lists_every_clip_with_author_and_link() -> None:
    text = data_card.attribution([record(1), record(2, "CC-BY-4.0")], [clip(5, user="z")])
    assert "[1](https://freesound.org/s/1/) | clip/1 | user1 | CC0-1.0" in text
    assert "[5](https://freesound.org/s/5/) | eating_with_speech | z | CC0-1.0" in text
