"""Collect CC0 and CC BY clips from Freesound with an API key.

Uses token authentication and downloads the high-quality Ogg previews, because
original files need a browser OAuth login. The key is sent only to the API host,
never to the preview CDN, and never printed or logged.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from synth.licences import FREESOUND_RELEASE_FILTER, normalise, release_allowed

API_ROOT = "https://freesound.org/apiv2"
SEARCH_FIELDS = "id,name,username,license,tags,duration,samplerate,previews,pack,type"
PREVIEW_KEY = "preview-hq-ogg"
PAGE_SIZE = 150
RETRY_STATUSES = {429, 500, 502, 503, 504}
USER_AGENT = "anechoic-chamber-data-pipeline"


class FreesoundError(RuntimeError):
    """A request failed after retries. Messages never contain the key."""


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str, Mapping[str, str]], Response]


def urllib_transport(url: str, headers: Mapping[str, str]) -> Response:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return Response(response.status, dict(response.headers), response.read())
    except urllib.error.HTTPError as error:
        return Response(error.code, dict(error.headers or {}), b"")
    except (urllib.error.URLError, TimeoutError) as error:
        return Response(599, {}, str(error).encode())


@dataclass
class FreesoundClient:
    api_key: str = field(repr=False)
    transport: Transport = urllib_transport
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    min_interval: float = 1.0
    max_retries: int = 5
    _last_api_call: float = field(default=-1e9, repr=False)

    def __repr__(self) -> str:
        return "FreesoundClient(api_key=<hidden>)"

    def _request(self, url: str, headers: Mapping[str, str], *, paced: bool) -> bytes:
        for attempt in range(self.max_retries + 1):
            if paced:
                wait = self.min_interval - (self.clock() - self._last_api_call)
                if wait > 0:
                    self.sleep(wait)
                self._last_api_call = self.clock()
            response = self.transport(url, headers)
            if response.status == 200:
                return response.body
            if response.status not in RETRY_STATUSES and response.status != 599:
                break
            if attempt < self.max_retries:
                retry_after = response.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else min(2.0**attempt, 60.0)
                self.sleep(delay)
        safe_url = url.split("?")[0]
        raise FreesoundError(f"request to {safe_url} failed with status {response.status}")

    def api_get(self, path: str, params: Mapping[str, str | int]) -> dict[str, Any]:
        url = f"{API_ROOT}/{path.strip('/')}/?{urllib.parse.urlencode(params)}"
        body = self._request(url, {"Authorization": f"Token {self.api_key}"}, paced=True)
        result: dict[str, Any] = json.loads(body)
        return result

    def search(self, query: str, filters: str, page: int = 1) -> dict[str, Any]:
        params: dict[str, str | int] = {
            "query": query,
            "filter": filters,
            "fields": SEARCH_FIELDS,
            "page": page,
            "page_size": PAGE_SIZE,
        }
        return self.api_get("search/text", params)

    def iter_search(self, query: str, filters: str, limit: int) -> Iterator[dict[str, Any]]:
        page, yielded = 1, 0
        while yielded < limit:
            data = self.search(query, filters, page)
            results = data.get("results", [])
            for sound in results:
                yield sound
                yielded += 1
                if yielded >= limit:
                    return
            if not data.get("next") or not results:
                return
            page += 1

    def fetch_preview(self, sound: Mapping[str, Any]) -> bytes:
        url = sound["previews"][PREVIEW_KEY]
        if urllib.parse.urlparse(url).path.startswith("/apiv2"):
            raise FreesoundError("preview URL points at the API, refusing to send it")
        return self._request(url, {}, paced=False)


def build_filter(min_seconds: float, max_seconds: float, extra: str = "") -> str:
    parts = [FREESOUND_RELEASE_FILTER, f"duration:[{min_seconds} TO {max_seconds}]"]
    return " ".join(parts + ([extra] if extra else []))


def id_filter(ids: Sequence[int]) -> str:
    return "id:(" + " OR ".join(str(i) for i in ids) + ")"


@dataclass(frozen=True)
class ClipRecord:
    freesound_id: int
    name: str
    username: str
    licence: str
    licence_url: str
    tags: list[str]
    duration: float
    source_url: str
    group: str
    origin: str
    file: str
    sha256: str


class Manifest:
    """Append-only JSON Lines file of kept clips, so a crash can resume."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[ClipRecord]:
        if not self.path.is_file():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [ClipRecord(**json.loads(line)) for line in lines if line.strip()]

    def append(self, record: ClipRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


Candidate = tuple[str, str, Mapping[str, Any]]  # (group, origin, sound)


def search_candidates(
    client: FreesoundClient,
    queries: Mapping[str, Sequence[str]],
    filters: str,
    per_query: int,
) -> Iterator[Candidate]:
    for group, group_queries in queries.items():
        for query in group_queries:
            for sound in client.iter_search(query, filters, per_query):
                yield group, f"search:{query}", sound


def id_candidates(
    client: FreesoundClient,
    ids_by_group: Mapping[str, Sequence[int]],
    filters: str,
    batch: int = 100,
) -> Iterator[Candidate]:
    for group, ids in ids_by_group.items():
        for start in range(0, len(ids), batch):
            chunk = ids[start : start + batch]
            for sound in client.iter_search("", f"{filters} {id_filter(chunk)}", len(chunk)):
                yield group, "fsd50k", sound


@dataclass
class CollectStats:
    kept: int = 0
    skipped_licence: int = 0
    skipped_user: int = 0
    skipped_duplicate: int = 0
    failed: int = 0


def collect(
    client: FreesoundClient,
    candidates: Iterable[Candidate],
    out_dir: Path,
    manifest: Manifest,
    per_group: int,
    exclude_usernames: Iterable[str] = (),
    log: Callable[[str], None] = print,
) -> CollectStats:
    """Download previews for release-safe candidates until each group has per_group clips."""
    existing = manifest.load()
    seen = {record.freesound_id for record in existing}
    counts: dict[str, int] = {}
    for record in existing:
        counts[record.group] = counts.get(record.group, 0) + 1
    excluded = {name.lower() for name in exclude_usernames}
    stats = CollectStats()

    for group, origin, sound in candidates:
        if counts.get(group, 0) >= per_group:
            continue
        sound_id = int(sound["id"])
        if sound_id in seen:
            stats.skipped_duplicate += 1
            continue
        licence = normalise(str(sound.get("license", "")))
        if not release_allowed(licence):
            stats.skipped_licence += 1
            continue
        if str(sound.get("username", "")).lower() in excluded:
            stats.skipped_user += 1
            continue
        try:
            data = client.fetch_preview(sound)
        except (FreesoundError, KeyError) as error:
            stats.failed += 1
            log(f"skip {sound_id}: {error}")
            continue
        path = out_dir / group / f"{sound_id}.ogg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        record = ClipRecord(
            freesound_id=sound_id,
            name=str(sound.get("name", "")),
            username=str(sound.get("username", "")),
            licence=licence,
            licence_url=str(sound.get("license", "")),
            tags=[str(tag) for tag in sound.get("tags", [])],
            duration=float(sound.get("duration", 0.0)),
            source_url=f"https://freesound.org/s/{sound_id}/",
            group=group,
            origin=origin,
            file=path.relative_to(out_dir).as_posix(),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        manifest.append(record)
        seen.add(sound_id)
        counts[group] = counts.get(group, 0) + 1
        stats.kept += 1
        if stats.kept % 25 == 0:
            log(f"kept {stats.kept} clips; per group {counts}")
    return stats
