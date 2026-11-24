"""Colab defterinin yapısal denetimi: açılır, kodu sözdizimsel olarak geçerli, kurallara uyar."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
DEFTER = KOK / "notebooks" / "colab_dil_modeli.ipynb"


def _hucreler(tur: str) -> list[str]:
    defter = json.loads(DEFTER.read_text(encoding="utf-8"))
    assert defter["nbformat"] == 4
    return ["".join(h["source"]) for h in defter["cells"] if h["cell_type"] == tur]


def test_kod_hucreleri_gecerli_python():
    for kaynak in _hucreler("code"):
        # "!komut" kabuk satırları Python değildir; yerine boş deyim konur.
        ast.parse(re.sub(r"^(\s*)!.*$", r"\1pass", kaynak, flags=re.M))


def test_defter_colabin_yalniz_gelistirme_icin_oldugunu_soyler():
    metin = "\n".join(_hucreler("markdown"))
    assert "yalnız geliştirme ve ölçüm içindir" in metin
    assert "internetsiz" in metin


def test_defter_yerel_istemciyi_kullanir_ve_golde_yazmaz():
    kod = "\n".join(_hucreler("code"))
    assert "YerelModelIstemcisi" in kod and "deney/dil_modeli_cikar.py" in kod
    assert "127.0.0.1" in kod
    assert "data/gold/" not in kod  # yalnız data/gold_taslak okunur


def test_klonlama_belirteci_secretstan_alir_ve_sizdirmaz():
    kod = "\n".join(_hucreler("code"))
    assert 'userdata.get("GITHUB_TOKEN")' in kod
    assert "http.extraHeader" in kod  # belirteç adrese ve .git/config'e yazılmaz
    assert "@github.com" not in kod and ":{belirtec}@" not in kod
    assert not re.search(r"print\([^)]*belirtec", kod)
    assert 'replace(belirtec, "***")' in kod  # hata çıktısında maskelenir


def test_kurulum_dogrulama_hucresi_var():
    kod = "\n".join(_hucreler("code"))
    assert '"pip", "install", "-q", "-e", "."' in kod
    assert "sys.path.insert(0, SRC)" in kod  # çalışan çekirdek yeni kurulumu görsün
    assert "import malzeme_kabul" in kod and "Kurulum doğrulandı" in kod
