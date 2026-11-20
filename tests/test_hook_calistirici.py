"""scripts/hooks/calistir.sh: hook betiğini bulunan Python ile çalıştırır."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from conftest import KOK

CALISTIRICI = KOK / "scripts/hooks/calistir.sh"
pytestmark = pytest.mark.skipif(shutil.which("sh") is None, reason="sh yok")


def calistir(betik, girdi, ortam=None):
    return subprocess.run(
        ["sh", str(CALISTIRICI), betik],
        input=json.dumps(girdi),
        capture_output=True,
        text=True,
        env=ortam or dict(os.environ),
    )


def test_engel_kodu_ve_mesaji_aktarilir(proje):
    girdi = {"tool_name": "Bash", "tool_input": {"command": "rm data/gold/etiket.json"}}
    sonuc = calistir("gold_koruma.py", dict(girdi, cwd=str(proje)))
    assert sonuc.returncode == 2
    assert "data/gold" in sonuc.stderr


def test_izin_kodu_aktarilir(proje):
    girdi = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(proje)}
    assert calistir("gold_koruma.py", girdi).returncode == 0


def test_python_bulunamazsa_engeller(proje, tmp_path):
    bos = tmp_path / "bos_path"
    bos.mkdir()
    # sh ve dirname dışında hiçbir şey bulunmayan PATH
    for arac in ("dirname",):
        (bos / arac).symlink_to(shutil.which(arac))
    ortam = {"PATH": str(bos)}
    sonuc = subprocess.run(
        [shutil.which("sh"), str(CALISTIRICI), "gold_koruma.py"],
        input="{}",
        capture_output=True,
        text=True,
        env=ortam,
    )
    assert sonuc.returncode == 2
    assert "Python" in sonuc.stderr
