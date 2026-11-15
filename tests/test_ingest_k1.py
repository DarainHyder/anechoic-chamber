"""The K1 output checker accepts a good folder and names every kind of problem."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from eval import realworld
from eval.realworld import RealWorldClip
from scripts import ingest_K1
from synth import realism

COMMIT = "a" * 40


def write_manifest(folder: Path, metrics: dict[str, Any]) -> None:
    files = [
        {
            "path": p.relative_to(folder).as_posix(),
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in sorted(folder.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    ]
    manifest = {"task": "K1_data_bank", "repo_commit": COMMIT, "metrics": metrics, "files": files}
    (folder / "manifest.json").write_text(json.dumps(manifest))


def good_metrics(mixtures: int = 200) -> dict[str, Any]:
    mix: dict[str, Any] = {
        "mixtures": mixtures,
        "clipped_count": 0,
        "tbr_in_range_rate": 1.0,
        "speech_detect_rate": 0.98,
        "trigger_detect_rate": 0.7,
        "false_trigger_rate": 0.05,
        "clean_trigger_detect_rate": 0.8,
    }
    mix["gate"] = realism.gate_results(mix)
    return {
        "smoke": False,
        "mixtures": mix,
        "leakage": {"groups_in_two_splits": 0, "test_uploaders_in_train": 0},
    }


def build(folder: Path, metrics: dict[str, Any] | None = None, clips: int = 80) -> Path:
    metrics = metrics or good_metrics()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "metrics.json").write_text(json.dumps(metrics))
    for name in ("REPORT.md", "DATA_CARD.md", "DATA_ATTRIBUTION.md", "freesound_bank.jsonl"):
        (folder / name).write_text("x")
    count = metrics["mixtures"]["mixtures"]
    (folder / "mixture_checks.jsonl").write_text("{}\n" * count)
    for i in range(min(20, count)):
        path = folder / "spectrograms" / f"{i:03d}.png"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"png")
    for i in range(5):
        path = folder / "samples" / f"{i:03d}_mixture.wav"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"wav")
    phrases = [{"group": "clicks", "phrase": f"p{i}", "vector": [0.0]} for i in range(300)]
    triggers = {g: {"clips": 10, "vector": [0.0]} for g in realism.TRIGGER_GROUPS}
    (folder / "embeddings.json").write_text(
        json.dumps({"dim": 512, "phrases": phrases, "triggers": triggers})
    )
    test_set = [
        RealWorldClip(i, f"user{i}", "CC0-1.0", f"https://freesound.org/s/{i}/",
                      "eating_with_speech", "ab" * 32, 10.0, 0.9, 0.5)
        for i in range(clips)
    ]  # fmt: skip
    realworld.write_lock(test_set, folder / "realworld_test_set.json", "2026-11-15")
    write_manifest(folder, metrics)
    return folder


def problems(folder: Path) -> list[str]:
    return ingest_K1.check(folder).problems


def test_a_good_folder_is_accepted(tmp_path: Path) -> None:
    result = ingest_K1.check(build(tmp_path / "out"))
    assert result.problems == []
    assert result.facts["realworld_size"] == 80
    assert result.facts["clean_trigger_detect_rate"] == 0.8


def test_missing_manifest(tmp_path: Path) -> None:
    assert "no manifest.json" in problems(tmp_path)[0]


def test_checksum_mismatch_and_missing_file(tmp_path: Path) -> None:
    folder = build(tmp_path / "out")
    (folder / "REPORT.md").write_text("changed")
    (folder / "DATA_CARD.md").unlink()
    found = problems(folder)
    assert any("checksum mismatch: REPORT.md" in p for p in found)
    assert any("listed file missing: DATA_CARD.md" in p for p in found)


def test_leftover_files_from_another_run_are_caught(tmp_path: Path) -> None:
    folder = build(tmp_path / "out")
    (folder / "spectrograms" / "999.png").write_bytes(b"old")
    assert any("not in the manifest" in p for p in problems(folder))


def test_smoke_output_is_not_accepted(tmp_path: Path) -> None:
    metrics = good_metrics()
    metrics["smoke"] = True
    assert any("smoke-test output" in p for p in problems(build(tmp_path / "out", metrics)))


def test_failed_gate_is_reported(tmp_path: Path) -> None:
    metrics = good_metrics()
    metrics["mixtures"]["trigger_detect_rate"] = 0.29
    metrics["mixtures"]["gate"] = realism.gate_results(metrics["mixtures"])
    found = problems(build(tmp_path / "out", metrics))
    assert any("gate trigger_detect_rate: 0.29" in p for p in found)


def test_short_test_set_is_reported(tmp_path: Path) -> None:
    found = problems(build(tmp_path / "out", clips=3))
    assert any("3 of 80 clips" in p for p in found)


def test_tampered_lock_is_reported(tmp_path: Path) -> None:
    folder = build(tmp_path / "out")
    lock = json.loads((folder / "realworld_test_set.json").read_text())
    lock["clips"][0]["scene"] = "typing_with_speech"
    (folder / "realworld_test_set.json").write_text(json.dumps(lock))
    write_manifest(folder, good_metrics())
    assert any("lock invalid" in p for p in problems(folder))


def test_leakage_and_bad_embeddings_are_reported(tmp_path: Path) -> None:
    metrics = good_metrics()
    metrics["leakage"]["groups_in_two_splits"] = 2
    folder = build(tmp_path / "out", metrics)
    data = json.loads((folder / "embeddings.json").read_text())
    data["dim"] = 16
    del data["triggers"]["typing"]
    (folder / "embeddings.json").write_text(json.dumps(data))
    write_manifest(folder, metrics)
    found = problems(folder)
    assert any("leakage found" in p for p in found)
    assert any("embeddings: dim 16" in p for p in found)
    assert any("no CLAP centroid for ['typing']" in p for p in found)


def test_wrong_counts_of_samples_and_spectrograms(tmp_path: Path) -> None:
    folder = build(tmp_path / "out")
    (folder / "samples" / "000_mixture.wav").unlink()
    (folder / "spectrograms" / "000.png").unlink()
    write_manifest(folder, good_metrics())
    found = problems(folder)
    assert any("4 sample mixtures" in p for p in found)
    assert any("19 spectrograms" in p for p in found)


def test_apply_copies_results_into_the_repo(tmp_path: Path) -> None:
    folder = build(tmp_path / "out")
    written = ingest_K1.apply(folder, root=tmp_path / "repo")
    assert sorted(written) == [
        "docs/DATA_ATTRIBUTION.md",
        "docs/DATA_CARD.md",
        "eval/realworld_test_set.json",
        "models/trigger_embeddings.json",
    ]
    assert len(realworld.load_lock(tmp_path / "repo" / "eval" / "realworld_test_set.json")) == 80


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert ingest_K1.main(["--dir", str(build(tmp_path / "good"))]) == 0
    assert "accepted" in capsys.readouterr().out
    assert ingest_K1.main(["--dir", str(build(tmp_path / "short", clips=3))]) == 1
