"""Kaggle K1: build the trigger bank, the locked real-world test set and CLAP embeddings.

The notebook only sets up Kaggle (GPU, secrets, models) and calls run(). Everything
here can run locally with stand-in models, which is how the tests exercise it.
Each stage leaves state behind, so a restarted run continues where it stopped.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from eval import realworld
from eval.realworld import RealWorldClip
from synth import audio, data_card, freesound, realism, splits, vocab
from synth.audio import SAMPLE_RATE, Audio
from synth.freesound import FreesoundClient, Manifest
from synth.licences import normalise, release_allowed
from synth.mix import ClipRef, MixConfig, MixtureSampler, Pools
from synth.realism import Tagger
from synth.sources import SOURCES
from synth.splits import Assignment

TRIGGERS = realism.TRIGGER_GROUPS
# datetime.UTC needs Python 3.11; Kaggle's Python version is unverified, so stay compatible.
UTC = timezone.utc  # noqa: UP017

TRIGGER_QUERIES: dict[str, tuple[str, ...]] = {
    "chewing_eating": (
        "chewing", "eating crisps", "crunching", "eating apple", "chewing gum",
        "slurping", "munching", "lip smack", "eating chips", "biting",
    ),
    "sniffing_breathing": (
        "sniffing", "sniff", "breathing", "nose blowing", "snort",
        "heavy breathing", "sniffle", "throat clearing",
    ),
    "clicks": (
        "pen click", "mouse click", "clicking", "ballpoint pen", "clock tick",
        "finger tapping", "knuckle crack", "switch click",
    ),
    "typing": (
        "keyboard typing", "typing", "mechanical keyboard", "laptop keyboard",
        "typewriter", "computer keyboard",
    ),
}  # fmt: skip
FSD50K_CLASSES: dict[str, tuple[str, ...]] = {
    "chewing_eating": ("Chewing_and_mastication", "Crunch", "Biting"),
    "sniffing_breathing": ("Breathing", "Sniff", "Snort", "Gasp", "Pant"),
    "clicks": ("Tick", "Clicking", "Tap", "Tick-tock"),
    "typing": ("Typing", "Computer_keyboard", "Typewriter"),
}
ESC50_CLASSES: dict[str, tuple[str, ...]] = {
    "chewing_eating": ("drinking_sipping",),
    "sniffing_breathing": ("breathing", "snoring", "sneezing"),
    "clicks": ("mouse_click", "clock_tick"),
    "typing": ("keyboard_typing",),
}
FULL_DATASETS = (
    "esc50",
    "fsd50k-ground-truth",
    "librispeech-train-clean-100",
    "librispeech-dev-clean",
    "librispeech-test-clean",
    "musan",
    "rirs",
)
SMOKE_DATASETS = ("esc50", "fsd50k-ground-truth", "librispeech-dev-clean")

EmbedAudio = Callable[[Sequence[Audio]], NDArray[np.floating]]
EmbedText = Callable[[Sequence[str]], NDArray[np.floating]]


@dataclass(frozen=True)
class K1Config:
    data_dir: Path
    bank_dir: Path
    realworld_dir: Path
    out_dir: Path
    state_dir: Path
    smoke: bool = True
    seed: int = 1234
    repo_commit: str = ""
    datasets: tuple[str, ...] = SMOKE_DATASETS
    per_trigger: int = 8
    per_query: int = 10
    fsd50k_per_group: int = 4
    realworld_per_query: int = 3
    realworld_queries_per_scene: int | None = 1
    realworld_size: int = realworld.TARGET_SIZE
    realworld_seconds: tuple[float, float] = (5.0, 60.0)
    realworld_min_speech: float = 0.3
    realworld_min_trigger: float = 0.1
    mix_splits: tuple[str, ...] = splits.SPLITS
    mixtures: int = 20
    samples: int = 5
    spectrograms: int = 20
    clap_max_clips: int = 50

    @classmethod
    def full(cls, **paths: Any) -> K1Config:
        return cls(
            **paths,
            smoke=False,
            datasets=FULL_DATASETS,
            per_trigger=400,
            per_query=150,
            fsd50k_per_group=300,
            realworld_per_query=25,
            realworld_queries_per_scene=None,
            mix_splits=(splits.TRAIN,),
            mixtures=200,
            clap_max_clips=300,
        )


@dataclass
class Deps:
    fetch: Callable[[str, Path], int]
    client: FreesoundClient
    tagger: Tagger
    embed_audio: EmbedAudio
    embed_text: EmbedText
    versions: Mapping[str, str] = field(default_factory=dict)
    log: Callable[[str], None] = print
    require_codec: bool = True


class Progress:
    """Prints progress with elapsed time and an ETA."""

    def __init__(self, label: str, total: int, log: Callable[[str], None], every: int = 10) -> None:
        self.label, self.total, self.log, self.every = label, max(total, 1), log, every
        self.start = time.monotonic()
        self.done = 0

    def step(self, count: int = 1) -> None:
        self.done += count
        if self.done % self.every == 0 or self.done >= self.total:
            elapsed = time.monotonic() - self.start
            eta = elapsed / self.done * (self.total - self.done)
            self.log(f"[{self.label}] {self.done}/{self.total} | {elapsed:.0f}s | ETA {eta:.0f}s")


# ---- inventories of downloaded data ----------------------------------------------


def esc50_clips(root: Path) -> list[tuple[str, Path, int]]:
    """(trigger group, path, fold) for ESC-50 classes that match a trigger."""
    metas = list(root.glob("**/meta/esc50.csv"))
    if not metas:
        return []
    meta = metas[0]
    wanted = {cls: group for group, classes in ESC50_CLASSES.items() for cls in classes}
    found = []
    with meta.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["category"] in wanted:
                path = meta.parent.parent / "audio" / row["filename"]
                if path.is_file():
                    found.append((wanted[row["category"]], path, int(row["fold"])))
    return sorted(found, key=lambda item: item[1].name)


def fsd50k_ids(root: Path, per_group: int) -> dict[str, list[int]]:
    """Freesound IDs per trigger group from FSD50K's dev and eval label files."""
    ids: dict[str, set[int]] = {group: set() for group in FSD50K_CLASSES}
    lookup = {cls.lower(): group for group, classes in FSD50K_CLASSES.items() for cls in classes}
    for path in sorted(root.glob("**/*.csv")):
        if path.stem not in {"dev", "eval"}:
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                for label in row.get("labels", "").split(","):
                    group = lookup.get(label.strip().lower())
                    if group:
                        ids[group].add(int(row["fname"]))
    return {group: sorted(found)[:per_group] for group, found in ids.items() if found}


def files(root: Path, pattern: str) -> list[Path]:
    return sorted(root.glob(pattern)) if root.is_dir() else []


def relative_posix(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


# ---- real-world test set -------------------------------------------------------------


def window_scores(tagger: Tagger, signal: Audio, group: str) -> tuple[float, float]:
    """Best speech and trigger scores over 4 s windows (2 s hop, first 60 s)."""
    window, hop = 4 * SAMPLE_RATE, 2 * SAMPLE_RATE
    signal = signal[: 60 * SAMPLE_RATE]
    if len(signal) < window:
        signal = np.pad(signal, (0, window - len(signal)))
    speech = trigger = 0.0
    for start in range(0, len(signal) - window + 1, hop):
        probs = tagger(signal[start : start + window])
        speech = max(speech, realism.group_score(probs, tagger.labels, "speech"))
        trigger = max(trigger, realism.group_score(probs, tagger.labels, group))
    return speech, trigger


def build_realworld(cfg: K1Config, deps: Deps) -> list[RealWorldClip]:
    state = cfg.state_dir / "realworld_test_set.json"
    if state.is_file():
        deps.log("real-world test set: reusing the locked set from state")
        return realworld.load_lock(state)
    candidates_dir = cfg.realworld_dir / "candidates"
    filters = freesound.build_filter(*cfg.realworld_seconds)
    queries = {
        scene: qs[: cfg.realworld_queries_per_scene] if cfg.realworld_queries_per_scene else qs
        for scene, qs in realworld.SCENES.items()
    }
    total = sum(len(qs) for qs in queries.values()) * cfg.realworld_per_query
    progress = Progress("real-world candidates", total, deps.log)
    found: list[RealWorldClip] = []
    seen: set[int] = set()
    for scene, scene_queries in queries.items():
        group = realworld.SCENE_TRIGGER[scene]
        for query in scene_queries:
            for sound in deps.client.iter_search(query, filters, cfg.realworld_per_query):
                progress.step()
                sound_id = int(sound["id"])
                licence = normalise(str(sound.get("license", "")))
                if sound_id in seen or not release_allowed(licence):
                    continue
                seen.add(sound_id)
                try:
                    data = deps.client.fetch_preview(sound)
                except freesound.FreesoundError as error:
                    deps.log(f"skip {sound_id}: {error}")
                    continue
                path = candidates_dir / f"{sound_id}.ogg"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                speech, trigger = window_scores(deps.tagger, audio.load(path), group)
                if speech >= cfg.realworld_min_speech and trigger >= cfg.realworld_min_trigger:
                    found.append(
                        RealWorldClip(
                            freesound_id=sound_id,
                            username=str(sound.get("username", "")),
                            licence=licence,
                            source_url=f"https://freesound.org/s/{sound_id}/",
                            scene=scene,
                            sha256=hashlib.sha256(data).hexdigest(),
                            duration=float(sound.get("duration", 0.0)),
                            speech_score=round(speech, 4),
                            trigger_score=round(trigger, 4),
                        )
                    )
    chosen = realworld.select(found, cfg.realworld_size)
    deps.log(f"real-world test set: {len(found)} candidates passed the judge, {len(chosen)} chosen")
    clips_dir = cfg.realworld_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    for clip in chosen:
        shutil.move(
            str(candidates_dir / f"{clip.freesound_id}.ogg"), clips_dir / f"{clip.freesound_id}.ogg"
        )
    shutil.rmtree(candidates_dir, ignore_errors=True)
    if not chosen:
        return []
    created = datetime.now(UTC).date().isoformat()
    realworld.write_lock(chosen, state, created)
    return chosen


# ---- trigger bank ----------------------------------------------------------------------


def build_bank(
    cfg: K1Config, deps: Deps, test_uploaders: Iterable[str]
) -> list[freesound.ClipRecord]:
    manifest = Manifest(cfg.state_dir / "freesound_bank.jsonl")
    filters = freesound.build_filter(0.5, 30)
    gt_dir = cfg.data_dir / "fsd50k-ground-truth"
    ids = fsd50k_ids(gt_dir, cfg.fsd50k_per_group) if gt_dir.is_dir() else {}
    deps.log(f"FSD50K IDs per group: { {g: len(v) for g, v in ids.items()} }")
    queries = {group: TRIGGER_QUERIES[group] for group in TRIGGERS}
    candidates = chain(
        freesound.id_candidates(deps.client, ids, filters),
        freesound.search_candidates(deps.client, queries, filters, cfg.per_query),
    )
    stats = freesound.collect(
        deps.client,
        candidates,
        cfg.bank_dir,
        manifest,
        per_group=cfg.per_trigger,
        exclude_usernames=test_uploaders,
        log=deps.log,
    )
    deps.log(f"trigger bank: {asdict(stats)}")
    return manifest.load()


# ---- splits, pools, embeddings, mixtures ----------------------------------------


@dataclass
class Inventory:
    assignments: list[Assignment]
    speech: list[ClipRef]
    music: list[ClipRef]
    noise: list[ClipRef]
    rirs: list[ClipRef]
    triggers: dict[str, list[ClipRef]]
    trigger_splits: dict[str, str]


def inventory(
    cfg: K1Config, bank: Sequence[freesound.ClipRecord], test_set: Sequence[RealWorldClip]
) -> Inventory:
    test_users = realworld.uploaders(test_set)
    assigned: list[Assignment] = []
    clip_refs: dict[str, ClipRef] = {}
    trigger_group: dict[str, str] = {}

    for group, path, fold in esc50_clips(cfg.data_dir / "esc50"):
        a = splits.esc50(path.name, fold)
        assigned.append(a)
        clip_refs[a.item] = ClipRef(f"esc50:{path.name}", path)
        trigger_group[a.item] = group
    for record in bank:
        a = splits.freesound(f"fs:{record.freesound_id}", record.username, test_users)
        assigned.append(a)
        clip_refs[a.item] = ClipRef(a.item, cfg.bank_dir / record.file)
        trigger_group[a.item] = record.group
    for clip in test_set:
        assigned.append(splits.freesound(f"rw:{clip.freesound_id}", clip.username, test_users))

    speech: list[ClipRef] = []
    music: list[ClipRef] = []
    noise: list[ClipRef] = []
    rirs: list[ClipRef] = []
    for path in files(cfg.data_dir, "librispeech-*/**/*.flac"):
        a = splits.librispeech(relative_posix(path, cfg.data_dir))
        assigned.append(a)
        if a.split in cfg.mix_splits:
            speech.append(ClipRef(a.item, path))
    for path in files(cfg.data_dir / "musan", "**/*.wav"):
        a = splits.musan(relative_posix(path, cfg.data_dir))
        assigned.append(a)
        if a.split in cfg.mix_splits:
            (music if "/music/" in a.item else noise).append(ClipRef(a.item, path))
    for path in files(cfg.data_dir / "rirs", "**/*.wav"):
        a = splits.rir(relative_posix(path, cfg.data_dir))
        assigned.append(a)
        if a.split in cfg.mix_splits:
            rirs.append(ClipRef(a.item, path))

    triggers: dict[str, list[ClipRef]] = {group: [] for group in TRIGGERS}
    trigger_splits = {}
    for a in assigned:
        if a.item in trigger_group:
            trigger_splits[a.item] = a.split
            if a.split in cfg.mix_splits:
                triggers[trigger_group[a.item]].append(clip_refs[a.item])
    return Inventory(assigned, speech, music, noise, rirs, triggers, trigger_splits)


def _normalise_rows(matrix: NDArray[np.floating]) -> NDArray[np.float64]:
    data = np.asarray(matrix, dtype=np.float64)
    norms = np.maximum(np.linalg.norm(data, axis=-1, keepdims=True), 1e-12)
    return np.asarray(data / norms, dtype=np.float64)


def embeddings(
    cfg: K1Config, deps: Deps, inv: Inventory, model: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """CLAP centroids for each trigger plus all 300 phrases, and a sanity check."""
    triggers: dict[str, Any] = {}
    for group in TRIGGERS:
        clips = sorted(inv.triggers[group], key=lambda c: c.clip_id)[: cfg.clap_max_clips]
        if not clips:
            continue
        signals = [c.load()[: 10 * SAMPLE_RATE] for c in clips]
        vectors = _normalise_rows(deps.embed_audio(signals))
        centroid = _normalise_rows(vectors.mean(axis=0))
        triggers[group] = {"clips": len(clips), "vector": [round(float(v), 6) for v in centroid]}
    rows = vocab.load()
    text = _normalise_rows(deps.embed_text([phrase for _, phrase in rows]))
    phrases = [
        {"group": group, "phrase": phrase, "vector": [round(float(v), 6) for v in vector]}
        for (group, phrase), vector in zip(rows, text, strict=True)
    ]
    text_centroids = {
        group: _normalise_rows(
            text[[i for i, (g, _) in enumerate(rows) if g == group]].mean(axis=0)
        )
        for group in TRIGGERS
    }
    nearest = {}
    for group, item in triggers.items():
        audio_vec = np.asarray(item["vector"])
        scores = {other: float(audio_vec @ vec) for other, vec in text_centroids.items()}
        nearest[group] = max(scores, key=lambda k: scores[k])
    agreement = {
        "nearest_text_group": nearest,
        "accuracy": sum(nearest[g] == g for g in nearest) / len(nearest) if nearest else None,
    }
    dim = len(phrases[0]["vector"]) if phrases else 0
    payload = {"model": model, "dim": dim, "triggers": triggers, "phrases": phrases}
    return payload, agreement


def mixtures(cfg: K1Config, deps: Deps, inv: Inventory) -> dict[str, Any]:
    pools = Pools(
        speech=inv.speech, triggers=inv.triggers, music=inv.music, noise=inv.noise, rirs=inv.rirs
    )
    mix_config = MixConfig(require_codec=deps.require_codec)
    sampler = MixtureSampler(pools, mix_config, seed=cfg.seed)
    progress = Progress("mixtures", cfg.mixtures, deps.log, every=20)
    checks = []
    spectrogram_every = max(1, cfg.mixtures // cfg.spectrograms)
    saved = 0
    for index in range(cfg.mixtures):
        m = sampler.sample(index)
        checks.append(realism.check(m, mix_config, deps.tagger))
        if m.spec.events and saved < cfg.samples:
            for part, signal in (("mixture", m.mixture), ("trigger", m.trigger), ("bed", m.bed)):
                audio.save(cfg.out_dir / "samples" / f"{index:03d}_{part}.wav", signal)
            saved += 1
        if index % spectrogram_every == 0 and index // spectrogram_every < cfg.spectrograms:
            events = ", ".join(f"{e.trigger} {e.measured_tbr_db:+.1f} dB" for e in m.spec.events)
            title = f"mixture {index}: {events or 'no trigger'} | codec {m.spec.codec or 'none'}"
            realism.render_spectrogram(m, cfg.out_dir / "spectrograms" / f"{index:03d}.png", title)
        progress.step()
    summary = realism.summarise(checks)
    summary["config"] = asdict(mix_config)
    (cfg.out_dir / "mixture_checks.jsonl").write_text(
        "".join(json.dumps(asdict(c)) + "\n" for c in checks), encoding="utf-8"
    )
    return summary


# ---- outputs ---------------------------------------------------------------------------


def file_list(root: Path, skip: Iterable[str] = ("manifest.json",)) -> list[dict[str, Any]]:
    skipped = set(skip)
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = relative_posix(path, root)
        if rel in skipped:
            continue
        rows.append({"path": rel, "bytes": path.stat().st_size, "sha256": audio_sha(path)})
    return rows


def audio_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def report(metrics: Mapping[str, Any]) -> str:
    realism_gate = metrics["mixtures"]["gate"]
    lines = [
        "# K1 data bank report",
        "",
        f"Smoke test: {metrics['smoke']}. Repo commit: `{metrics['repo_commit'] or 'unknown'}`.",
        "",
        "## Gate checks",
        "",
        "| Check | Target | Actual | Result |",
        "| --- | --- | --- | --- |",
    ]
    leak = metrics["leakage"]
    lines.append(
        f"| Groups in two splits | 0 | {leak['groups_in_two_splits']} | "
        f"{'PASS' if leak['groups_in_two_splits'] == 0 else 'FAIL'} |"
    )
    lines.append(
        f"| Test-set uploaders in train or val | 0 | {leak['test_uploaders_in_train']} | "
        f"{'PASS' if leak['test_uploaders_in_train'] == 0 else 'FAIL'} |"
    )
    for name, result in realism_gate.items():
        actual = result["actual"]
        shown = f"{actual:.3f}" if isinstance(actual, float) else actual
        verdict = {True: "PASS", False: "FAIL", None: "NOT MEASURED"}[result["passed"]]
        lines.append(f"| {name} | {result['target']} | {shown} | {verdict} |")
    rw = metrics["realworld"]
    lines += [
        "",
        "## Data",
        "",
        f"- Real-world test set: {rw['size']} of {rw['target']} clips.",
        f"- Trigger bank (Freesound): {metrics['bank']['clips']} clips, per group "
        f"{metrics['bank']['per_group']}.",
        f"- Mixture trigger pools: {metrics['pools']['triggers']}.",
        f"- CLAP audio-to-text agreement: {metrics['embeddings']['accuracy']} "
        f"(nearest text group per trigger: {metrics['embeddings']['nearest_text_group']}).",
        f"- Trigger detection by trigger: {metrics['mixtures']['trigger_detect_rate_by_trigger']}.",
        "",
        "Listen to `samples/` and look at `spectrograms/` before accepting these numbers.",
    ]
    return "\n".join(lines) + "\n"


def run(cfg: K1Config, deps: Deps, clap_model: str = "laion/clap-htsat-fused") -> dict[str, Any]:
    for folder in (cfg.data_dir, cfg.bank_dir, cfg.realworld_dir, cfg.out_dir, cfg.state_dir):
        folder.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    log = deps.log

    downloads = {}
    for name in cfg.datasets:
        t0 = time.monotonic()
        downloads[name] = deps.fetch(name, cfg.data_dir)
        log(f"download {name}: {downloads[name]} files in {time.monotonic() - t0:.0f}s")

    test_set = build_realworld(cfg, deps)
    if test_set:
        shutil.copy(
            cfg.state_dir / "realworld_test_set.json", cfg.out_dir / "realworld_test_set.json"
        )
    bank = build_bank(cfg, deps, realworld.uploaders(test_set))
    (cfg.out_dir / "freesound_bank.jsonl").write_text(
        "".join(json.dumps(asdict(r)) + "\n" for r in bank), encoding="utf-8"
    )

    inv = inventory(cfg, bank, test_set)
    leaks = splits.leaks(inv.assignments)
    uploader_leaks = splits.test_set_uploader_leaks(inv.assignments, realworld.uploaders(test_set))
    log(
        f"leakage: {len(leaks)} groups in two splits, {len(uploader_leaks)} test uploaders in train"
    )

    payload, agreement = embeddings(cfg, deps, inv, clap_model)
    (cfg.out_dir / "embeddings.json").write_text(json.dumps(payload), encoding="utf-8")

    mixture_summary = mixtures(cfg, deps, inv)

    split_counts = splits.counts(inv.assignments)
    generated = datetime.now(UTC).date().isoformat()
    (cfg.out_dir / "DATA_CARD.md").write_text(
        data_card.build(SOURCES, split_counts, bank, test_set, generated), encoding="utf-8"
    )
    (cfg.out_dir / "DATA_ATTRIBUTION.md").write_text(
        data_card.attribution(bank, test_set), encoding="utf-8"
    )

    per_group: dict[str, int] = {}
    for record in bank:
        per_group[record.group] = per_group.get(record.group, 0) + 1
    metrics: dict[str, Any] = {
        "smoke": cfg.smoke,
        "repo_commit": cfg.repo_commit,
        "downloads": downloads,
        "realworld": {"size": len(test_set), "target": cfg.realworld_size},
        "bank": {"clips": len(bank), "per_group": per_group},
        "pools": {
            "speech": len(inv.speech),
            "music": len(inv.music),
            "noise": len(inv.noise),
            "rirs": len(inv.rirs),
            "triggers": {g: len(v) for g, v in inv.triggers.items()},
        },
        "splits": split_counts,
        "leakage": {
            "groups_in_two_splits": len(leaks),
            "test_uploaders_in_train": len(uploader_leaks),
            "examples": sorted(leaks)[:10],
        },
        "embeddings": agreement,
        "mixtures": mixture_summary,
        "runtime_seconds": round(time.monotonic() - started, 1),
    }
    (cfg.out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (cfg.out_dir / "REPORT.md").write_text(report(metrics), encoding="utf-8")
    hyper = {k: str(v) if isinstance(v, Path) else v for k, v in asdict(cfg).items()}
    manifest = {
        "task": "K1_data_bank",
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "repo_commit": cfg.repo_commit,
        "versions": dict(deps.versions),
        "hyperparameters": {
            "k1": hyper,
            "mix": asdict(MixConfig(require_codec=deps.require_codec)),
        },
        "metrics": metrics,
        "files": file_list(cfg.out_dir),
    }
    (cfg.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"K1 finished in {metrics['runtime_seconds']}s")
    return metrics


def with_paths(cfg: K1Config, root: Path) -> K1Config:
    """Return cfg with every folder under root (used by tests and local dry runs)."""
    return replace(
        cfg,
        data_dir=root / "data",
        bank_dir=root / "trigger_bank",
        realworld_dir=root / "realworld",
        out_dir=root / "outputs" / "K1_data_bank",
        state_dir=root / "state",
    )
