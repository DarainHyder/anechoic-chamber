"""End-to-end K1 run with stand-ins for the datasets, Freesound, the judge and CLAP."""

import hashlib
import io
import json
import urllib.parse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from eval import realworld
from synth import audio, k1, vocab
from synth.audio import SAMPLE_RATE
from synth.freesound import FreesoundClient, Response
from tests.test_mix import burst, speechlike
from tests.test_realism import FakeTagger


def ogg_bytes(signal: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, signal, SAMPLE_RATE, format="OGG", subtype="VORBIS")
    return buffer.getvalue()


def wav(path: Path, signal: np.ndarray, fmt: str = "WAV") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), signal, SAMPLE_RATE, format=fmt)


def fake_fetch(name: str, root: Path) -> int:
    base = root / name
    marker = base / ".done"
    if marker.exists():
        return int(marker.read_text())
    count = 0
    if name == "esc50":
        meta = base / "ESC-50-master" / "meta" / "esc50.csv"
        rows = [
            ("1-1-A-1.wav", 1, "keyboard_typing"),
            ("4-2-A-1.wav", 4, "mouse_click"),
            ("5-3-A-1.wav", 5, "breathing"),
            ("2-4-A-1.wav", 2, "drinking_sipping"),
            ("1-5-A-1.wav", 1, "dog"),
        ]
        meta.parent.mkdir(parents=True, exist_ok=True)
        lines = ["filename,fold,target,category,esc10,src_file,take"]
        for i, (filename, fold, category) in enumerate(rows):
            lines.append(f"{filename},{fold},{i},{category},False,{i},A")
            wav(meta.parent.parent / "audio" / filename, burst(i, 1.0))
            count += 1
        meta.write_text("\n".join(lines) + "\n")
    elif name == "fsd50k-ground-truth":
        gt = base / "FSD50K.ground_truth" / "dev.csv"
        gt.parent.mkdir(parents=True, exist_ok=True)
        gt.write_text(
            'fname,labels,mids,split\n9001,"Typing,Computer_keyboard",x,train\n9002,Breathing,y,val\n'
        )
        count = 1
    elif name == "librispeech-dev-clean":
        for speaker in (84, 174, 251):
            path = (
                base / "LibriSpeech" / "dev-clean" / str(speaker) / "1" / f"{speaker}-1-0000.flac"
            )
            wav(path, speechlike(5, speaker), "FLAC")
            count += 1
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(count))
    return count


class FakeFreesound:
    """Search results per query (or per ID filter), with real Ogg previews."""

    def __init__(self) -> None:
        self.preview_calls = 0

    def sound(self, sound_id: int) -> dict[str, Any]:
        licence = (
            "https://creativecommons.org/licenses/by-nc/3.0/"
            if sound_id % 11 == 0
            else ("http://creativecommons.org/publicdomain/zero/1.0/")
        )
        return {
            "id": sound_id,
            "name": f"sound {sound_id}",
            "username": f"user{sound_id % 7}",
            "license": licence,
            "tags": ["test"],
            "duration": 6.0,
            "previews": {"preview-hq-ogg": f"https://cdn.freesound.org/p/{sound_id}.ogg"},
        }

    def __call__(self, url: str, headers: Mapping[str, str]) -> Response:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc == "cdn.freesound.org":
            self.preview_calls += 1
            sound_id = int(Path(parsed.path).stem)
            signal = speechlike(6, sound_id) + np.pad(burst(sound_id, 2.0), (0, 4 * SAMPLE_RATE))
            return Response(200, {}, ogg_bytes(np.clip(signal, -1, 1)))
        params = urllib.parse.parse_qs(parsed.query)
        filters = params.get("filter", [""])[0]
        page = int(params["page"][0])
        if "id:(" in filters:
            ids = [int(i) for i in filters.split("id:(")[1].rstrip(")").split(" OR ")]
        else:
            seed = int(hashlib.sha256(params.get("query", [""])[0].encode()).hexdigest()[:6], 16)
            ids = [1000 + (seed + i * 37) % 5000 for i in range(6)]
        results = [self.sound(i) for i in ids] if page == 1 else []
        return Response(200, {}, json.dumps({"results": results, "next": None}).encode())


class AllTriggersTagger(FakeTagger):
    """Hears speech and every trigger type in any audio."""

    def __call__(self, signal: np.ndarray) -> np.ndarray:
        probs = super().__call__(signal)
        for name in ("Chewing, mastication", "Sniff", "Clicking", "Typing"):
            probs[self.labels.index(name)] = 0.3
        return probs


PHRASE_GROUP = {phrase: group for group, phrase in vocab.load()}


def fake_embed_audio(signals: Sequence[np.ndarray]) -> np.ndarray:
    """Every clip sounds equally like all four triggers and like no negative prompt."""
    vector = np.zeros(16)
    vector[:4] = 1.0
    return np.stack([vector for _ in signals])


def fake_embed_text(texts: Sequence[str]) -> np.ndarray:
    """Trigger phrases point along their group's axis; anything else along axes 4 to 15."""
    rows = []
    for text in texts:
        vector = np.zeros(16)
        group = PHRASE_GROUP.get(text)
        if group in k1.TRIGGERS:
            vector[k1.TRIGGERS.index(group)] = 1.0
        else:
            vector[4 + int(hashlib.sha256(text.encode()).hexdigest()[:4], 16) % 12] = 1.0
        rows.append(vector)
    return np.stack(rows)


def make(tmp_path: Path, server: FakeFreesound, logs: list[str]) -> tuple[k1.K1Config, k1.Deps]:
    cfg = k1.with_paths(
        k1.K1Config(
            data_dir=Path(),
            bank_dir=Path(),
            realworld_dir=Path(),
            out_dir=Path(),
            state_dir=Path(),
            realworld_size=4,
            per_trigger=3,
            mixtures=12,
            spectrograms=3,
            samples=2,
            repo_commit="abc123",
        ),
        tmp_path,
    )
    client = FreesoundClient("key", transport=server, sleep=lambda _: None, min_interval=0.0)
    deps = k1.Deps(
        fetch=fake_fetch,
        client=client,
        tagger=AllTriggersTagger(loud_rms=0.0),
        embed_audio=fake_embed_audio,
        embed_text=fake_embed_text,
        versions={"python": "test"},
        log=logs.append,
        require_codec=audio.find_ffmpeg() is not None,
    )
    return cfg, deps


@pytest.fixture(scope="module")
def first_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any], list[str]]:
    root = tmp_path_factory.mktemp("k1")
    logs: list[str] = []
    cfg, deps = make(root, FakeFreesound(), logs)
    return root, k1.run(cfg, deps), logs


def test_outputs_are_complete(first_run: tuple[Path, dict[str, Any], list[str]]) -> None:
    root, metrics, _ = first_run
    out = root / "outputs" / "K1_data_bank"
    for name in (
        "manifest.json",
        "metrics.json",
        "REPORT.md",
        "embeddings.json",
        "DATA_CARD.md",
        "DATA_ATTRIBUTION.md",
        "realworld_test_set.json",
        "freesound_bank.jsonl",
        "mixture_checks.jsonl",
    ):
        assert (out / name).is_file(), name
    assert len(list((out / "spectrograms").glob("*.png"))) == 3
    assert len(list((out / "samples").glob("*_mixture.wav"))) == 2
    assert metrics["mixtures"]["mixtures"] == 12
    assert metrics["mixtures"]["clipped_count"] == 0


def test_no_leakage_and_test_uploaders_kept_out(
    first_run: tuple[Path, dict[str, Any], list[str]],
) -> None:
    root, metrics, _ = first_run
    assert metrics["leakage"]["groups_in_two_splits"] == 0
    assert metrics["leakage"]["test_uploaders_in_train"] == 0
    locked = realworld.load_lock(root / "outputs" / "K1_data_bank" / "realworld_test_set.json")
    assert len(locked) == 4
    bank_users = {
        json.loads(line)["username"].lower()
        for line in (root / "outputs" / "K1_data_bank" / "freesound_bank.jsonl")
        .read_text()
        .splitlines()
    }
    assert not bank_users & realworld.uploaders(locked)


def test_only_release_licences_are_collected(
    first_run: tuple[Path, dict[str, Any], list[str]],
) -> None:
    root, _, _ = first_run
    lines = (root / "outputs" / "K1_data_bank" / "freesound_bank.jsonl").read_text().splitlines()
    assert lines
    assert {json.loads(line)["licence"] for line in lines} <= {"CC0-1.0", "CC-BY-4.0", "CC-BY-3.0"}


def test_embeddings_cover_all_phrases(first_run: tuple[Path, dict[str, Any], list[str]]) -> None:
    root, metrics, _ = first_run
    data = json.loads((root / "outputs" / "K1_data_bank" / "embeddings.json").read_text())
    assert len(data["phrases"]) == 300
    assert data["dim"] == 16
    assert set(data["triggers"]) <= set(k1.TRIGGERS)
    for item in data["triggers"].values():
        assert np.linalg.norm(item["vector"]) == pytest.approx(1.0, abs=1e-4)
    assert metrics["embeddings"]["accuracy"] is not None


def test_manifest_checksums_match(first_run: tuple[Path, dict[str, Any], list[str]]) -> None:
    root, _, _ = first_run
    out = root / "outputs" / "K1_data_bank"
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["repo_commit"] == "abc123"
    assert manifest["files"]
    for row in manifest["files"]:
        assert hashlib.sha256((out / row["path"]).read_bytes()).hexdigest() == row["sha256"]


def test_report_has_a_gate_table(first_run: tuple[Path, dict[str, Any], list[str]]) -> None:
    root, _, logs = first_run
    text = (root / "outputs" / "K1_data_bank" / "REPORT.md").read_text()
    assert "| Groups in two splits | 0 | 0 | PASS |" in text
    assert "speech_detect_rate" in text
    assert any("ETA" in line for line in logs)


def test_second_run_resumes_instead_of_starting_over(
    first_run: tuple[Path, dict[str, Any], list[str]],
) -> None:
    root, metrics, _ = first_run
    server = FakeFreesound()
    logs: list[str] = []
    cfg, deps = make(root, server, logs)
    again = k1.run(cfg, deps)
    assert any("reusing the locked set" in line for line in logs)
    assert server.preview_calls == 0
    assert again["bank"] == metrics["bank"]
    assert again["realworld"] == metrics["realworld"]


def test_full_config_is_bigger_than_smoke() -> None:
    paths: dict[str, Any] = dict(
        data_dir=Path(), bank_dir=Path(), realworld_dir=Path(), out_dir=Path(), state_dir=Path()
    )
    full = k1.K1Config.full(**paths)
    smoke = k1.K1Config(**paths)
    assert not full.smoke and smoke.smoke
    assert full.mixtures == 200 and full.realworld_size == 80
    assert full.mix_splits == ("train",)
    assert set(k1.SMOKE_DATASETS) <= set(full.datasets)


def test_outputs_from_an_earlier_run_are_cleared(tmp_path: Path) -> None:
    cfg, deps = make(tmp_path, FakeFreesound(), [])
    stray = cfg.out_dir / "spectrograms" / "999.png"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"old")
    k1.run(cfg, deps)
    assert not stray.exists()
    assert len(list((cfg.out_dir / "spectrograms").glob("*.png"))) == cfg.spectrograms


def test_state_from_another_configuration_is_refused(tmp_path: Path) -> None:
    from dataclasses import replace

    cfg, _ = make(tmp_path, FakeFreesound(), [])
    cfg.state_dir.mkdir(parents=True)
    k1.check_state(cfg)
    k1.check_state(cfg)  # the same configuration again is fine
    with pytest.raises(RuntimeError, match="different configuration"):
        k1.check_state(replace(cfg, smoke=False, realworld_size=80))


def test_curation_keeps_trigger_like_clips_and_drops_others() -> None:
    names = ["chewing_eating", "sniffing_breathing", "clicks", "typing", "negative:silence"]
    classes = np.eye(5)
    own = np.array([[0.1, 0.0, 0.0, 0.0, 0.2], [0.9, 0.1, 0.0, 0.0, 0.2]])
    assert k1.judge_clip(own, names, classes, "chewing_eating") == (True, 1)
    silence = np.array([[0.2, 0.0, 0.0, 0.0, 0.9]])
    assert k1.judge_clip(silence, names, classes, "chewing_eating") == (False, -1)
    clicks_vs_typing = np.array([[0.0, 0.0, 0.7, 0.8, 0.1]])  # second place is allowed
    assert k1.judge_clip(clicks_vs_typing, names, classes, "clicks")[0]
    third_place = np.array([[0.9, 0.0, 0.2, 0.8, 0.1]])
    assert not k1.judge_clip(third_place, names, classes, "clicks")[0]


def test_clip_windows_cover_short_and_long_clips() -> None:
    assert len(k1.clip_windows(np.zeros(SAMPLE_RATE, dtype=np.float32))) == 1
    windows = k1.clip_windows(np.zeros(60 * SAMPLE_RATE, dtype=np.float32))
    assert len(windows) == k1.CURATION_WINDOWS
    assert all(len(w) == 4 * SAMPLE_RATE for w in windows)


def test_metrics_report_curation_and_clean_upper_bound(
    first_run: tuple[Path, dict[str, Any], list[str]],
) -> None:
    root, metrics, _ = first_run
    assert metrics["curation"]["method"] == "CLAP zero-shot"
    assert metrics["bank"]["collected"] >= metrics["bank"]["clips"] > 0
    assert metrics["mixtures"]["clean_trigger_detect_rate"] is not None
    report = (root / "outputs" / "K1_data_bank" / "REPORT.md").read_text()
    assert "Clean trigger alone" in report and "Bank curation" in report
