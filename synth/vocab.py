"""The 300-phrase trigger vocabulary that free-text descriptions are mapped onto."""

from __future__ import annotations

import csv
from pathlib import Path

VOCAB_PATH = Path(__file__).parent / "vocab" / "trigger_phrases.tsv"
GROUPS = ("chewing_eating", "sniffing_breathing", "clicks", "typing", "other")
SIZE = 300
MIN_PER_TRIGGER = 40
MAX_WORDS = 6


def load(path: Path = VOCAB_PATH) -> list[tuple[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [(row["group"], row["phrase"]) for row in csv.DictReader(handle, delimiter="\t")]


def problems(rows: list[tuple[str, str]]) -> list[str]:
    found = []
    if len(rows) != SIZE:
        found.append(f"expected {SIZE} phrases, found {len(rows)}")
    phrases = [phrase for _, phrase in rows]
    duplicates = sorted({p for p in phrases if phrases.count(p) > 1})
    if duplicates:
        found.append(f"duplicates: {duplicates}")
    for group, phrase in rows:
        if group not in GROUPS:
            found.append(f"unknown group {group!r} for {phrase!r}")
        if phrase != phrase.strip().lower() or not phrase:
            found.append(f"not lowercase or trimmed: {phrase!r}")
        if not 1 <= len(phrase.split()) <= MAX_WORDS:
            found.append(f"too long: {phrase!r}")
    for group in GROUPS[:4]:
        count = sum(1 for g, _ in rows if g == group)
        if count < MIN_PER_TRIGGER:
            found.append(f"{group} has {count} phrases, needs {MIN_PER_TRIGGER}")
    return found
