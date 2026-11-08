"""Generate the public data card and the per-clip attribution list."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from eval.realworld import RealWorldClip
from synth.freesound import ClipRecord
from synth.licences import release_allowed
from synth.sources import Source
from synth.splits import SPLITS

KNOWN_GAPS = (
    "No local recordings: sounds such as chewing roti or hostel pen clicks come only from "
    "whatever Creative Commons uploaders have shared.",
    "English speech only (LibriSpeech). Urdu speech needs a Mozilla Data Collective account "
    "and terms that forbid re-hosting, so it is not included yet.",
    "Freesound clips are high-quality Ogg previews (about 192 kbps), not original files.",
    "Freesound trigger clips are field recordings, so the 'exact trigger' includes each "
    "recording's own background noise.",
    "ESC-50 is non-commercial (CC BY-NC): used for training a free product only, never released.",
)


def _table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return lines


def build(
    sources: Mapping[str, Source],
    split_counts: Mapping[str, Mapping[str, int]],
    freesound: Sequence[ClipRecord],
    realworld: Sequence[RealWorldClip],
    generated: str,
    gaps: Sequence[str] = KNOWN_GAPS,
) -> str:
    lines = [
        "# Data card",
        "",
        f"Generated {generated} from the data pipeline's manifests. Counts are clips or files.",
        "",
        "## Sources",
        "",
    ]
    rows = []
    for key, source in sources.items():
        counts = split_counts.get(key, {})
        total = sum(counts.values())
        per_split = " / ".join(str(counts.get(split, 0)) for split in SPLITS)
        rows.append(
            [
                source.name,
                source.role,
                source.licence,
                total if counts else "n/a",
                per_split if counts else "n/a",
                source.split_rule,
            ]
        )
    header = ["Source", "Role", "Licence", "Count", "Train / val / test", "Split rule"]
    lines += _table(header, rows)

    lines += ["", "## Freesound clips", ""]
    licences = Counter(record.licence for record in freesound)
    groups = Counter(record.group for record in freesound)
    lines += _table(["Licence", "Clips"], sorted(licences.items()))
    lines += [""]
    lines += _table(["Group", "Clips"], sorted(groups.items()))
    uploader_count = len({r.username.lower() for r in freesound})
    lines += [
        "",
        f"{len(freesound)} clips from {uploader_count} uploaders. Every clip is CC0 or CC BY; "
        "the full list with authors is in `docs/DATA_ATTRIBUTION.md`.",
    ]

    lines += ["", "## Frozen real-world test set", ""]
    scenes = Counter(clip.scene for clip in realworld)
    lines += _table(["Scene", "Clips"], sorted(scenes.items()))
    lines += [
        "",
        f"{len(realworld)} clips, locked in `eval/realworld_test_set.json` (IDs and checksums "
        "only). Their uploaders are excluded from training. Never used for training or tuning.",
    ]

    lines += ["", "## Known gaps", ""]
    lines += [f"- {gap}" for gap in gaps]
    return "\n".join(lines) + "\n"


def attribution(freesound: Sequence[ClipRecord], realworld: Sequence[RealWorldClip]) -> str:
    lines = [
        "# Data attribution",
        "",
        "Creative Commons clips used by Anechoic Chamber, from [Freesound](https://freesound.org).",
        "",
        "## Training clips",
        "",
    ]
    rows = [
        [f"[{r.freesound_id}]({r.source_url})", r.name.replace("|", "/"), r.username, r.licence]
        for r in sorted(freesound, key=lambda r: r.freesound_id)
        if release_allowed(r.licence)
    ]
    lines += _table(["Clip", "Title", "Author", "Licence"], rows)
    lines += ["", "## Real-world test clips", ""]
    rows = [
        [f"[{c.freesound_id}]({c.source_url})", c.scene, c.username, c.licence]
        for c in sorted(realworld, key=lambda c: c.freesound_id)
    ]
    lines += _table(["Clip", "Scene", "Author", "Licence"], rows)
    return "\n".join(lines) + "\n"
