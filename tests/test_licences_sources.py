"""Licence rules and the source registry."""

import pytest

from synth import licences
from synth.sources import SOURCES


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0"),
        ("https://creativecommons.org/licenses/by/4.0/", "CC-BY-4.0"),
        ("http://creativecommons.org/licenses/by/3.0/", "CC-BY-3.0"),
        ("http://creativecommons.org/licenses/by-nc/3.0/", "CC-BY-NC-3.0"),
        ("http://creativecommons.org/licenses/sampling+/1.0/", "CC-Sampling-Plus-1.0"),
        ("https://creativecommons.org/publicdomain/mark/1.0/", "Public-Domain"),
        ("Creative Commons 0", "CC0-1.0"),
        ("Attribution", "CC-BY-4.0"),
        ("Attribution NonCommercial", "CC-BY-NC-4.0"),
        ("Apache 2.0", "Apache-2.0"),
        ("CC-BY-4.0", "CC-BY-4.0"),
        ("", "unknown"),
        ("All rights reserved", "unknown"),
        ("https://creativecommons.org/licenses/by-nd/4.0/", "unknown"),
    ],
)
def test_normalise(raw: str, expected: str) -> None:
    assert licences.normalise(raw) == expected


@pytest.mark.parametrize("licence", ["CC0-1.0", "CC-BY-3.0", "CC-BY-4.0", "Public-Domain"])
def test_release_allowed(licence: str) -> None:
    assert licences.release_allowed(licence)
    assert licences.training_allowed(licence)


@pytest.mark.parametrize("licence", ["CC-BY-NC-3.0", "CC-BY-NC-4.0", "Apache-2.0"])
def test_training_only(licence: str) -> None:
    assert not licences.release_allowed(licence)
    assert licences.training_allowed(licence)


@pytest.mark.parametrize("licence", ["CC-Sampling-Plus-1.0", "unknown"])
def test_never_used(licence: str) -> None:
    assert not licences.release_allowed(licence)
    assert not licences.training_allowed(licence)


def test_attribution_flag() -> None:
    assert licences.needs_attribution("CC-BY-4.0")
    assert not licences.needs_attribution("CC0-1.0")


def test_release_filter_names_only_cc0_and_by() -> None:
    assert licences.FREESOUND_RELEASE_FILTER == 'license:("Creative Commons 0" OR "Attribution")'


def test_every_source_is_complete() -> None:
    for key, source in SOURCES.items():
        assert source.key == key
        assert source.licence and source.licence_page.startswith("https://")
        assert source.split_rule
        assert all(url.startswith("https://") for url in source.urls)


def test_download_sources_have_urls() -> None:
    for key in ("esc50", "fsd50k", "librispeech", "musan", "rirs"):
        assert SOURCES[key].urls, key


def test_non_commercial_sources_are_marked_training_only() -> None:
    assert "training only" in SOURCES["esc50"].note.lower()
