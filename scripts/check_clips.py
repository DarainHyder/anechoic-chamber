"""Validate the local recording log and count usable clips.

    python -m scripts.check_clips                 validate private/recordings/clip_log.csv
    python -m scripts.check_clips --gate          also require the Phase 0 target of 100 clips
    python -m scripts.check_clips --log PATH      validate another log

The clips live in a folder named clips/ next to the log. See docs/recording/guide.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from scripts.log_tools import date_problem, read_rows

COLUMNS = (
    "clip_id",
    "file",
    "trigger",
    "session_id",
    "recorded_on",
    "room",
    "device",
    "people",
    "consent_given",
    "consent_note",
    "contains_speech",
    "notes",
)
TRIGGERS = {"chewing_eating", "sniffing_breathing", "clicks", "typing"}
AUDIO_SUFFIXES = {".3gp", ".aac", ".amr", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"}
CLIP_ID = re.compile(r"C\d{4}")
SESSION_ID = re.compile(r"S\d{2,3}")
PERSON = re.compile(r"self|P\d{2}")
DEFAULT_LOG = Path("private/recordings/clip_log.csv")
GATE_TARGET = 100


@dataclass
class Report:
    valid: int = 0
    by_trigger: Counter[str] = field(default_factory=Counter)
    sessions: set[str] = field(default_factory=set)
    problems: list[str] = field(default_factory=list)


def row_problems(row: dict[str, str], clips_dir: Path, today: date) -> list[str]:
    """Return everything wrong with one row, ignoring duplicates across rows."""
    problems = []
    if not CLIP_ID.fullmatch(row["clip_id"]):
        problems.append("clip_id must look like C0001")

    name = row["file"]
    if not name or name != Path(name).name or "\\" in name:
        problems.append("file must be a plain file name inside clips/")
    elif Path(name).suffix.lower() not in AUDIO_SUFFIXES:
        problems.append(f"file is not a known audio type: {name}")
    elif not (clips_dir / name).is_file():
        problems.append(f"file not found in clips/: {name}")
    elif (clips_dir / name).stat().st_size == 0:
        problems.append(f"file is empty: {name}")

    if row["trigger"] not in TRIGGERS:
        problems.append(f"trigger must be one of {sorted(TRIGGERS)}")
    if not SESSION_ID.fullmatch(row["session_id"]):
        problems.append("session_id must look like S01")

    problem = date_problem(row["recorded_on"], today)
    if problem:
        problems.append(f"recorded_on: {problem}")

    for column in ("room", "device"):
        if not row[column]:
            problems.append(f"{column} is empty")

    people = [person.strip() for person in row["people"].split(";")]
    if not all(PERSON.fullmatch(person) for person in people):
        problems.append("people must be codes such as self or P01;P02, never names")

    if row["consent_given"] != "yes":
        problems.append("consent_given must be yes; do not log clips without consent")
    if not row["consent_note"]:
        problems.append("consent_note is empty")
    if row["contains_speech"] not in {"yes", "no"}:
        problems.append("contains_speech must be yes or no")
    return problems


def check_log(log: Path, today: date | None = None) -> Report:
    report = Report()
    if not log.is_file():
        report.problems.append(f"no log found at {log}")
        return report

    today = today or date.today()
    clips_dir = log.parent / "clips"
    rows, report.problems = read_rows(log, COLUMNS)
    seen_ids: set[str] = set()
    seen_files: set[str] = set()

    for row in rows:
        problems = row_problems(row, clips_dir, today)
        if row["clip_id"] in seen_ids:
            problems.append("duplicate clip_id")
        if row["file"].lower() in seen_files:
            problems.append("this file is already logged")
        seen_ids.add(row["clip_id"])
        seen_files.add(row["file"].lower())

        label = row["clip_id"] or "no id"
        report.problems.extend(f"{label}: {problem}" for problem in problems)
        if not problems:
            report.valid += 1
            report.by_trigger[row["trigger"]] += 1
            report.sessions.add(row["session_id"])

    if clips_dir.is_dir():
        for path in sorted(clips_dir.iterdir()):
            if path.is_file() and path.name.lower() not in seen_files:
                report.problems.append(f"{path.name}: in clips/ but not in the log")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the local recording log.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--gate", action="store_true", help=f"require {GATE_TARGET} valid clips")
    args = parser.parse_args(argv)

    report = check_log(args.log)
    for problem in report.problems:
        print(f"FAIL {problem}")
    print(f"Valid clips: {report.valid} across {len(report.sessions)} sessions")
    for trigger in sorted(TRIGGERS):
        print(f"  {trigger}: {report.by_trigger[trigger]}")

    if report.problems:
        return 1
    if args.gate and report.valid < GATE_TARGET:
        print(f"FAIL gate: {report.valid} of {GATE_TARGET} clips")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
