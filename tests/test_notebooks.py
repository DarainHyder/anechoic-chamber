"""Kaggle notebooks follow the protocol: header, smoke flag, GPU check, secrets, zip."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

NOTEBOOKS = Path(__file__).resolve().parent.parent / "kaggle" / "notebooks"
K1 = NOTEBOOKS / "K1_data_bank.ipynb"
KEY_PATTERNS = re.compile(
    r"gsk_[A-Za-z0-9]{10,}|hf_[A-Za-z0-9]{10,}|KGAT_[a-f0-9]{10,}|AIza[\w-]{20,}"
)


def load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def sources(notebook: dict[str, Any], kind: str) -> list[str]:
    return ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == kind]


@pytest.fixture(scope="module")
def k1() -> dict[str, Any]:
    return load(K1)


def test_header_states_the_run_contract(k1: dict[str, Any]) -> None:
    header = "".join(k1["cells"][0]["source"])
    assert k1["cells"][0]["cell_type"] == "markdown"
    for word in ("Purpose", "Inputs", "Outputs", "Accelerator", "Internet", "Runtime", "Secrets"):
        assert f"**{word}**" in header, word


def test_every_code_cell_is_valid_python(k1: dict[str, Any]) -> None:
    for index, source in enumerate(sources(k1, "code")):
        compile(source, f"K1 cell {index}", "exec")


def test_no_saved_outputs(k1: dict[str, Any]) -> None:
    assert all(not c.get("outputs") for c in k1["cells"] if c["cell_type"] == "code")


def test_smoke_flag_commit_pin_and_guard(k1: dict[str, Any]) -> None:
    config = sources(k1, "code")[0]
    assert "SMOKE_TEST = True" in config
    commit = re.search(r'REPO_COMMIT = "([^"]+)"', config)
    assert commit and re.fullmatch(r"[0-9a-f]{40}|PENDING_PUSH", commit.group(1))
    assert 'if REPO_COMMIT == "PENDING_PUSH":\n    raise RuntimeError' in config


def test_setup_pins_packages_seeds_and_checks_the_gpu(k1: dict[str, Any]) -> None:
    setup = sources(k1, "code")[1]
    assert re.search(r'"pyloudnorm==[\d.]+"', setup) and re.search(
        r'"panns-inference==[\d.]+"', setup
    )
    for seed_call in ("random.seed(SEED)", "np.random.seed(SEED)", "torch.manual_seed(SEED)"):
        assert seed_call in setup
    assert "torch.cuda.is_available()" in setup
    assert "if not SMOKE_TEST and not HAS_GPU:\n    raise RuntimeError" in setup


def test_secrets_come_from_kaggle_only(k1: dict[str, Any]) -> None:
    code = "\n".join(sources(k1, "code"))
    assert 'UserSecretsClient().get_secret("FREESOUND_API_KEY")' in code
    assert not KEY_PATTERNS.search(json.dumps(k1))
    assert not re.search(r"(API_KEY|TOKEN|SECRET)\s*=\s*['\"]", code)


def test_runs_repo_code_and_zips_outputs(k1: dict[str, Any]) -> None:
    code = "\n".join(sources(k1, "code"))
    assert "k1.run(cfg, deps" in code
    assert "git" in code and "checkout" in code
    assert 'shutil.make_archive(str(ZIP_PATH), "zip", root_dir=OUT_DIR)' in code
    assert 'OUT_DIR = WORK / "outputs" / "K1_data_bank"' in code
    assert "RESUME_FROM" in code


def test_run_guide_covers_settings_secret_and_download() -> None:
    guide = (NOTEBOOKS / "K1_data_bank_RUN.md").read_text(encoding="utf-8")
    for needed in (
        "GPU T4",
        "Internet",
        "FREESOUND_API_KEY",
        "SMOKE_TEST",
        "K1_data_bank_outputs.zip",
        "kaggle_outputs/K1_data_bank/",
        "k1-resume",
        "DONE",
    ):
        assert needed in guide, needed
