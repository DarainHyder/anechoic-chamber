"""Validate the tester log and count booked testers.

    python -m scripts.check_testers               validate private/testers/tester_log.csv
    python -m scripts.check_testers --gate        also require 5 to 10 booked testers
    python -m scripts.check_testers --log PATH    validate another log

The log holds codes only. Contact details stay in a separate private file. This
script catches name columns, emails, phone numbers and handles, but it cannot
recognise a name typed into free text, so keep names out of the notes yourself.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from scripts.log_tools import date_problem, read_rows

COLUMNS = (
    "tester_id",
    "status",
    "adult_confirmed",
    "consent_given",
    "consent_date",
    "main_triggers",
    "avoid_sounds",
    "notes",
)
STATUSES = {"invited", "booked", "withdrawn"}
TESTER_ID = re.compile(r"T\d{2}")
EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
HANDLE = re.compile(r"(^|\s)(@\w+|u/\w+)")
PHONE_LIKE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
PHONE_MIN_DIGITS = 10
DEFAULT_LOG = Path("private/testers/tester_log.csv")
GATE_MIN = 5
GATE_MAX = 10


@dataclass
class Report:
    booked: int = 0
    invited: int = 0
    withdrawn: int = 0
    trigger_mentions: int = 0
    problems: list[str] = field(default_factory=list)


def contact_detail_in(text: str) -> str | None:
    """Return the kind of contact detail found in the text, if any."""
    if EMAIL.search(text):
        return "email address"
    if HANDLE.search(text):
        return "username"
    for match in PHONE_LIKE.finditer(text):
        if sum(character.isdigit() for character in match.group()) >= PHONE_MIN_DIGITS:
            return "phone number"
    return None


def split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def row_problems(row: dict[str, str], today: date) -> list[str]:
    """Return everything wrong with one row, ignoring duplicates across rows."""
    problems = []
    if not TESTER_ID.fullmatch(row["tester_id"]):
        problems.append("tester_id must look like T01")
    if row["status"] not in STATUSES:
        problems.append(f"status must be one of {sorted(STATUSES)}")

    for column, value in row.items():
        kind = contact_detail_in(value)
        if kind:
            problems.append(f"{column} contains a {kind}; keep contact details out of this log")

    if row["status"] == "booked":
        if row["adult_confirmed"] != "yes":
            problems.append("adult_confirmed must be yes; testers must be 18 or over")
        if row["consent_given"] != "yes":
            problems.append("consent_given must be yes before booking")
        problem = date_problem(row["consent_date"], today)
        if problem:
            problems.append(f"consent_date: {problem}")
        if not split_list(row["main_triggers"]):
            problems.append("main_triggers is empty")
    return problems


def check_log(log: Path, today: date | None = None) -> Report:
    report = Report()
    if not log.is_file():
        report.problems.append(f"no log found at {log}")
        return report

    today = today or date.today()
    rows, report.problems = read_rows(log, COLUMNS)
    seen_ids: set[str] = set()

    for row in rows:
        problems = row_problems(row, today)
        if row["tester_id"] in seen_ids:
            problems.append("duplicate tester_id")
        seen_ids.add(row["tester_id"])

        label = row["tester_id"] or "no id"
        report.problems.extend(f"{label}: {problem}" for problem in problems)
        if problems:
            continue
        if row["status"] == "booked":
            report.booked += 1
            report.trigger_mentions += len(split_list(row["main_triggers"]))
        elif row["status"] == "invited":
            report.invited += 1
        else:
            report.withdrawn += 1
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the tester log.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument(
        "--gate", action="store_true", help=f"require {GATE_MIN} to {GATE_MAX} booked testers"
    )
    args = parser.parse_args(argv)

    report = check_log(args.log)
    for problem in report.problems:
        print(f"FAIL {problem}")
    print(
        f"Booked: {report.booked}, invited: {report.invited}, withdrawn: {report.withdrawn}, "
        f"triggers recorded: {report.trigger_mentions}"
    )

    if report.problems:
        return 1
    if args.gate and not GATE_MIN <= report.booked <= GATE_MAX:
        print(f"FAIL gate: {report.booked} booked, target is {GATE_MIN} to {GATE_MAX}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
