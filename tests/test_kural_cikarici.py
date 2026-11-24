"""Kural tabanlı çıkarıcının testleri.

Birim testleri küçük metin parçalarıyla, entegrasyon testleri depodaki
MIL-PRF-23377K PDF'iyle çalışır.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pdf_uretici import pdf_yaz

from malzeme_kabul.cikarim.kural_cikarici import (
    cikar,
    kabul_disi_testler,
    metni_normallestir,
    paragraflara_bol,
    sinir_cikar,
    sure_cikar,
    uygulanabilirlik_cikar,
)
from malzeme_kabul.belge.pdf_okuyucu import pdf_oku

KOK = Path(__file__).resolve().parents[1]
K_PDF = KOK / "data" / "raw" / "MIL-PRF-23377K.pdf"


# --- Metin temizliği ve paragraflar ---------------------------------------------


def test_pdf_glif_kodlari_normallesir():
    assert metni_normallestir("49 (cid:114)3(cid:113) C") == "49 ±3° C"
    assert metni_normallestir("15 to 23 (cid:80)m") == "15 to 23 µm"
    assert metni_normallestir("46º C") == "46° C"
    assert metni_normallestir("Type I(cid:3)x") == "Type I x"


def test_paragraflar_numara_baslik_ve_sayfayla_ayrilir(tmp_path):
    yol = pdf_yaz(tmp_path / "p.pdf", [
        {"metin": ["Downloaded from https://www.everyspec.com", "MIL-PRF-23377K",
                   "3.6.3 Viscosity. The maximum viscosity shall be", "40 seconds through a cup.", "7"]},
        {"metin": ["MIL-PRF-23377K", "3.6.4 Pot life. After 4 hours the viscosity", "shall be 70 seconds."]},
    ])
    paragraflar = paragraflara_bol(pdf_oku(yol), belge_no="MIL-PRF-23377K")
    p = paragraflar["3.6.3"]
    assert p.baslik == "Viscosity"
    assert p.metin == "The maximum viscosity shall be 40 seconds through a cup."
    assert p.sayfa == 1
    assert paragraflar["3.6.4"].sayfa == 2
    assert "everyspec" not in p.metin


# --- Sınır kuralları ------------------------------------------------------------


@pytest.mark.parametrize(
    "metin, alt, ust, birim",
    [
        ("The VOC content shall be not greater than 340 g/L (2.8 lb/gal).", None, 340, "g/L"),
        ("shall exhibit an elongation of not less than 10 percent when tested", 10, None, "%"),
        ("the maximum viscosity of the unthinned primer shall be 40 seconds through a #4 Ford cup", None, 40, "s"),
        ("The fineness of grind shall be 5 or greater on the Hegman scale", 5, None, None),
        ("shall be tack free within 5 hours and shall dry hard within 8 hours", None, 5, "hour"),
        ("shall be not greater than 5 ppm (see 4.5).", None, 5, "ppm"),
        ("a dry-film thickness of 15 to 23 microns (µm) (0.6 to 0.9 mil)", 15, 23, "µm"),
        ("a minimum of 90 percent of the coating shall be stripped", 90, None, "%"),
        ("shall be not greater than ten percent throughout the range", None, 10, "%"),
    ],
)
def test_sayisal_sinir_kurallari(metin, alt, ust, birim):
    s = sinir_cikar(metin)
    assert s.kriter_turu == "sayisal"
    assert (s.alt, s.ust, s.birim) == (alt, ust, birim)
    assert s.orijinal_metin


def test_sayi_yoksa_metinsel_kriter_doner():
    s = sinir_cikar("There shall be no evidence of lifting or any other film irregularity.")
    assert s.kriter_turu == "metinsel"
    assert s.orijinal_metin.startswith("There shall be no evidence of lifting")


def test_baglam_sayilari_sinir_sanilmaz():
    # "for 4 hours" koşuldur, sınır 70 saniyedir.
    s = sinir_cikar("After mixing and storage for 4 hours, the maximum viscosity (see 3.6.3) shall be 70 seconds.")
    assert (s.ust, s.birim) == (70, "s")


# --- Süre, uygulanabilirlik, kabul dışı testler ----------------------------------


@pytest.mark.parametrize(
    "metin, beklenen",
    [("after storage for a period of one year for metal", (1, "year")),
     ("six months for plastic containers", (6, "month")),
     ("for 14 days", (14, "day"))],
)
def test_sure_cikar(metin, beklenen):
    assert sure_cikar(metin) == beklenen


@pytest.mark.parametrize(
    "ad, beklenen",
    [("Chromium content (class N only)", ["Class N"]),
     ("Infrared reflectance (type II only)", ["Type II"]),
     ("Color – Type I", ["Type I"]),
     ("Viscosity", [])],
)
def test_uygulanabilirlik_test_adindan_cikar(ad, beklenen):
    assert uygulanabilirlik_cikar(ad) == beklenen


def test_kabul_muayenesinden_haric_tutulan_testler_bulunur():
    metin = (
        "Conformance inspection consists of all the tests specified in 4.5, with the exception of "
        "storage stability (see table II), accelerated storage stability (see 4.5.2), corrosion "
        "resistance (see 4.5.8), toxicity (see 4.5.12), and strippability (see 4.5.13). There shall be no failures."
    )
    assert kabul_disi_testler(metin) == [
        "storage stability", "accelerated storage stability", "corrosion resistance", "toxicity", "strippability",
    ]


# --- MIL-PRF-23377K entegrasyon testleri ---------------------------------------

k_yok = pytest.mark.skipif(not K_PDF.exists(), reason="MIL-PRF-23377K.pdf data/raw altında yok")


@pytest.fixture(scope="module")
def k_dokumani():
    return cikar(K_PDF, belge_no="MIL-PRF-23377", revizyon="K")


@k_yok
def test_k_tablo_ii_deki_butun_testler_cikarilir(k_dokumani):
    assert len(k_dokumani.testler) == 27
    assert k_dokumani.standart.baslik == "PRIMER COATINGS: EPOXY, HIGH-SOLIDS"


@k_yok
def test_k_her_sart_madde_numarasi_ve_kaynak_belgeyle_gelir(k_dokumani):
    for t in k_dokumani.testler:
        assert (t.kaynak.belge_no, t.kaynak.revizyon) == ("MIL-PRF-23377", "K")
        assert t.kaynak.madde and t.kaynak.sayfa


@k_yok
def test_k_voc_siniri(k_dokumani):
    voc = next(t for t in k_dokumani.testler if t.kaynak.madde == "3.4.2")
    assert (voc.sinir.ust, voc.sinir.birim, voc.test_metodu) == (340, "g/L", "ASTM D3960")
    assert voc.kabul_testi


@k_yok
def test_k_kabul_disi_testler_yalniz_yeterlilikte(k_dokumani):
    turler = {t.kaynak.madde: t.test_turleri for t in k_dokumani.testler}
    for madde in ("3.5.3", "3.5.4", "3.8.2.1", "3.8.2.2", "3.3", "3.12"):
        assert turler[madde] == {"yeterlilik"}, madde
    assert turler["3.6.3"] == {"kabul", "yeterlilik"}


@k_yok
def test_k_raf_omru_ve_depolama_kosulu(k_dokumani):
    (r,) = k_dokumani.raf_omurleri
    assert (r.sure, r.birim, r.kaynak.madde) == (1, "year", "3.5.3")
    assert (r.kosul.alt, r.kosul.ust, r.kosul.birim) == (1.7, 46, "°C")


@k_yok
def test_k_test_panelleri_numune_hazirligina_doner(k_dokumani):
    paneller = {n.id: n for n in k_dokumani.numune_hazirlama}
    assert set(paneller) == {"panel_A", "panel_B", "panel_C", "panel_D"}
    assert "250/4" in paneller["panel_A"].kupon_malzemesi
    assert paneller["panel_A"].kuru_film_kalinligi.alt == 15
    assert paneller["panel_A"].uygulama_yontemi.endswith("ASTM D823 Method D.")
    yapisma = next(t for t in k_dokumani.testler if t.kaynak.madde == "3.7.4")
    assert yapisma.numune_hazirlama_id == "panel_C"


# --- scripts/kabul_dokumani_uret.py ---------------------------------------------


def test_dosya_adindan_belge_no_ve_revizyon():
    from conftest import betik_yukle

    betik = betik_yukle("scripts/kabul_dokumani_uret.py")
    assert betik.belge_no_ve_revizyon("MIL-PRF-23377K.pdf") == ("MIL-PRF-23377", "K")
    assert betik.belge_no_ve_revizyon("MIL-PRF-81733D.pdf") == ("MIL-PRF-81733", "D")
    with pytest.raises(ValueError):
        betik.belge_no_ve_revizyon("rapor.pdf")


@k_yok
def test_betik_json_markdown_ve_word_uretir(tmp_path):
    from conftest import betik_yukle

    from malzeme_kabul.sozlesme.sema import KabulDokumani

    betik = betik_yukle("scripts/kabul_dokumani_uret.py")
    assert betik.main([str(K_PDF), "--cikti", str(tmp_path)]) == 0
    json_yolu = tmp_path / "MIL-PRF-23377K_kabul_dokumani.json"
    d = KabulDokumani.model_validate_json(json_yolu.read_text(encoding="utf-8"))
    assert len(d.testler) == 27
    assert (tmp_path / "MIL-PRF-23377K_kabul_dokumani.md").read_text(encoding="utf-8").startswith("# Kabul")
    assert (tmp_path / "MIL-PRF-23377K_kabul_dokumani.docx").stat().st_size > 0
