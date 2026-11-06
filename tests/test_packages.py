"""The Python packages import and report a version."""

import importlib
import re

import pytest


@pytest.mark.parametrize("name", ["api", "eval", "ml", "synth"])
def test_package_imports(name: str) -> None:
    module = importlib.import_module(name)
    assert re.fullmatch(r"\d+\.\d+\.\d+", module.__version__)
