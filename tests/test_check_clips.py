"""The clip-log checker accepts good logs and rejects unusable ones."""

import csv
from datetime import date
from pathlib import Path

import pytest

from scripts import check_clips

ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 11, 6)


def good_row(number: int = 1) -> dict[str, str]:
    return {
        "clip_id": f"C{number:04d}",
        "file": f"clip_{number:04d}.m4a",
        "trigger": "chewing_eating",
        "session_id": "S01",
        "recorded_on": "2026-11-05",
        "room": "kitchen",
        "device": "phone_a",
        "people": "self;P01",
        "consent_given": "yes",
        "consent_note": "signed form 2026-11-05",
        "contains_speech": "no",
        "notes": "",
    }


def write_log(folder: Path, rows: list[dict[str, str]], make_files: bool = True) -> Path:
    clips = folder / "clips"
    clips.mkdir(exist_ok=True)
    log = folder / "clip_log.csv"
    with log.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=check_clips.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    if make_files:
        for row in rows:
            name = row["file"]
            if name and name == Path(name).name:
                (clips / name).write_bytes(b"audio")
    return log


def problems_for(tmp_path: Path, **changes: str) -> list[str]:
    log = write_log(tmp_path, [good_row() | changes])
    return check_clips.check_log(log, TODAY).problems


def test_good_log_is_valid(tmp_path: Path) -> None:
    report = check_clips.check_log(write_log(tmp_path, [good_row(1), good_row(2)]), TODAY)
    assert report.problems == []
    assert report.valid == 2
    assert report.by_trigger["chewing_eating"] == 2
    assert report.sessions == {"S01"}


@pytest.mark.parametrize(
    ("column", "value", "expected"),
    [
        ("clip_id", "1", "clip_id"),
        ("trigger", "burping", "trigger"),
        ("session_id", "", "session_id"),
        ("recorded_on", "06/11/2026", "YYYY-MM-DD"),
        ("recorded_on", "2026-02-30", "not a real date"),
        ("recorded_on", "2026-11-07", "future"),
        ("room", "", "room"),
        ("device", "", "device"),
        ("people", "Ali", "never names"),
        ("people", "", "never names"),
        ("consent_given", "no", "consent_given"),
        ("consent_given", "", "consent_given"),
        ("consent_note", "", "consent_note"),
        ("contains_speech", "maybe", "contains_speech"),
        ("file", "../outside.m4a", "plain file name"),
        ("file", "notes.txt", "audio type"),
    ],
)
def test_bad_values_are_rejected(tmp_path: Path, column: str, value: str, expected: str) -> None:
    problems = problems_for(tmp_path, **{column: value})
    assert any(expected in problem for problem in problems), problems


def test_missing_audio_file_is_rejected(tmp_path: Path) -> None:
    log = write_log(tmp_path, [good_row()], make_files=False)
    report = check_clips.check_log(log, TODAY)
    assert report.valid == 0
    assert "file not found" in report.problems[0]


def test_empty_audio_file_is_rejected(tmp_path: Path) -> None:
    log = write_log(tmp_path, [good_row()])
    (tmp_path / "clips" / "clip_0001.m4a").write_bytes(b"")
    assert "file is empty" in check_clips.check_log(log, TODAY).problems[0]


def test_duplicate_id_and_file_are_rejected(tmp_path: Path) -> None:
    report = check_clips.check_log(write_log(tmp_path, [good_row(), good_row()]), TODAY)
    assert report.valid == 1
    assert any("duplicate clip_id" in problem for problem in report.problems)
    assert any("already logged" in problem for problem in report.problems)


def test_unlogged_clip_is_reported(tmp_path: Path) -> None:
    log = write_log(tmp_path, [good_row()])
    (tmp_path / "clips" / "no_consent.m4a").write_bytes(b"audio")
    assert check_clips.check_log(log, TODAY).problems == [
        "no_consent.m4a: in clips/ but not in the log"
    ]


def test_excel_utf8_marker_and_blank_rows_are_tolerated(tmp_path: Path) -> None:
    log = write_log(tmp_path, [good_row()])
    text = log.read_text(encoding="utf-8")
    log.write_text("﻿" + text + ",,,,,,,,,,,\n", encoding="utf-8")
    report = check_clips.check_log(log, TODAY)
    assert report.problems == []
    assert report.valid == 1


def test_extra_column_is_rejected(tmp_path: Path) -> None:
    log = tmp_path / "clip_log.csv"
    log.write_text(",".join(check_clips.COLUMNS) + ",full_name\n", encoding="utf-8")
    assert "columns do not match" in check_clips.check_log(log, TODAY).problems[0]


def test_non_utf8_file_is_rejected(tmp_path: Path) -> None:
    log = tmp_path / "clip_log.csv"
    log.write_bytes(b"clip_id,caf\xe9\n")
    assert "not UTF-8" in check_clips.check_log(log, TODAY).problems[0]


def test_row_with_too_many_cells_is_rejected(tmp_path: Path) -> None:
    log = write_log(tmp_path, [])
    with log.open("a", encoding="utf-8") as handle:
        handle.write("a,b,c,d,e,f,g,h,i,j,k,l,too_many\n")
    assert "more cells than columns" in check_clips.check_log(log, TODAY).problems[0]


def test_missing_log_is_reported(tmp_path: Path) -> None:
    assert "no log found" in check_clips.check_log(tmp_path / "none.csv", TODAY).problems[0]


def test_gate_needs_100_valid_clips(tmp_path: Path) -> None:
    rows = [good_row(number) for number in range(1, 100)]
    log = write_log(tmp_path, rows)
    assert check_clips.main(["--log", str(log)]) == 0
    assert check_clips.main(["--log", str(log), "--gate"]) == 1

    log = write_log(tmp_path, [*rows, good_row(100)])
    assert check_clips.main(["--log", str(log), "--gate"]) == 0


def test_gate_fails_on_any_problem(tmp_path: Path) -> None:
    rows = [good_row(number) for number in range(1, 101)]
    rows[0]["consent_given"] = "no"
    assert check_clips.main(["--log", str(write_log(tmp_path, rows)), "--gate"]) == 1


def test_template_matches_the_checker() -> None:
    template = ROOT / "docs" / "recording" / "clip_log_template.csv"
    assert template.read_text(encoding="utf-8").strip() == ",".join(check_clips.COLUMNS)
