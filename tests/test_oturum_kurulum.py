"""scripts/oturum_kurulum.sh betiğinin testleri.

Betik sahte bir HOME ile çalıştırılır; gerçek ~/.claude/ dosyalarına dokunulmaz.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from conftest import KOK

BETIK = KOK / "scripts/oturum_kurulum.sh"
AJANLAR = sorted(p.name for p in (KOK / ".claude/agents").glob("*.md"))


def kurulum(ev):
    ortam = dict(os.environ, HOME=str(ev))
    ortam.pop("CLAUDE_PROJECT_DIR", None)
    return subprocess.run(["sh", str(BETIK)], capture_output=True, text=True, env=ortam, check=True)


def ayar_oku(ev):
    return json.loads((ev / ".claude/settings.json").read_text(encoding="utf-8"))


def komutlar(ayar):
    return [h["command"] for g in ayar["hooks"]["PreToolUse"] for h in g["hooks"]]


@pytest.fixture
def ev(tmp_path):
    return tmp_path / "ev"


def test_ajanlar_ve_hooklar_kopyalanir(ev):
    kurulum(ev)
    assert len(AJANLAR) == 5
    assert sorted(p.name for p in (ev / ".claude/agents").glob("*.md")) == AJANLAR
    hook_dizini = ev / ".claude/hooks/malzeme-kabul-ai"
    for ad in ("calistir.sh", "gold_koruma.py", "tests_kilidi.py", "_yazma_analizi.py"):
        assert (hook_dizini / ad).is_file()


def test_yollar_mutlaktir(ev):
    kurulum(ev)
    ayar = ayar_oku(ev)
    assert f"Edit(/{KOK}/data/gold/**)" in ayar["permissions"]["deny"]
    for komut in komutlar(ayar):
        assert "${CLAUDE_PROJECT_DIR}" not in komut
        assert str(ev / ".claude/hooks/malzeme-kabul-ai/calistir.sh") in komut
        assert f"CLAUDE_PROJECT_DIR={KOK}" in komut
    gruplar = ayar["hooks"]["PreToolUse"]
    assert all(h.get("onFailure") == "block" for g in gruplar for h in g["hooks"])


def test_iki_kez_calismak_ayni_sonucu_verir(ev):
    kurulum(ev)
    ilk = ayar_oku(ev)
    kurulum(ev)
    assert ayar_oku(ev) == ilk
    assert len(komutlar(ilk)) == 2


def test_var_olan_baska_ayarlar_korunur(ev):
    (ev / ".claude").mkdir(parents=True)
    baska_hook = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo baska"}]}
    (ev / ".claude/settings.json").write_text(
        json.dumps(
            {
                "model": "x",
                "permissions": {"deny": ["Bash(rm -rf:*)"]},
                "hooks": {"PreToolUse": [baska_hook]},
            }
        )
    )
    kurulum(ev)
    kurulum(ev)
    ayar = ayar_oku(ev)
    assert ayar["model"] == "x"
    assert ayar["permissions"]["deny"].count("Bash(rm -rf:*)") == 1
    assert ayar["hooks"]["PreToolUse"].count(baska_hook) == 1
    # baska_hook + depodaki tek PreToolUse grubu (içinde iki hook)
    assert len(ayar["hooks"]["PreToolUse"]) == 2
    assert len(komutlar(ayar)) == 3


def hook_komutu_calistir(komut, girdi, cwd):
    ortam = dict(os.environ)
    ortam.pop("CLAUDE_PROJECT_DIR", None)
    return subprocess.run(komut, shell=True, input=json.dumps(girdi), capture_output=True, text=True, env=ortam, cwd=cwd)


def test_kurulan_gold_hooku_ust_klasorden_de_engeller(ev, tmp_path):
    """Oturum depo dışında başlasa bile kurulan hook data/gold yazmasını engeller."""
    kurulum(ev)
    komut = next(k for k in komutlar(ayar_oku(ev)) if "gold_koruma.py" in k)
    ust = tmp_path / "ust"
    ust.mkdir()

    engel = hook_komutu_calistir(
        komut,
        {"tool_name": "Write", "tool_input": {"file_path": str(KOK / "data/gold/deneme.txt")}, "cwd": str(ust)},
        ust,
    )
    assert engel.returncode == 2
    assert "data/gold" in engel.stderr

    bash_engel = hook_komutu_calistir(
        komut,
        {"tool_name": "Bash", "tool_input": {"command": f"echo x > {KOK}/data/gold/deneme.txt"}, "cwd": str(ust)},
        ust,
    )
    assert bash_engel.returncode == 2

    serbest = hook_komutu_calistir(
        komut,
        {"tool_name": "Write", "tool_input": {"file_path": str(KOK / "data/raw/deneme.txt")}, "cwd": str(ust)},
        ust,
    )
    assert serbest.returncode == 0
    assert not (KOK / "data/gold/deneme.txt").exists()
