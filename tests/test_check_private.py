"""The privacy guard blocks private files, in unit tests and in real pushes."""

import subprocess
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scripts import check_private

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / ".githooks"


@pytest.mark.parametrize(
    "path",
    [
        "private/recordings/clip_01.m4a",
        "private/notes.txt",
        "docs/private/consent.pdf",
        "kaggle_outputs/K1_bank/manifest.json",
        "Private/x.txt",
        ".env",
        "api/.env.local",
        "clip_log.csv",
        "docs/recording/tester_log.csv",
        "stray.wav",
        "eval/VOICE_NOTE.OPUS",
        "video.mp4",
        "CLAUDE.md",
        "claude.md",
        ".claude/settings.json",
        "docs/PLAN.md",
        "docs/BUILD_PROTOCOL.md",
        "docs/PROGRESS.md",
    ],
)
def test_blocked_paths(path: str) -> None:
    assert check_private.block_reason(path) is not None


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        ".env.example",
        "docs/recording/consent_note.md",
        "docs/recording/clip_log_template.csv",
        "docs/testers/tester_log_template.csv",
        "scripts/check_private.py",
        "private.md",
        "wav_notes.txt",
        "docs/setup_accounts.md",
        "notes/CLAUDE.md.txt",
    ],
)
def test_allowed_paths(path: str) -> None:
    assert check_private.block_reason(path) is None


@given(
    folder=st.text(alphabet="abcdefgh/", min_size=0, max_size=12),
    suffix=st.sampled_from(sorted(check_private.MEDIA_SUFFIXES)),
)
def test_every_media_type_is_blocked_at_any_depth(folder: str, suffix: str) -> None:
    assert check_private.block_reason(f"{folder}/clip{suffix.upper()}") is not None


def test_env_example_with_empty_values_is_clean() -> None:
    assert check_private.env_example_problems("# comment\nGEMINI_API_KEY=\n\nHF_TOKEN=  \n") == []


def test_env_example_with_a_value_is_reported() -> None:
    problems = check_private.env_example_problems("A=\nGEMINI_API_KEY=abc123\n")
    assert problems == [".env.example line 2: GEMINI_API_KEY has a value"]


def test_repo_env_example_holds_no_keys() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "FREESOUND_API_KEY=" in text
    assert check_private.env_example_problems(text) == []


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def commit(work: Path, name: str, content: str) -> None:
    target = work / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    git(work, "add", "-f", name)
    git(work, "commit", "-m", f"add {name}")


def remote_has(work: Path, name: str) -> bool:
    git(work, "fetch", "origin")
    return name in git(work, "ls-tree", "-r", "--name-only", "origin/main").stdout


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    """A clone of a local bare remote, using the real pre-push hook."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    git(tmp_path, "clone", str(remote), str(work))
    git(work, "config", "core.hooksPath", HOOKS.as_posix())
    git(work, "checkout", "-B", "main")
    commit(work, "README.md", "hello")
    assert git(work, "push", "origin", "main", check=False).returncode == 0
    return work


def test_hook_allows_a_clean_push(clone: Path) -> None:
    commit(clone, "notes.md", "fine")
    assert git(clone, "push", "origin", "main", check=False).returncode == 0
    assert remote_has(clone, "notes.md")


@pytest.mark.parametrize("name", ["private/consent.txt", ".env", "docs/clip.wav"])
def test_hook_blocks_a_private_file(clone: Path, name: str) -> None:
    commit(clone, name, "secret")
    result = git(clone, "push", "origin", "main", check=False)
    assert result.returncode != 0
    assert "BLOCKED" in result.stderr
    assert not remote_has(clone, name)


def test_hook_blocks_a_file_added_then_deleted(clone: Path) -> None:
    commit(clone, "private/consent.txt", "secret")
    git(clone, "rm", "private/consent.txt")
    git(clone, "commit", "-m", "remove it")
    assert git(clone, "push", "origin", "main", check=False).returncode != 0


def test_hook_allows_removing_a_file_that_was_pushed_by_mistake(clone: Path) -> None:
    commit(clone, "CLAUDE.md", "notes")
    assert git(clone, "push", "--no-verify", "origin", "main", check=False).returncode == 0
    git(clone, "rm", "--cached", "CLAUDE.md")
    git(clone, "commit", "-m", "stop tracking it")
    assert git(clone, "push", "origin", "main", check=False).returncode == 0
    assert not remote_has(clone, "CLAUDE.md")


def test_hook_blocks_a_local_only_file(clone: Path) -> None:
    commit(clone, "docs/PLAN.md", "plan")
    result = git(clone, "push", "origin", "main", check=False)
    assert result.returncode != 0
    assert "local-only working file" in result.stderr


def test_hook_blocks_a_filled_in_env_example(clone: Path) -> None:
    commit(clone, ".env.example", "GEMINI_API_KEY=abc123\n")
    result = git(clone, "push", "origin", "main", check=False)
    assert result.returncode != 0
    assert "GEMINI_API_KEY has a value" in result.stderr


def test_hook_checks_a_push_of_a_single_commit(clone: Path) -> None:
    commit(clone, "private/first.txt", "secret")
    sha = git(clone, "rev-parse", "HEAD").stdout.strip()
    assert git(clone, "push", "origin", f"{sha}:refs/heads/main", check=False).returncode != 0


def test_history_mode_finds_a_deleted_file(clone: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commit(clone, "private/consent.txt", "secret")
    git(clone, "rm", "private/consent.txt")
    git(clone, "commit", "-m", "remove it")
    monkeypatch.chdir(clone)
    assert check_private.main(["--history"]) == 1
    assert check_private.main([]) == 0


def test_git_failure_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert check_private.main([]) == 2
