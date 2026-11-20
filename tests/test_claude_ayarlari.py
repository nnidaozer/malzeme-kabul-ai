""".claude/ ayarlarının ve alt ajan tanımlarının beklenen kuralları içerdiğini denetler."""

from __future__ import annotations

import json
import re

import pytest

from conftest import KOK

AYAR = json.loads((KOK / ".claude/settings.json").read_text(encoding="utf-8"))
AJANLAR = KOK / ".claude/agents"


def frontmatter(yol):
    """Basit YAML frontmatter okuyucu (anahtar: değer satırları)."""
    metin = yol.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", metin, re.S)
    assert m, f"{yol.name}: frontmatter yok"
    alanlar = {}
    for satir in m.group(1).splitlines():
        anahtar, _, deger = satir.partition(":")
        alanlar[anahtar.strip()] = deger.strip()
    return alanlar


def araclar(alan):
    return {a.strip() for a in alan.split(",") if a.strip()}


def test_gold_icin_edit_yasagi_var():
    assert "Edit(/data/gold/**)" in AYAR["permissions"]["deny"]


@pytest.mark.parametrize("betik", ["gold_koruma.py", "tests_kilidi.py"])
def test_hook_lar_yazma_araclarinda_ve_bash_te_calisir(betik):
    for grup in AYAR["hooks"]["PreToolUse"]:
        for hook in grup["hooks"]:
            if betik in hook["command"]:
                eslesen = set(grup["matcher"].split("|"))
                assert {"Write", "Edit", "NotebookEdit", "Bash", "PowerShell"} <= eslesen
                assert hook.get("onFailure") == "block"
                assert "scripts/hooks/calistir.sh" in hook["command"]
                assert (KOK / "scripts/hooks" / betik).is_file()
                return
    pytest.fail(f"{betik} settings.json'da tanımlı değil")


BEKLENEN_AJANLAR = {
    "planlayici": {"Read", "Grep", "Glob"},
    "test-yazari": {"Read", "Grep", "Glob", "Write", "Edit", "Bash"},
    "uygulayici": {"Read", "Grep", "Glob", "Write", "Edit", "Bash"},
    "gozden-geciren": {"Read", "Grep", "Glob"},
    "degerlendirme-kosucusu": {"Read", "Grep", "Glob", "Bash"},
}


@pytest.mark.parametrize("ad,beklenen", BEKLENEN_AJANLAR.items())
def test_ajan_araclari(ad, beklenen):
    alanlar = frontmatter(AJANLAR / f"{ad}.md")
    assert alanlar["name"] == ad
    assert alanlar["description"]
    assert araclar(alanlar["tools"]) == beklenen


def test_degerlendirme_kosucusunda_yazma_araclari_yasak():
    alanlar = frontmatter(AJANLAR / "degerlendirme-kosucusu.md")
    assert {"Write", "Edit", "NotebookEdit"} <= araclar(alanlar["disallowedTools"])


def test_tests_kilidi_uygulayici_adini_kullanir():
    from conftest import betik_yukle

    kilit = betik_yukle("scripts/hooks/tests_kilidi.py")
    assert kilit.KILITLI_AJANLAR == {"uygulayici"}
    assert frontmatter(AJANLAR / "uygulayici.md")["name"] in kilit.KILITLI_AJANLAR
