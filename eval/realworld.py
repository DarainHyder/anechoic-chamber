"""The frozen real-world test set: Creative Commons clips of real scenes.

The repo stores only IDs, licences and checksums, never audio. Once locked, the
list carries a fingerprint; any change to it fails the tests, so the set can
never drift towards what the model happens to do well on.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from synth.licences import release_allowed

LOCK_PATH = Path(__file__).parent / "realworld_test_set.json"
TARGET_SIZE = 80
MAX_PER_UPLOADER = 2

# Freesound searches for real scenes where a trigger happens around speech.
SCENES: dict[str, tuple[str, ...]] = {
    "eating_with_speech": (
        "restaurant conversation",
        "dinner table conversation",
        "people eating talking",
        "family dinner",
        "lunch conversation",
        "cafe chatter",
        "eating and talking",
        "canteen",
    ),
    "typing_with_speech": (
        "office typing talking",
        "typing and talking",
        "office ambience keyboard",
        "call centre",
        "newsroom",
        "typing conversation",
    ),
    "sniffing_with_speech": (
        "sniffing talking",
        "sick person talking",
        "cold voice sniff",
        "blowing nose talking",
    ),
    "clicks_with_speech": (
        "pen click talking",
        "classroom ambience",
        "mouse clicking office",
        "clicking pen voice",
    ),
}
SCENE_TRIGGER = {
    "eating_with_speech": "chewing_eating",
    "typing_with_speech": "typing",
    "sniffing_with_speech": "sniffing_breathing",
    "clicks_with_speech": "clicks",
}


class LockError(RuntimeError):
    pass


@dataclass(frozen=True)
class RealWorldClip:
    freesound_id: int
    username: str
    licence: str
    source_url: str
    scene: str
    sha256: str
    duration: float
    speech_score: float
    trigger_score: float


def select(
    candidates: Iterable[RealWorldClip],
    size: int = TARGET_SIZE,
    max_per_uploader: int = MAX_PER_UPLOADER,
) -> list[RealWorldClip]:
    """Pick the clearest clips, taking scenes in turn and capping each uploader."""
    by_scene: dict[str, list[RealWorldClip]] = defaultdict(list)
    for clip in candidates:
        if release_allowed(clip.licence):
            by_scene[clip.scene].append(clip)
    for clips in by_scene.values():
        clips.sort(key=lambda c: (-min(c.speech_score, c.trigger_score), c.freesound_id))

    chosen: list[RealWorldClip] = []
    per_user: dict[str, int] = defaultdict(int)
    seen: set[int] = set()
    queues = {scene: list(clips) for scene, clips in sorted(by_scene.items())}
    while len(chosen) < size and any(queues.values()):
        for scene in sorted(queues):
            queue = queues[scene]
            while queue:
                clip = queue.pop(0)
                user = clip.username.lower()
                if clip.freesound_id in seen or per_user[user] >= max_per_uploader:
                    continue
                chosen.append(clip)
                seen.add(clip.freesound_id)
                per_user[user] += 1
                break
            if len(chosen) >= size:
                break
    return chosen


def fingerprint(clips: Sequence[RealWorldClip]) -> str:
    canonical = json.dumps(
        [asdict(c) for c in sorted(clips, key=lambda c: c.freesound_id)], sort_keys=True
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def write_lock(clips: Sequence[RealWorldClip], path: Path, created: str) -> dict[str, Any]:
    if not clips:
        raise LockError("refusing to lock an empty test set")
    bad = [c.freesound_id for c in clips if not release_allowed(c.licence)]
    if bad:
        raise LockError(f"clips without a CC0 or CC BY licence: {bad}")
    lock = {
        "version": 1,
        "created": created,
        "size": len(clips),
        "fingerprint": fingerprint(clips),
        "clips": [asdict(c) for c in sorted(clips, key=lambda c: c.freesound_id)],
    }
    path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return lock


def load_lock(path: Path = LOCK_PATH) -> list[RealWorldClip]:
    data: Mapping[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    clips = [RealWorldClip(**row) for row in data["clips"]]
    if len(clips) != data["size"] or fingerprint(clips) != data["fingerprint"]:
        raise LockError("the locked test set was changed; restore it from git")
    if any(not release_allowed(c.licence) for c in clips):
        raise LockError("the locked test set contains a clip that is not CC0 or CC BY")
    return clips


def uploaders(clips: Iterable[RealWorldClip]) -> set[str]:
    return {clip.username.lower() for clip in clips}
