"""Licence names, and the rules for what may be trained on or released.

Released assets (clips, demos, test sets shipped publicly) may use only CC0 and
CC BY. Training may also use non-commercial licences, because the product is
free; that choice is recorded in the data card.
"""

from __future__ import annotations

import re

CC0 = "CC0-1.0"
PUBLIC_DOMAIN = "Public-Domain"
UNKNOWN = "unknown"

# Freesound's names, as used in search filters and some responses.
FREESOUND_NAMES = {
    "creative commons 0": CC0,
    "attribution": "CC-BY-4.0",
    "attribution noncommercial": "CC-BY-NC-4.0",
    "sampling+": "CC-Sampling-Plus-1.0",
}
FREESOUND_RELEASE_FILTER = 'license:("Creative Commons 0" OR "Attribution")'

_CC_URL = re.compile(
    r"creativecommons\.org/(?:licenses/(?P<kind>[a-z+-]+)|publicdomain/(?P<pd>zero|mark))"
    r"/(?P<version>\d+\.\d+)"
)
_SPDX_LIKE = {
    "cc0": CC0,
    "cc0-1.0": CC0,
    "cc-by-3.0": "CC-BY-3.0",
    "cc-by-4.0": "CC-BY-4.0",
    "cc by 4.0": "CC-BY-4.0",
    "cc-by-nc-3.0": "CC-BY-NC-3.0",
    "cc-by-nc-4.0": "CC-BY-NC-4.0",
    "apache-2.0": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "mit": "MIT",
}

RELEASE_ALLOWED = {CC0, PUBLIC_DOMAIN, "CC-BY-3.0", "CC-BY-4.0"}
TRAINING_ALLOWED = RELEASE_ALLOWED | {"CC-BY-NC-3.0", "CC-BY-NC-4.0", "Apache-2.0", "MIT"}


def normalise(raw: str) -> str:
    """Map a licence URL or name to one canonical identifier."""
    text = raw.strip().lower()
    if not text:
        return UNKNOWN
    match = _CC_URL.search(text)
    if match:
        version = match.group("version")
        if match.group("pd") == "zero":
            return CC0
        if match.group("pd") == "mark":
            return PUBLIC_DOMAIN
        kind = match.group("kind")
        names = {"by": "CC-BY", "by-nc": "CC-BY-NC", "sampling+": "CC-Sampling-Plus"}
        return f"{names[kind]}-{version}" if kind in names else UNKNOWN
    if text in FREESOUND_NAMES:
        return FREESOUND_NAMES[text]
    return _SPDX_LIKE.get(text, UNKNOWN)


def release_allowed(licence: str) -> bool:
    return licence in RELEASE_ALLOWED


def training_allowed(licence: str) -> bool:
    return licence in TRAINING_ALLOWED


def needs_attribution(licence: str) -> bool:
    return licence.startswith("CC-BY")
