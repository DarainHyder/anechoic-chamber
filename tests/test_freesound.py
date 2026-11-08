"""The Freesound collector, against a fake server (no network)."""

import json
import urllib.parse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from synth import freesound
from synth.freesound import FreesoundClient, Manifest, Response

KEY = "secret-key-123"
CC0 = "http://creativecommons.org/publicdomain/zero/1.0/"
BY = "https://creativecommons.org/licenses/by/4.0/"
NC = "http://creativecommons.org/licenses/by-nc/3.0/"


def sound(sound_id: int, licence: str = CC0, user: str = "alice") -> dict[str, Any]:
    return {
        "id": sound_id,
        "name": f"clip {sound_id}",
        "username": user,
        "license": licence,
        "tags": ["chewing"],
        "duration": 3.5,
        "previews": {"preview-hq-ogg": f"https://cdn.freesound.org/previews/{sound_id}.ogg"},
    }


class FakeServer:
    def __init__(self, pages: list[list[dict[str, Any]]], fail_first: int = 0) -> None:
        self.pages = pages
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.fail_first = fail_first

    def __call__(self, url: str, headers: Mapping[str, str]) -> Response:
        self.calls.append((url, dict(headers)))
        if self.fail_first > 0:
            self.fail_first -= 1
            return Response(429, {"Retry-After": "7"}, b"")
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc == "cdn.freesound.org":
            return Response(200, {}, b"OggS fake audio " + parsed.path.encode())
        params = urllib.parse.parse_qs(parsed.query)
        page = int(params["page"][0])
        results = self.pages[page - 1] if page <= len(self.pages) else []
        body = {"results": results, "next": "more" if page < len(self.pages) else None}
        return Response(200, {}, json.dumps(body).encode())

    def api_calls(self) -> list[tuple[str, dict[str, str]]]:
        return [call for call in self.calls if "/apiv2/" in call[0]]

    def preview_calls(self) -> list[tuple[str, dict[str, str]]]:
        return [call for call in self.calls if "cdn.freesound.org" in call[0]]


def client(server: FakeServer, sleeps: list[float] | None = None) -> FreesoundClient:
    log = sleeps if sleeps is not None else []
    return FreesoundClient(KEY, transport=server, sleep=log.append, clock=lambda: 0.0)


def run(server: FakeServer, tmp_path: Path, per_group: int = 10, **kwargs: Any) -> Any:
    c = client(server)
    candidates = freesound.search_candidates(c, {"chewing": ["chewing"]}, "f", per_query=50)
    return freesound.collect(
        c, candidates, tmp_path / "bank", Manifest(tmp_path / "m.jsonl"), per_group, **kwargs
    )


def test_search_sends_the_release_filter_and_key_only_to_the_api(tmp_path: Path) -> None:
    server = FakeServer([[sound(1), sound(2)]])
    c = client(server)
    filters = freesound.build_filter(1, 30)
    stats = freesound.collect(
        c,
        freesound.search_candidates(c, {"chewing": ["chewing"]}, filters, 10),
        tmp_path / "bank",
        Manifest(tmp_path / "m.jsonl"),
        per_group=10,
    )
    assert stats.kept == 2
    url, headers = server.api_calls()[0]
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert 'license:("Creative Commons 0" OR "Attribution")' in query["filter"][0]
    assert "duration:[1 TO 30]" in query["filter"][0]
    assert headers == {"Authorization": f"Token {KEY}"}
    assert KEY not in url
    assert all(headers == {} for _, headers in server.preview_calls())


def test_non_release_licences_are_skipped_even_if_returned(tmp_path: Path) -> None:
    server = FakeServer([[sound(1, NC), sound(2, BY), sound(3, "")]])
    stats = run(server, tmp_path)
    assert (stats.kept, stats.skipped_licence) == (1, 2)
    records = Manifest(tmp_path / "m.jsonl").load()
    assert [r.freesound_id for r in records] == [2]
    assert records[0].licence == "CC-BY-4.0"
    assert records[0].source_url == "https://freesound.org/s/2/"


def test_excluded_uploaders_are_skipped(tmp_path: Path) -> None:
    server = FakeServer([[sound(1, user="Test_Set_User"), sound(2)]])
    stats = run(server, tmp_path, exclude_usernames=["test_set_user"])
    assert (stats.kept, stats.skipped_user) == (1, 1)


def test_records_hold_licence_author_and_checksum(tmp_path: Path) -> None:
    run(FakeServer([[sound(5, BY, "bob")]]), tmp_path)
    record = Manifest(tmp_path / "m.jsonl").load()[0]
    saved = tmp_path / "bank" / record.file
    assert saved.is_file()
    assert record.username == "bob"
    assert record.origin == "search:chewing"
    import hashlib

    assert record.sha256 == hashlib.sha256(saved.read_bytes()).hexdigest()


def test_resume_does_not_fetch_again(tmp_path: Path) -> None:
    run(FakeServer([[sound(1), sound(2)]]), tmp_path)
    server = FakeServer([[sound(1), sound(2), sound(3)]])
    stats = run(server, tmp_path)
    assert stats.kept == 1
    assert stats.skipped_duplicate == 2
    assert len(server.preview_calls()) == 1


def test_per_group_cap(tmp_path: Path) -> None:
    stats = run(FakeServer([[sound(i) for i in range(1, 9)]]), tmp_path, per_group=3)
    assert stats.kept == 3


def test_paging_follows_next(tmp_path: Path) -> None:
    server = FakeServer([[sound(1)], [sound(2)], [sound(3)]])
    assert run(server, tmp_path).kept == 3
    assert len(server.api_calls()) == 3


def test_rate_limit_waits_for_retry_after() -> None:
    server = FakeServer([[sound(1)]], fail_first=2)
    sleeps: list[float] = []
    data = client(server, sleeps).search("chewing", "f")
    assert data["results"][0]["id"] == 1
    assert sleeps.count(7.0) == 2


def test_gives_up_after_retries_without_leaking_the_key() -> None:
    server = FakeServer([[sound(1)]], fail_first=99)
    with pytest.raises(freesound.FreesoundError) as error:
        client(server).search("chewing", "f")
    assert KEY not in str(error.value)
    assert "429" in str(error.value)


def test_pacing_spaces_api_calls() -> None:
    times = iter([0.0, 0.0, 0.2, 0.2])
    sleeps: list[float] = []
    c = FreesoundClient(
        KEY, transport=FakeServer([[sound(1)]]), sleep=sleeps.append, clock=lambda: next(times)
    )
    c.search("a", "f")
    c.search("a", "f")
    assert sleeps and sleeps[-1] == pytest.approx(0.8)


def test_repr_hides_the_key() -> None:
    assert KEY not in repr(client(FakeServer([])))


def test_preview_pointing_at_the_api_is_refused() -> None:
    bad = sound(1)
    bad["previews"]["preview-hq-ogg"] = "https://freesound.org/apiv2/sounds/1/download/"
    with pytest.raises(freesound.FreesoundError):
        client(FakeServer([])).fetch_preview(bad)


def test_id_candidates_batch_ids_into_filters() -> None:
    server = FakeServer([[sound(1), sound(2)]])
    c = client(server)
    found = list(freesound.id_candidates(c, {"typing": [1, 2]}, "f", batch=100))
    assert [(group, origin) for group, origin, _ in found] == [("typing", "fsd50k")] * 2
    query = urllib.parse.parse_qs(urllib.parse.urlparse(server.api_calls()[0][0]).query)
    assert query["filter"][0].endswith("id:(1 OR 2)")
