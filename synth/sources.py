"""Every data source the pipeline uses, with its licence and split rule.

Licences were checked on 2026-11-08 against each source's own page.
"""

from __future__ import annotations

from dataclasses import dataclass

OPENSLR_MIRRORS = (
    "https://openslr.elda.org/resources",
    "https://openslr.trmal.net/resources",
    "https://openslr.magicdatatech.com/resources",
)


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    role: str
    licence: str
    licence_page: str
    split_rule: str
    urls: tuple[str, ...] = ()
    note: str = ""


def openslr(resource: int, filename: str) -> tuple[str, ...]:
    return tuple(f"{mirror}/{resource}/{filename}" for mirror in OPENSLR_MIRRORS)


SOURCES: dict[str, Source] = {
    source.key: source
    for source in (
        Source(
            key="esc50",
            name="ESC-50",
            role="triggers",
            licence="CC-BY-NC-3.0",
            licence_page="https://github.com/karolpiczak/ESC-50#license",
            split_rule="fold: 1-3 train, 4 val, 5 test (folds keep each source recording together)",
            urls=("https://github.com/karolpiczak/ESC-50/archive/refs/heads/master.zip",),
            note="Non-commercial: training only, never released.",
        ),
        Source(
            key="freesound",
            name="Freesound (API previews)",
            role="triggers and real-world test set",
            licence="per clip: CC0 or CC BY only",
            licence_page="https://freesound.org/help/faq/#licenses",
            split_rule="uploader: every clip from one uploader lands in one split",
            note="High-quality Ogg previews (about 192 kbps), not original files.",
        ),
        Source(
            key="fsd50k",
            name="FSD50K labels",
            role="choosing Freesound clips by class",
            licence="CC-BY-4.0 (labels); clips from the Freesound API keep their own licence",
            licence_page="https://zenodo.org/records/4060432",
            split_rule="uploader, same as Freesound",
            urls=(
                "https://zenodo.org/records/4060432/files/FSD50K.ground_truth.zip?download=1",
                "https://zenodo.org/records/4060432/files/FSD50K.metadata.zip?download=1",
            ),
        ),
        Source(
            key="librispeech",
            name="LibriSpeech",
            role="speech",
            licence="CC-BY-4.0",
            licence_page="https://www.openslr.org/12/",
            split_rule="official subset: train-clean-100 train, dev-clean val, test-clean test",
            urls=openslr(12, "train-clean-100.tar.gz")
            + openslr(12, "dev-clean.tar.gz")
            + openslr(12, "test-clean.tar.gz"),
            note="English only. Urdu speech is a known gap until a free source is verified.",
        ),
        Source(
            key="musan",
            name="MUSAN (music and noise parts)",
            role="music and background noise",
            licence="CC-BY-4.0",
            licence_page="https://www.openslr.org/17/",
            split_rule="file: hashed by file name",
            urls=openslr(17, "musan.tar.gz"),
        ),
        Source(
            key="rirs",
            name="RIRS_NOISES room impulse responses",
            role="room echo",
            licence="Apache-2.0",
            licence_page="https://www.openslr.org/28/",
            split_rule="room: hashed by room folder",
            urls=openslr(28, "rirs_noises.zip"),
        ),
        Source(
            key="clap",
            name="CLAP laion/clap-htsat-fused",
            role="trigger embeddings (never a judge)",
            licence="Apache-2.0",
            licence_page="https://huggingface.co/laion/clap-htsat-fused",
            split_rule="not data",
        ),
        Source(
            key="panns",
            name="PANNs Cnn14 AudioSet tagger",
            role="independent realism judge (never used in training)",
            licence="CC-BY-4.0 (checkpoints); MIT (code)",
            licence_page="https://zenodo.org/records/3987831",
            split_rule="not data",
        ),
    )
}
