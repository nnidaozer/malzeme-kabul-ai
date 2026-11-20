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
