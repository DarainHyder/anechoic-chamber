"""Assign train, val and test splits by source group, and prove nothing leaks.

A group is the unit that must never span two splits: an ESC-50 fold, a
LibriSpeech speaker, a Freesound uploader, a MUSAN file, a room. Anyone whose
clips are in the frozen real-world test set is kept out of train and val too.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

TRAIN, VAL, TEST = "train", "val", "test"
SPLITS = (TRAIN, VAL, TEST)
DEFAULT_SALT = "anechoic-chamber-v1"
ESC50_FOLDS = {1: TRAIN, 2: TRAIN, 3: TRAIN, 4: VAL, 5: TEST}
LIBRISPEECH_SUBSETS = {"train-clean-100": TRAIN, "dev-clean": VAL, "test-clean": TEST}


def hashed_split(group: str, salt: str = DEFAULT_SALT, val: float = 0.1, test: float = 0.1) -> str:
    """Deterministic 80/10/10 split from a hash of the group name."""
    digest = hashlib.sha256(f"{salt}:{group}".encode()).digest()
    position = int.from_bytes(digest[:8], "big") / 2**64
    if position < test:
        return TEST
    if position < test + val:
        return VAL
    return TRAIN


@dataclass(frozen=True)
class Assignment:
    item: str
    source: str
    group: str
    split: str


def esc50(filename: str, fold: int) -> Assignment:
    return Assignment(filename, "esc50", f"esc50-fold{fold}", ESC50_FOLDS[fold])


def librispeech(path: str) -> Assignment:
    """Path like LibriSpeech/dev-clean/<speaker>/<chapter>/<file>.flac."""
    parts = PurePosixPath(path).parts
    index = parts.index("LibriSpeech")
    subset, speaker = parts[index + 1], parts[index + 2]
    return Assignment(path, "librispeech", f"librispeech-spk{speaker}", LIBRISPEECH_SUBSETS[subset])


def freesound(item: str, username: str, test_set_uploaders: Iterable[str] = ()) -> Assignment:
    group = f"freesound-user:{username.lower()}"
    if username.lower() in {name.lower() for name in test_set_uploaders}:
        return Assignment(item, "freesound", group, TEST)
    return Assignment(item, "freesound", group, hashed_split(group))


def musan(path: str) -> Assignment:
    group = f"musan:{PurePosixPath(path).stem}"
    return Assignment(path, "musan", group, hashed_split(group))


def rir(path: str) -> Assignment:
    """Group simulated rooms by Room folder and real ones by recording session."""
    pure = PurePosixPath(path)
    if "simulated_rirs" in pure.parts:
        room = "/".join(pure.parts[-3:-1])
    else:
        room = "_".join(pure.stem.split("_")[:4])
    group = f"rir:{room}"
    return Assignment(path, "rirs", group, hashed_split(group))


def leaks(assignments: Iterable[Assignment]) -> dict[str, set[str]]:
    """Return every group that appears in more than one split."""
    splits_by_group: dict[str, set[str]] = defaultdict(set)
    for assignment in assignments:
        splits_by_group[assignment.group].add(assignment.split)
    return {group: splits for group, splits in splits_by_group.items() if len(splits) > 1}


def test_set_uploader_leaks(
    assignments: Iterable[Assignment], test_set_uploaders: Iterable[str]
) -> list[str]:
    """Return items from a test-set uploader that ended up in train or val."""
    blocked = {f"freesound-user:{name.lower()}" for name in test_set_uploaders}
    return [a.item for a in assignments if a.group in blocked and a.split != TEST]


def counts(assignments: Iterable[Assignment]) -> Mapping[str, Mapping[str, int]]:
    table: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(SPLITS, 0))
    for assignment in assignments:
        table[assignment.source][assignment.split] += 1
    return dict(table)
