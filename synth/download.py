"""Download datasets with mirrors, resume, checksums and safe extraction.

Large tar archives are extracted while streaming, keeping only the members the
pipeline needs, so an 11 GB archive never has to sit on disk. Every finished step
writes a marker file, so a restarted notebook skips work already done.
"""

from __future__ import annotations

import hashlib
import json
import tarfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO, Any

from synth.sources import SOURCES

CHUNK = 1 << 20
USER_AGENT = "anechoic-chamber-data-pipeline"
Opener = Callable[..., Any]


class DownloadError(RuntimeError):
    pass


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _close(error: BaseException) -> None:
    """HTTP errors hold an open response; close it so sockets are not leaked."""
    if isinstance(error, urllib.error.HTTPError):
        error.close()


def _open(url: str, opener: Opener, start: int = 0) -> Any:
    headers = {"User-Agent": USER_AGENT}
    if start:
        headers["Range"] = f"bytes={start}-"
    return opener(urllib.request.Request(url, headers=headers), timeout=120)


def download(
    urls: Sequence[str],
    dest: Path,
    sha256: str | None = None,
    expected_size: int | None = None,
    opener: Opener = urllib.request.urlopen,
    log: Callable[[str], None] = print,
) -> Path:
    """Fetch the first mirror that works into dest, resuming a partial .part file."""
    if dest.is_file() and (sha256 is None or sha256_of(dest) == sha256):
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    errors = []
    for url in urls:
        try:
            start = part.stat().st_size if part.is_file() else 0
            with _open(url, opener, start) as response:
                mode = "ab" if start and response.status == 206 else "wb"
                with part.open(mode) as handle:
                    for block in iter(lambda: response.read(CHUNK), b""):
                        handle.write(block)
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            _close(error)
            errors.append(f"{url}: {error}")
            log(f"mirror failed, trying next: {url}")
    else:
        raise DownloadError("all mirrors failed: " + "; ".join(errors))

    size = part.stat().st_size
    if expected_size is not None and size != expected_size:
        part.unlink()
        raise DownloadError(f"{dest.name}: size {size}, expected {expected_size}")
    if sha256 is not None and sha256_of(part) != sha256:
        part.unlink()
        raise DownloadError(f"{dest.name}: checksum mismatch")
    part.replace(dest)
    return dest


def safe_target(root: Path, member: str) -> Path:
    """Resolve an archive member under root, refusing absolute or escaping paths."""
    pure = PurePosixPath(member)
    if pure.is_absolute() or ".." in pure.parts or ":" in member:
        raise DownloadError(f"unsafe archive member: {member}")
    target = (root / Path(*pure.parts)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise DownloadError(f"unsafe archive member: {member}")
    return target


def _write_member(source: IO[bytes], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        for block in iter(lambda: source.read(CHUNK), b""):
            handle.write(block)


def _marker(dest_dir: Path, name: str) -> Path:
    return dest_dir / f".done-{name}.json"


def stream_extract_tar(
    urls: Sequence[str],
    dest_dir: Path,
    keep: Callable[[str], bool],
    name: str,
    opener: Opener = urllib.request.urlopen,
    log: Callable[[str], None] = print,
) -> int:
    """Stream a .tar.gz from the first working mirror, extracting only kept files."""
    marker = _marker(dest_dir, name)
    if marker.is_file():
        return int(json.loads(marker.read_text())["files"])
    errors = []
    for url in urls:
        try:
            count = 0
            with _open(url, opener) as response, tarfile.open(fileobj=response, mode="r|gz") as tar:
                for member in tar:
                    if not member.isfile() or not keep(member.name):
                        continue
                    source = tar.extractfile(member)
                    if source is None:
                        continue
                    _write_member(source, safe_target(dest_dir, member.name))
                    count += 1
                    if count % 2000 == 0:
                        log(f"{name}: {count} files")
            marker.write_text(json.dumps({"files": count, "url": url}))
            return count
        except (urllib.error.URLError, TimeoutError, ConnectionError, tarfile.TarError) as error:
            _close(error)
            errors.append(f"{url}: {error}")
            log(f"mirror failed, trying next: {url}")
    raise DownloadError("all mirrors failed: " + "; ".join(errors))


def extract_zip(archive: Path, dest_dir: Path, keep: Callable[[str], bool], name: str) -> int:
    marker = _marker(dest_dir, name)
    if marker.is_file():
        return int(json.loads(marker.read_text())["files"])
    count = 0
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if info.is_dir() or not keep(info.filename):
                continue
            with bundle.open(info) as source:
                _write_member(source, safe_target(dest_dir, info.filename))
            count += 1
    marker.write_text(json.dumps({"files": count, "archive": archive.name}))
    return count


@dataclass(frozen=True)
class Dataset:
    name: str
    source: str
    urls: tuple[str, ...]
    kind: str  # "tar" streams; "zip" downloads then extracts
    keep: Callable[[str], bool]


def _librispeech(subset: str) -> Dataset:
    urls = tuple(url for url in SOURCES["librispeech"].urls if url.endswith(f"/{subset}.tar.gz"))
    return Dataset(
        name=f"librispeech-{subset}",
        source="librispeech",
        urls=urls,
        kind="tar",
        keep=lambda member: member.endswith(".flac") or member.endswith("SPEAKERS.TXT"),
    )


DATASETS: dict[str, Dataset] = {
    dataset.name: dataset
    for dataset in (
        Dataset(
            name="esc50",
            source="esc50",
            urls=SOURCES["esc50"].urls,
            kind="zip",
            keep=lambda m: "/audio/" in m and m.endswith(".wav") or m.endswith("meta/esc50.csv"),
        ),
        Dataset(
            name="fsd50k-ground-truth",
            source="fsd50k",
            urls=SOURCES["fsd50k"].urls[:1],
            kind="zip",
            keep=lambda m: m.endswith(".csv"),
        ),
        Dataset(
            name="fsd50k-metadata",
            source="fsd50k",
            urls=SOURCES["fsd50k"].urls[1:],
            kind="zip",
            keep=lambda m: m.endswith(".json") or m.endswith(".csv"),
        ),
        _librispeech("train-clean-100"),
        _librispeech("dev-clean"),
        _librispeech("test-clean"),
        Dataset(
            name="musan",
            source="musan",
            urls=SOURCES["musan"].urls,
            kind="tar",
            keep=lambda m: (
                (m.startswith("musan/music/") or m.startswith("musan/noise/"))
                and m.endswith(".wav")
            ),
        ),
        Dataset(
            name="rirs",
            source="rirs",
            urls=SOURCES["rirs"].urls,
            kind="zip",
            keep=lambda m: (
                m.endswith(".wav")
                and ("real_rirs_isotropic_noises/" in m or "simulated_rirs/" in m)
                and "noise" not in PurePosixPath(m).name.lower()
            ),
        ),
    )
}


def fetch(
    dataset: Dataset,
    root: Path,
    opener: Opener = urllib.request.urlopen,
    log: Callable[[str], None] = print,
) -> int:
    """Download and extract one dataset under root/<name>/; returns files kept."""
    dest = root / dataset.name
    dest.mkdir(parents=True, exist_ok=True)
    if dataset.kind == "tar":
        return stream_extract_tar(dataset.urls, dest, dataset.keep, dataset.name, opener, log)
    archive = download(dataset.urls, root / "_archives" / f"{dataset.name}.zip", opener=opener)
    count = extract_zip(archive, dest, dataset.keep, dataset.name)
    archive.unlink(missing_ok=True)
    return count
