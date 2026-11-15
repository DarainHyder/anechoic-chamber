"""Validate Kaggle K1 outputs, then (with --apply) copy the accepted results into the repo.

    python -m scripts.ingest_K1                    check kaggle_outputs/K1_data_bank/
    python -m scripts.ingest_K1 --apply            also write the test-set lock and data card
    python -m scripts.ingest_K1 --dir PATH         check another folder

Checks: manifest present and pinned to a commit, every listed file present with a
matching sha256, no unlisted files (a sign of leftovers from another run),
required outputs present, metric sanity, the test-set lock intact, and a full
run rather than a smoke test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval import realworld
from synth import realism

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "kaggle_outputs" / "K1_data_bank"
REQUIRED = (
    "manifest.json",
    "metrics.json",
    "REPORT.md",
    "embeddings.json",
    "DATA_CARD.md",
    "DATA_ATTRIBUTION.md",
    "freesound_bank.jsonl",
    "mixture_checks.jsonl",
)
EMBEDDING_DIM = 512
PHRASES = 300


@dataclass
class Result:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(folder: Path) -> Result:
    result = Result()
    if not (folder / "manifest.json").is_file():
        result.problems.append(f"no manifest.json in {folder}")
        return result
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    if manifest.get("task") != "K1_data_bank":
        result.problems.append(
            f"manifest task is {manifest.get('task')!r}, expected 'K1_data_bank'"
        )
    commit = str(manifest.get("repo_commit", ""))
    if len(commit) != 40:
        result.problems.append("manifest is not pinned to a full commit")
    result.facts["commit"] = commit

    listed = {row["path"]: row for row in manifest.get("files", [])}
    for path, row in listed.items():
        target = folder / path
        if not target.is_file():
            result.problems.append(f"listed file missing: {path}")
        elif sha256(target) != row["sha256"]:
            result.problems.append(f"checksum mismatch: {path}")
    present = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()} - {
        "manifest.json"
    }
    unlisted = sorted(present - set(listed))
    if unlisted:
        result.problems.append(
            f"{len(unlisted)} files not in the manifest (leftovers from another run?): "
            f"{unlisted[:5]}"
        )
    for name in REQUIRED:
        if not (folder / name).is_file():
            result.problems.append(f"required output missing: {name}")
    if result.problems:
        return result

    metrics = json.loads((folder / "metrics.json").read_text(encoding="utf-8"))
    if metrics.get("smoke"):
        result.problems.append("this is a smoke-test output; run the full notebook")

    mix = metrics["mixtures"]
    checks = (folder / "mixture_checks.jsonl").read_text(encoding="utf-8").splitlines()
    if len(checks) != mix["mixtures"]:
        result.problems.append(f"{len(checks)} mixture checks for {mix['mixtures']} mixtures")
    spectrograms = len(list((folder / "spectrograms").glob("*.png")))
    expected = min(20, mix["mixtures"])
    if spectrograms != expected:
        result.problems.append(f"{spectrograms} spectrograms, expected {expected}")
    samples = len(list((folder / "samples").glob("*_mixture.wav")))
    if samples != 5:
        result.problems.append(f"{samples} sample mixtures, expected 5")

    for name, gate in realism.gate_results(mix).items():
        result.facts[name] = gate["actual"]
        if gate["passed"] is False:
            result.problems.append(f"gate {name}: {gate['actual']} against target {gate['target']}")
    result.facts["clean_trigger_detect_rate"] = mix.get("clean_trigger_detect_rate")
    leaks = metrics["leakage"]
    if leaks["groups_in_two_splits"] or leaks["test_uploaders_in_train"]:
        result.problems.append(f"leakage found: {leaks}")

    embeddings = json.loads((folder / "embeddings.json").read_text(encoding="utf-8"))
    if embeddings.get("dim") != EMBEDDING_DIM or len(embeddings.get("phrases", [])) != PHRASES:
        result.problems.append(
            f"embeddings: dim {embeddings.get('dim')}, phrases {len(embeddings.get('phrases', []))}"
        )
    missing_triggers = set(realism.TRIGGER_GROUPS) - set(embeddings.get("triggers", {}))
    if missing_triggers:
        result.problems.append(f"no CLAP centroid for {sorted(missing_triggers)}")

    lock = folder / "realworld_test_set.json"
    if not lock.is_file():
        result.problems.append("no real-world test set lock")
    else:
        try:
            clips = realworld.load_lock(lock)
        except (realworld.LockError, KeyError, ValueError) as error:
            result.problems.append(f"real-world lock invalid: {error}")
        else:
            result.facts["realworld_size"] = len(clips)
            if len(clips) < realworld.TARGET_SIZE:
                result.problems.append(
                    f"real-world test set has {len(clips)} of {realworld.TARGET_SIZE} clips"
                )
    return result


def apply(folder: Path, root: Path = ROOT) -> list[str]:
    """Copy accepted outputs into the repo. Only call after check() passed."""
    copies = {
        folder / "realworld_test_set.json": root / "eval" / "realworld_test_set.json",
        folder / "DATA_CARD.md": root / "docs" / "DATA_CARD.md",
        folder / "DATA_ATTRIBUTION.md": root / "docs" / "DATA_ATTRIBUTION.md",
        folder / "embeddings.json": root / "models" / "trigger_embeddings.json",
    }
    written = []
    for source, target in copies.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written.append(target.relative_to(root).as_posix())
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Kaggle K1 outputs.")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    result = check(args.dir)
    for name, value in result.facts.items():
        print(f"  {name}: {value}")
    for warning in result.warnings:
        print(f"WARN {warning}")
    for problem in result.problems:
        print(f"FAIL {problem}")
    samples = sorted((args.dir / "samples").glob("*_mixture.wav"))
    if samples:
        print("Samples to listen to (mixture, trigger alone, bed alone):")
        for path in samples:
            print(f"  {path}")
    if not result.ok:
        print("K1 outputs NOT accepted.")
        return 1
    print("K1 outputs accepted.")
    if args.apply:
        for path in apply(args.dir):
            print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
