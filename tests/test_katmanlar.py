"""Katman sınırlarının testleri (docs/mimari.md).

- Ürün (src/malzeme_kabul) deney/ paketini hiçbir yerde içe aktarmaz; "yalnız
  dil modeli" modu ürünün içinde bulunmaz.
- Kararı veren katman (kural) dil modeli istemcisini içe aktarmaz.
- Sözleşmeler (sozlesme) çıkarım, karar ya da arayüz katmanına bağlı değildir.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from malzeme_kabul.cikarim import yerel_model

KOK = Path(__file__).resolve().parents[1]
PAKET = KOK / "src" / "malzeme_kabul"
KATMANLAR = ["sozlesme", "belge", "cikarim", "kural", "revizyon", "katalog", "kayit", "hat", "arayuz"]


def ice_aktarimlar(dosya: Path) -> set[str]:
    moduller: set[str] = set()
    for d in ast.walk(ast.parse(dosya.read_text(encoding="utf-8"))):
        if isinstance(d, ast.Import):
            moduller.update(a.name for a in d.names)
        elif isinstance(d, ast.ImportFrom):
            if d.level:
                raise AssertionError(f"{dosya}: göreli içe aktarma yerine tam yol kullan (from malzeme_kabul....)")
            moduller.add(d.module or "")
    return moduller


def katman_dosyalari(katman: str | None = None) -> list[Path]:
    kok = PAKET / katman if katman else PAKET
    return sorted(kok.rglob("*.py"))


def test_klasor_yapisi_mimariye_uyar():
    for katman in KATMANLAR:
        assert (PAKET / katman / "__init__.py").is_file(), katman
    assert (KOK / "deney" / "__init__.py").is_file()
    assert sorted(p.name for p in PAKET.glob("*.py")) == ["__init__.py"]  # bütün kod bir katmanda


@pytest.mark.parametrize("dosya", katman_dosyalari(), ids=lambda p: p.relative_to(PAKET).as_posix())
def test_urun_deneyi_ice_aktarmaz(dosya):
    yasak = {m for m in ice_aktarimlar(dosya) if m == "deney" or m.startswith("deney.")}
    assert not yasak, f"ürün kodu deney/ paketini kullanıyor: {yasak}"


@pytest.mark.parametrize("dosya", katman_dosyalari("kural"), ids=lambda p: p.name)
def test_kural_dil_modeline_baglanmaz(dosya):
    moduller = ice_aktarimlar(dosya)
    assert not {m for m in moduller if m.startswith("malzeme_kabul.cikarim")}


@pytest.mark.parametrize("dosya", katman_dosyalari("sozlesme"), ids=lambda p: p.name)
def test_sozlesme_yalniz_sozlesme_ve_birimlere_baglidir(dosya):
    ic = {m for m in ice_aktarimlar(dosya) if m.startswith("malzeme_kabul.")}
    assert ic <= {"malzeme_kabul.sozlesme.sema", "malzeme_kabul.kural.birimler"}, ic


def test_yalniz_dil_modeli_cikarimi_urunde_yok():
    for ad in ("belgeden_cikar", "cikarim_semasi", "yaniti_coz", "CikarimYaniti"):
        assert not hasattr(yerel_model, ad), f"{ad} deney/yalniz_dil_modeli.py içinde olmalı"


# --- Parti durumunu yalnız karar hattı yazar -------------------------------------------------------

PARTI_DURUMU_YAZABILEN = {"hat/katalog_karari.py"}


def test_parti_durumu_ata_src_icinde_yalniz_hat_katalog_kararindan_cagrilir():
    """Parti durumu (serbest / karantina) yalnız `hat.katalog_karari` üzerinden değişir.

    Böylece rol ve gerekçe denetimi (`karari_duzelt`) ve makine kuralı atlanamaz.
    Doğrudan çağrı, getattr ile ad üzerinden erişim de sayılır.
    """
    ihlaller = []
    for dosya in katman_dosyalari():
        goreli = dosya.relative_to(PAKET).as_posix()
        for d in ast.walk(ast.parse(dosya.read_text(encoding="utf-8"))):
            cagri = isinstance(d, ast.Attribute) and d.attr == "parti_durumu_ata" and isinstance(d.ctx, ast.Load)
            ad = isinstance(d, ast.Constant) and d.value == "parti_durumu_ata"
            if (cagri or ad) and goreli not in PARTI_DURUMU_YAZABILEN:
                ihlaller.append(f"{goreli}:{d.lineno}")
    assert not ihlaller, "parti_durumu_ata hat/katalog_karari.py dışında kullanılıyor:\n" + "\n".join(ihlaller)


def test_parti_durumu_ata_denetimi_bos_gecmez():
    """Düzenek denetimi: izinli dosyada gerçekten çağrı bulunur (arama adı yanlışsa yukarıdaki test boşa geçerdi)."""
    agac = ast.parse((PAKET / "hat/katalog_karari.py").read_text(encoding="utf-8"))
    assert any(isinstance(d, ast.Attribute) and d.attr == "parti_durumu_ata" for d in ast.walk(agac))
