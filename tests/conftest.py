"""Ortak test yardımcıları."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


def betik_yukle(goreli_yol: str):
    """scripts/ altındaki bir betiği modül olarak yükler."""
    yol = KOK / goreli_yol
    sys.path.insert(0, str(yol.parent))
    spec = importlib.util.spec_from_file_location(yol.stem, yol)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture
def proje(tmp_path, monkeypatch):
    """data/gold/, tests/ ve src/ içeren sahte bir proje kökü."""
    for klasor in ("data/gold", "data/raw", "tests", "src/malzeme_kabul"):
        (tmp_path / klasor).mkdir(parents=True)
    (tmp_path / "data/gold/etiket.json").write_text("{}")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return tmp_path


def hook_calistir(betik: str, girdi: dict, proje_dizini: Path) -> subprocess.CompletedProcess:
    """Hook betiğini Claude Code'un yaptığı gibi stdin'e JSON vererek çalıştırır."""
    ortam = dict(os.environ, CLAUDE_PROJECT_DIR=str(proje_dizini))
    return subprocess.run(
        [sys.executable, str(KOK / betik)],
        input=json.dumps(girdi),
        capture_output=True,
        text=True,
        env=ortam,
        cwd=proje_dizini,
    )


# --- Dil modeli gerektiren testler (pytest -m dil_modeli --dil-modeli MODEL) ---


def pytest_addoption(parser):
    parser.addoption(
        "--dil-modeli",
        metavar="MODEL",
        default=None,
        help="dil_modeli işaretli testleri bu yerel modelle çalıştır (ör. qwen2.5:7b-instruct-q4_K_M)",
    )
    parser.addoption("--dil-modeli-arka-uc", default="ollama", help="ollama ya da llamacpp")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--dil-modeli"):
        return
    atla = pytest.mark.skip(reason="yerel dil modeli verilmedi; çalıştırmak için --dil-modeli MODEL")
    for item in items:
        if "dil_modeli" in item.keywords:
            item.add_marker(atla)


@pytest.fixture(scope="session")
def dil_modeli_istemcisi(request):
    from malzeme_kabul.yerel_model import YerelModelIstemcisi

    return YerelModelIstemcisi(
        model=request.config.getoption("--dil-modeli"),
        arka_uc=request.config.getoption("--dil-modeli-arka-uc"),
    )
