"""Downloads against a local HTTP server: mirrors, resume, checksums, safe extraction."""

import hashlib
import io
import tarfile
import threading
import zipfile
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from synth import download
from synth.download import DATASETS, DownloadError


class RangeHandler(SimpleHTTPRequestHandler):
    """Serves files with optional byte-range support, quietly."""

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        start = 0
        header = self.headers.get("Range")
        if header and header.startswith("bytes="):
            start = int(header[6:].split("-")[0])
            self.send_response(206)
        else:
            self.send_response(200)
        body = data[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    root = tmp_path / "served"
    root.mkdir()

    def handler(*args: Any, **kwargs: Any) -> RangeHandler:
        return RangeHandler(*args, directory=str(root), **kwargs)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", root
    httpd.shutdown()
    httpd.server_close()


def quiet(_: str) -> None:
    pass


def test_download_with_checksum(server: tuple[str, Path], tmp_path: Path) -> None:
    base, root = server
    (root / "a.bin").write_bytes(b"x" * 5000)
    digest = hashlib.sha256(b"x" * 5000).hexdigest()
    out = download.download([f"{base}/a.bin"], tmp_path / "out" / "a.bin", sha256=digest, log=quiet)
    assert out.read_bytes() == b"x" * 5000


def test_falls_back_to_the_next_mirror(server: tuple[str, Path], tmp_path: Path) -> None:
    base, root = server
    (root / "a.bin").write_bytes(b"data")
    out = download.download(
        ["http://127.0.0.1:9/a.bin", f"{base}/missing.bin", f"{base}/a.bin"],
        tmp_path / "a.bin",
        log=quiet,
    )
    assert out.read_bytes() == b"data"


def test_resumes_a_partial_download(server: tuple[str, Path], tmp_path: Path) -> None:
    base, root = server
    payload = bytes(range(256)) * 40
    (root / "big.bin").write_bytes(payload)
    dest = tmp_path / "big.bin"
    (tmp_path / "big.bin.part").write_bytes(payload[:1000])
    download.download([f"{base}/big.bin"], dest, expected_size=len(payload), log=quiet)
    assert dest.read_bytes() == payload


def test_bad_checksum_is_rejected(server: tuple[str, Path], tmp_path: Path) -> None:
    base, root = server
    (root / "a.bin").write_bytes(b"data")
    with pytest.raises(DownloadError, match="checksum"):
        download.download([f"{base}/a.bin"], tmp_path / "a.bin", sha256="0" * 64, log=quiet)
    assert not (tmp_path / "a.bin").exists()


def test_all_mirrors_failing_raises(tmp_path: Path) -> None:
    with pytest.raises(DownloadError, match="all mirrors failed"):
        download.download(["http://127.0.0.1:9/x"], tmp_path / "x", log=quiet)


def make_tar(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_stream_extract_keeps_only_wanted_members(server: tuple[str, Path], tmp_path: Path) -> None:
    base, root = server
    (root / "c.tar.gz").write_bytes(
        make_tar({"musan/music/a.wav": b"m", "musan/speech/b.wav": b"s", "musan/noise/c.wav": b"n"})
    )
    dest = tmp_path / "musan"
    keep = DATASETS["musan"].keep
    count = download.stream_extract_tar([f"{base}/c.tar.gz"], dest, keep, "musan", log=quiet)
    assert count == 2
    assert (dest / "musan/music/a.wav").read_bytes() == b"m"
    assert not (dest / "musan/speech/b.wav").exists()
    (root / "c.tar.gz").unlink()
    again = download.stream_extract_tar([f"{base}/c.tar.gz"], dest, keep, "musan", log=quiet)
    assert again == 2


@pytest.mark.parametrize("name", ["../evil.wav", "/abs/evil.wav", "a/../../evil.wav", "C:evil.wav"])
def test_unsafe_members_are_refused(tmp_path: Path, name: str) -> None:
    with pytest.raises(DownloadError, match="unsafe"):
        download.safe_target(tmp_path, name)


def test_unsafe_tar_member_stops_extraction(server: tuple[str, Path], tmp_path: Path) -> None:
    base, root = server
    (root / "bad.tar.gz").write_bytes(make_tar({"../../evil.wav": b"x"}))
    with pytest.raises(DownloadError, match="unsafe"):
        download.stream_extract_tar(
            [f"{base}/bad.tar.gz"], tmp_path / "d", lambda _: True, "bad", log=quiet
        )
    assert not (tmp_path / "evil.wav").exists()


def test_fetch_zip_dataset(server: tuple[str, Path], tmp_path: Path) -> None:
    base, root = server
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("ESC-50-master/audio/1-100-A-1.wav", b"w")
        bundle.writestr("ESC-50-master/meta/esc50.csv", b"filename,fold")
        bundle.writestr("ESC-50-master/README.md", b"r")
    (root / "esc.zip").write_bytes(buffer.getvalue())
    dataset = download.Dataset(
        "esc50", "esc50", (f"{base}/esc.zip",), "zip", DATASETS["esc50"].keep
    )
    assert download.fetch(dataset, tmp_path / "data", log=quiet) == 2
    assert (tmp_path / "data/esc50/ESC-50-master/meta/esc50.csv").is_file()
    assert not (tmp_path / "data/_archives/esc50.zip").exists()


@pytest.mark.parametrize(
    ("dataset", "member", "kept"),
    [
        ("librispeech-dev-clean", "LibriSpeech/dev-clean/84/121123/84-121123-0000.flac", True),
        ("librispeech-dev-clean", "LibriSpeech/dev-clean/84/121123/84-121123.trans.txt", False),
        ("librispeech-dev-clean", "LibriSpeech/SPEAKERS.TXT", True),
        ("rirs", "RIRS_NOISES/simulated_rirs/smallroom/Room001/Room001-00001.wav", True),
        (
            "rirs",
            "RIRS_NOISES/real_rirs_isotropic_noises/RVB2014_type1_rir_largeroom1_near_angla.wav",
            True,
        ),
        (
            "rirs",
            "RIRS_NOISES/real_rirs_isotropic_noises/RVB2014_type1_noise_largeroom1_1.wav",
            False,
        ),
        ("rirs", "RIRS_NOISES/pointsource_noises/noise-free-sound-0001.wav", False),
        ("esc50", "ESC-50-master/audio/1-100-A-1.wav", True),
    ],
)
def test_member_filters(dataset: str, member: str, kept: bool) -> None:
    assert DATASETS[dataset].keep(member) is kept


def test_every_dataset_has_https_mirrors() -> None:
    for dataset in DATASETS.values():
        assert dataset.urls and all(url.startswith("https://") for url in dataset.urls)
        assert dataset.kind in {"tar", "zip"}
