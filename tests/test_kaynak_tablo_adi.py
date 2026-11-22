"""Test adı ile kaynak tablo adı ayrımı (3.4: ≤ 1 ppm yalnızca kadmiyum için)."""

from __future__ import annotations

from pathlib import Path

import pytest

from malzeme_kabul.karar_motoru import eslestir
from malzeme_kabul.kural_cikarici import cikar, test_adi_ayir as adi_ayir
from malzeme_kabul.sema import TestSarti as Sart

KOK = Path(__file__).resolve().parents[1]
K_PDF = KOK / "data" / "raw" / "MIL-PRF-23377K.pdf"
TABLO = "Lead and cadmium content"


def _sart(id_: str, ad: str, tablo: str | None = None) -> Sart:
    return Sart.model_validate({
        "id": id_,
        "test_adi": ad,
        "kaynak_tablo_adi": tablo,
        "sinir": {"kriter_turu": "sayisal", "ust": 1, "birim": "ppm", "orijinal_metin": "metin"},
        "kaynak": {"belge_no": "MIL-PRF-23377", "revizyon": "K", "madde": "3.4"},
        "test_turleri": ["kabul"],
    })


# --- test_adi_ayir -------------------------------------------------------------

def test_yalniz_kadmiyumu_anan_cumle_kadmiyum_adini_verir():
    cumle = "Incidental cadmium and cadmium compounds shall be not greater than one part per million (ppm)."
    assert adi_ayir(TABLO, cumle) == "Cadmium content"


def test_yalniz_kursunu_anan_cumle_kursun_adini_verir():
    cumle = "The non-volatile portion shall contain not more than 0.05 percent by weight of lead metal."
    assert adi_ayir(TABLO, cumle) == "Lead content"


def test_iki_bileseni_de_anan_cumle_tablo_adini_korur():
    cumle = "No component shall contain cadmium, or more than 0.05 percent by weight of lead."
    assert adi_ayir(TABLO, cumle) == TABLO


@pytest.mark.parametrize("ad", ["Viscosity", "Mixing and dilution", "Chromium content (class N only)"])
def test_birlesik_olmayan_ad_degismez(ad):
    assert adi_ayir(ad, "cadmium shall be not greater than 1 ppm") == ad


# --- şema ---------------------------------------------------------------------

def test_sema_tablo_adini_ayrica_tutar():
    t = _sart("lead_and_cadmium_content", "Cadmium content", TABLO)
    assert (t.test_adi, t.kaynak_tablo_adi) == ("Cadmium content", TABLO)


def test_sema_test_adiyla_ayni_tablo_adini_tutmaz():
    assert _sart("viscosity", "Viscosity", "viscosity").kaynak_tablo_adi is None


# --- karar motoru eşleştirmesi ---------------------------------------------------

def test_sertifikadaki_tablo_adi_tek_teste_eslesir():
    testler = [_sart("lead_and_cadmium_content", "Cadmium content", TABLO), _sart("viscosity", "Viscosity")]
    assert eslestir("Lead and cadmium content", testler) == "lead_and_cadmium_content"
    assert eslestir("Cadmium content", testler) == "lead_and_cadmium_content"


def test_ayni_tablo_satirindan_iki_test_varsa_tablo_adi_belirsizdir():
    testler = [
        _sart("lead_and_cadmium_content", "Cadmium content", TABLO),
        _sart("lead_and_cadmium_content_lead", "Lead content", TABLO),
    ]
    assert eslestir("Lead and cadmium content", testler) is None  # insan incelemeli
    assert eslestir("Cadmium content", testler) == "lead_and_cadmium_content"
    assert eslestir("Lead content", testler) == "lead_and_cadmium_content_lead"


# --- çıkarıcı (23377K) --------------------------------------------------------------

@pytest.mark.skipif(not K_PDF.exists(), reason="MIL-PRF-23377K.pdf data/raw altında yok")
def test_cikarici_kadmiyum_satirini_tablo_adindan_ayirir():
    dok = cikar(K_PDF, belge_no="MIL-PRF-23377", revizyon="K")
    t = next(t for t in dok.testler if t.kaynak.madde == "3.4")
    assert t.test_adi == "Cadmium content"
    assert t.kaynak_tablo_adi == TABLO
    assert (t.sinir.ust, t.sinir.birim) == (1, "ppm")
    viskozite = next(t for t in dok.testler if t.id == "viscosity")
    assert viskozite.kaynak_tablo_adi is None
