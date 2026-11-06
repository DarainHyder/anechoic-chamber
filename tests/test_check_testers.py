"""The tester-log checker counts booked testers and keeps the log anonymous."""

import csv
from datetime import date
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scripts import check_testers

ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 11, 6)


def good_row(number: int = 1) -> dict[str, str]:
    return {
        "tester_id": f"T{number:02d}",
        "status": "booked",
        "adult_confirmed": "yes",
        "consent_given": "yes",
        "consent_date": "2026-11-05",
        "main_triggers": "chewing; sniffing",
        "avoid_sounds": "",
        "notes": "",
    }


def write_log(folder: Path, rows: list[dict[str, str]]) -> Path:
    log = folder / "tester_log.csv"
    with log.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=check_testers.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return log


def test_good_log_is_valid(tmp_path: Path) -> None:
    report = check_testers.check_log(write_log(tmp_path, [good_row(1), good_row(2)]), TODAY)
    assert report.problems == []
    assert report.booked == 2
    assert report.trigger_mentions == 4


@pytest.mark.parametrize(
    ("column", "value", "expected"),
    [
        ("tester_id", "Sara", "tester_id"),
        ("status", "maybe", "status"),
        ("adult_confirmed", "no", "18 or over"),
        ("adult_confirmed", "", "18 or over"),
        ("consent_given", "", "consent_given"),
        ("consent_date", "yesterday", "YYYY-MM-DD"),
        ("main_triggers", " ; ", "main_triggers"),
        ("notes", "reach me at someone@example.com", "email address"),
        ("notes", "call +92 300 1234567", "phone number"),
        ("notes", "found via u/someone", "username"),
        ("avoid_sounds", "ask @someone first", "username"),
    ],
)
def test_bad_values_are_rejected(tmp_path: Path, column: str, value: str, expected: str) -> None:
    log = write_log(tmp_path, [good_row() | {column: value}])
    report = check_testers.check_log(log, TODAY)
    assert report.booked == 0
    assert any(expected in problem for problem in report.problems), report.problems


def test_name_column_is_rejected(tmp_path: Path) -> None:
    log = tmp_path / "tester_log.csv"
    log.write_text("full_name," + ",".join(check_testers.COLUMNS) + "\n", encoding="utf-8")
    assert "columns do not match" in check_testers.check_log(log, TODAY).problems[0]


def test_duplicate_id_is_rejected(tmp_path: Path) -> None:
    report = check_testers.check_log(write_log(tmp_path, [good_row(), good_row()]), TODAY)
    assert report.booked == 1
    assert any("duplicate tester_id" in problem for problem in report.problems)


def test_invited_and_withdrawn_are_not_booked(tmp_path: Path) -> None:
    blank = dict.fromkeys(check_testers.COLUMNS, "")
    rows = [
        good_row(1),
        blank | {"tester_id": "T02", "status": "invited"},
        blank | {"tester_id": "T03", "status": "withdrawn"},
    ]
    report = check_testers.check_log(write_log(tmp_path, rows), TODAY)
    assert report.problems == []
    assert (report.booked, report.invited, report.withdrawn) == (1, 1, 1)


def test_contact_details_are_rejected_on_invited_rows(tmp_path: Path) -> None:
    blank = dict.fromkeys(check_testers.COLUMNS, "")
    row = blank | {"tester_id": "T02", "status": "invited", "notes": "a@b.co"}
    report = check_testers.check_log(write_log(tmp_path, [row]), TODAY)
    assert report.invited == 0
    assert "email address" in report.problems[0]


@given(st.emails())
def test_any_email_is_detected(email: str) -> None:
    assert check_testers.contact_detail_in(f"contact {email} please") == "email address"


@pytest.mark.parametrize("text", ["2026-11-05", "chewing; sniffing", "rated 8 of 10", ""])
def test_ordinary_text_is_not_a_contact_detail(text: str) -> None:
    assert check_testers.contact_detail_in(text) is None


@pytest.mark.parametrize(
    ("booked", "expected"), [(4, 1), (5, 0), (10, 0), (11, 1)], ids=["4", "5", "10", "11"]
)
def test_gate_needs_5_to_10_booked(tmp_path: Path, booked: int, expected: int) -> None:
    log = write_log(tmp_path, [good_row(number) for number in range(1, booked + 1)])
    assert check_testers.main(["--log", str(log), "--gate"]) == expected


def test_template_matches_the_checker() -> None:
    template = ROOT / "docs" / "testers" / "tester_log_template.csv"
    assert template.read_text(encoding="utf-8").strip() == ",".join(check_testers.COLUMNS)
