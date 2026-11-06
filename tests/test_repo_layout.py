"""The repo has its planned folders and ignores private paths."""

from pathlib import Path

from scripts import check_layout

ROOT = Path(__file__).resolve().parent.parent


def test_repo_layout_is_correct() -> None:
    assert check_layout.find_problems(ROOT) == []


def test_missing_folder_is_reported(tmp_path: Path) -> None:
    problems = check_layout.find_problems_in_dirs(tmp_path)
    assert "missing folder: extension" in problems
    assert "missing file: CLAUDE.md" in problems
