"""Confirm the repo has the planned folders and ignores private paths.

Standard library only. Exit code 0 means the layout is correct.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REQUIRED_DIRS = (
    "extension",
    "web",
    "packages/engine",
    "api",
    "ml",
    "synth",
    "eval",
    "kaggle/notebooks",
    "models",
    "scripts",
    "docs",
)
REQUIRED_FILES = (
    "CLAUDE.md",
    "README.md",
    "docs/PLAN.md",
    "docs/PROGRESS.md",
    "docs/BUILD_PROTOCOL.md",
)
MUST_BE_IGNORED = (
    "private/recordings/clip.wav",
    "private/testers/tester_log.csv",
    "kaggle_outputs/K1_x/manifest.json",
    ".env",
    ".env.local",
    "stray_recording.m4a",
)
MUST_NOT_BE_IGNORED = (".env.example",)


def is_ignored(root: Path, path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path],
        cwd=root,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git check-ignore failed for {path}")
    return result.returncode == 0


def find_problems(root: Path) -> list[str]:
    problems = [f"missing folder: {d}" for d in REQUIRED_DIRS if not (root / d).is_dir()]
    problems += [f"missing file: {f}" for f in REQUIRED_FILES if not (root / f).is_file()]
    problems += [f"not ignored: {p}" for p in MUST_BE_IGNORED if not is_ignored(root, p)]
    problems += [f"wrongly ignored: {p}" for p in MUST_NOT_BE_IGNORED if is_ignored(root, p)]
    return problems


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    problems = find_problems(root)
    for problem in problems:
        print(f"FAIL {problem}")
    if not problems:
        checked = (
            len(REQUIRED_DIRS)
            + len(REQUIRED_FILES)
            + len(MUST_BE_IGNORED)
            + len(MUST_NOT_BE_IGNORED)
        )
        print(f"OK layout: {checked} checks passed")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
