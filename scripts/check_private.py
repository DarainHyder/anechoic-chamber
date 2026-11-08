"""Stop private material reaching the public repo.

Standard library only, so the pre-push hook runs without the virtual environment.

    python scripts/check_private.py             check files in the current commit
    python scripts/check_private.py --history   check every file in all history (CI)
    python scripts/check_private.py --pre-push  check commits being pushed (git hook)

Exit code 0 means clean. Any failure, including a git error, blocks the push.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable
from pathlib import PurePosixPath

BLOCKED_DIRS = {"private", "kaggle_outputs"}
BLOCKED_NAMES = {"clip_log.csv", "tester_log.csv"}
# Local working files for the coding assistant: kept on the developer's machine only.
LOCAL_ONLY_PATHS = {"claude.md", "docs/plan.md", "docs/build_protocol.md", "docs/progress.md"}
LOCAL_ONLY_DIRS = {".claude"}
MEDIA_SUFFIXES = {
    ".3gp",
    ".aac",
    ".aif",
    ".aiff",
    ".amr",
    ".flac",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".oga",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
    ".wma",
}
ENV_EXAMPLE = ".env.example"


def block_reason(path: str) -> str | None:
    """Return why a repo path must not be pushed, or None if it is allowed."""
    parts = PurePosixPath(path).parts
    name = parts[-1].lower()
    if BLOCKED_DIRS.intersection(part.lower() for part in parts[:-1]):
        return "inside a private folder"
    if PurePosixPath(path).as_posix().lower() in LOCAL_ONLY_PATHS or LOCAL_ONLY_DIRS.intersection(
        part.lower() for part in parts[:-1]
    ):
        return "a local-only working file"
    if name in BLOCKED_NAMES:
        return "a real clip or tester log"
    if name == ".env" or (name.startswith(".env.") and name != ENV_EXAMPLE):
        return "an environment file that may hold keys"
    if PurePosixPath(name).suffix in MEDIA_SUFFIXES:
        return "an audio or video file"
    return None


def env_example_problems(text: str) -> list[str]:
    """Return a problem for each line of .env.example that holds a value."""
    problems = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if separator and value.strip():
            problems.append(f"{ENV_EXAMPLE} line {number}: {key.strip()} has a value")
    return problems


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, check=True, encoding="utf-8", errors="replace"
    )
    return result.stdout


def split_paths(output: str) -> set[str]:
    return {path.strip("\n") for path in output.split("\0") if path.strip("\n")}


def paths_in_commits(*revisions: str) -> set[str]:
    """Return every path added or changed by the commits, including ones later deleted.

    Deletions are left out, so removing a file that should never have been pushed is allowed.
    """
    return split_paths(
        git("log", "-m", "--name-only", "--diff-filter=d", "--format=", "-z", *revisions)
    )


def env_example_at(revision: str) -> str | None:
    tracked = git("ls-tree", "--name-only", revision, "--", ENV_EXAMPLE)
    return git("show", f"{revision}:{ENV_EXAMPLE}") if tracked.strip() else None


def find_problems(paths: Iterable[str], revision: str) -> list[str]:
    problems = []
    for path in sorted(paths):
        reason = block_reason(path)
        if reason:
            problems.append(f"{path}: {reason}")
    text = env_example_at(revision)
    if text is not None:
        problems.extend(env_example_problems(text))
    return problems


def is_zero(sha: str) -> bool:
    return set(sha) == {"0"}


def check_pre_push(lines: Iterable[str]) -> list[str]:
    """Check the refs git passes to the hook: local_ref local_sha remote_ref remote_sha."""
    problems: list[str] = []
    for line in lines:
        fields = line.split()
        if len(fields) != 4:
            continue
        _, local_sha, _, remote_sha = fields
        if is_zero(local_sha):
            continue  # a branch deletion uploads nothing
        if is_zero(remote_sha):
            paths = paths_in_commits(local_sha, "--not", "--remotes")
        else:
            paths = paths_in_commits(f"{remote_sha}..{local_sha}")
        problems.extend(find_problems(paths, local_sha))
    return problems


def run(history: bool, pre_push: bool) -> list[str]:
    if pre_push:
        return check_pre_push(sys.stdin)
    if history:
        return find_problems(paths_in_commits("--all"), "HEAD")
    return find_problems(split_paths(git("ls-files", "-z")), "HEAD")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stop private material reaching the public repo.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--history", action="store_true")
    group.add_argument("--pre-push", action="store_true")
    args = parser.parse_args(argv)
    try:
        problems = run(args.history, args.pre_push)
    except (subprocess.CalledProcessError, OSError) as error:
        print(f"BLOCKED: privacy check could not run: {error}", file=sys.stderr)
        return 2
    for problem in problems:
        print(f"BLOCKED: {problem}", file=sys.stderr)
    if problems:
        print("This repo is public. Remove these files before pushing.", file=sys.stderr)
        return 1
    print("OK privacy check: nothing private found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
