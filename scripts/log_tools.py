"""Shared helpers for the CSV logs kept in private/."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def read_rows(path: Path, columns: Sequence[str]) -> tuple[list[dict[str, str]], list[str]]:
    """Read a log. Return (rows, problems); rows is empty if the file is unusable.

    utf-8-sig accepts the invisible marker Excel adds to "CSV UTF-8" files.
    Rows that are completely blank are skipped, because spreadsheets often add them.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return [], [f"{path.name}: not UTF-8. In Excel, use Save As > CSV UTF-8."]

    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = list(reader.fieldnames or [])
    if header != list(columns):
        missing = [c for c in columns if c not in header]
        extra = [c for c in header if c not in columns]
        detail = f"missing {missing}, unexpected {extra}" if missing or extra else "wrong order"
        return [], [f"{path.name}: columns do not match the template ({detail})"]

    rows: list[dict[str, str]] = []
    problems: list[str] = []
    for number, raw in enumerate(reader, start=2):
        if raw.get(None):
            problems.append(f"line {number}: more cells than columns")
            continue
        row = {key: (value or "").strip() for key, value in raw.items()}
        if any(row.values()):
            rows.append(row)
    return rows, problems


def date_problem(value: str, today: date) -> str | None:
    """Return what is wrong with a YYYY-MM-DD date, or None if it is valid."""
    if not ISO_DATE.fullmatch(value):
        return f"date must be YYYY-MM-DD, got '{value}'"
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return f"not a real date: '{value}'"
    return f"date is in the future: '{value}'" if parsed > today else None
