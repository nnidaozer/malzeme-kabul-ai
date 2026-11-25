"""Gerçek CoA'ları ürün şartnamesiyle eşleştiren betiğin testleri (deney/coa_eslestirme.py)."""

from __future__ import annotations

import csv

import pytest

from conftest import KOK
from deney.coa_eslestirme import (
    SARTNAME_SINIRSIZ,
    SINIR_AYNI,
    SINIR_FARKLI,
    SINIRSIZ,
    YOK,
    Kalem,
    TestSatiri,
    coa_satirlari,
    eslestir,
    eslestirme_yap,
    kelimelerden_satirlar,
    main,
    oransal_sinir,
    sartname_kalemleri,
    sikilik,
    sinir_karsilastir,
)

COA = KOK / "data" / "raw" / "gercek_coa"


def k(x: float, y: float, metin: str, h: float = 10.0, gen: float = 5.0) -> list[dict]:
    """pdfplumber kelimeleri gibi sözlükler (x0, x1, top, bottom, text); kelimeler arasında 3 pt boşluk."""
    kelimeler = []
    for kelime in metin.split(" "):
        kelimeler.append({"x0": x, "x1": x + gen * len(kelime), "top": y, "bottom": y + h, "text": kelime})
        x += gen * len(kelime) + 3
    return kelimeler


def satirlar(*gruplar):
    return kelimelerden_satirlar([kelime for g in gruplar for kelime in g])


# --- Satır ve hücreler ----------------------------------------------------------------


def test_alt_simge_kelimeye_yapisir_genis_bosluk_hucre_ayirir():
    s = satirlar(
        k(100, 100, "Na", gen=7.5), k(115, 104.7, "2", h=6, gen=4.4), k(119.4, 100, "O", gen=9.4),
        k(300, 100, "50.52 %"),
    )
    assert len(s) == 1
    assert [h.metin for h in s[0].hucreler] == ["Na2O", "50.52 %"]


def test_dikeyde_hafif_kayan_kelime_ayni_satirdadir():
    s = satirlar(k(100, 380.2, "Bulk density"), k(300, 380.2, "69"), k(315, 377.9, "lb/ft3", h=14.3))
    assert [h.metin for h in s[0].hucreler] == ["Bulk density", "69 lb/ft3"]


# --- CoA düzenleri ----------------------------------------------------------------------


def _alfa_tablosu():
    return satirlar(
        k(150, 300, "Test"), k(312, 300, "Limits"), k(392, 300, "Results"),
        k(150, 314, "Assay (GC)"), k(312, 314, "99.7 % min"), k(401, 314, "99.88 %"),
        k(150, 328, "Boiling range"), k(312, 328, "To pass test"), k(401, 328, "Passes"),
        k(150, 342, "inc. 110.6ºC"),
        # tablonun altında girintili, sınırsız satırlar (Alfa Aesar 033361 F09W020)
        k(200, 356, "Ethanol"), k(312, 356, "90.43 %"),
        k(100, 380, "Certified by:"),
    )


def test_limit_tablosu_okunur_ad_devami_ve_girintili_satirlar():
    testler = coa_satirlari(_alfa_tablosu())
    assert [(t.ad, t.sinir, t.deger) for t in testler] == [
        ("Assay (GC)", "99.7 % min", "99.88 %"),
        ("Boiling range inc. 110.6ºC", "To pass test", "Passes"),
        ("Ethanol", "", "90.43 %"),
    ]
    assert {t.duzen for t in testler} == {"tablo"}


def test_spectrum_min_max_ve_cok_satirli_hucreler():
    s = satirlar(
        k(145, 200, "Test"), k(341, 200, "Specification"), k(498, 200, "Result"),
        k(313, 214, "min"), k(407, 214, "max"),
        k(38, 228, "ASSAY"), k(276, 228, "99.0%"), k(495, 228, "100.0 %"),
        k(38, 242, "WATER"), k(371, 242, "0.5 %"), k(500, 242, "0.03 %"),
        # APPEARANCE: sınır ve sonuç üç satıra yayılmış, test satırına göre dikeyde ortalanmış
        k(495, 257, "CLEAR"),
        k(276, 262, "CLEAR AND"),
        k(38, 267, "APPEARANCE"), k(483, 267, "COLORLESS"),
        k(276, 272, "COLORLESS"),
        k(494, 277, "LIQUID"),
        k(38, 296, "ABSORBANCE:"), k(276, 296, "."), k(510, 296, "."),
        k(38, 310, "230 nm"), k(371, 310, "0.30"), k(503, 310, "0.06"),
        k(38, 324, "RETEST DATE"), k(480, 324, "23-AUG-2023"),
    )
    testler = {t.ad: t for t in coa_satirlari(s)}
    assert testler["ASSAY"].sinir == "min 99.0%" and testler["ASSAY"].deger == "100.0 %"
    assert testler["WATER"].sinir == "max 0.5 %"
    assert testler["APPEARANCE"].sinir == "CLEAR AND COLORLESS"
    assert testler["APPEARANCE"].deger == "CLEAR COLORLESS LIQUID"
    assert testler["ABSORBANCE: 230 nm"].sinir == "max 0.30"  # "." satırı bölüm başlığıdır
    assert "RETEST DATE" not in testler  # belge bilgisi, test değil


def test_sinirsiz_liste_bolum_basligi_ve_element_izgarasi():
    s = satirlar(
        k(110, 100, "Lot No.:"), k(200, 100, "W21I035"),
        k(150, 130, "UV absorbance vs H2O"),
        k(200, 144, "195 nm"), k(352, 144, "0.35 AU"),
        k(150, 158, "Water"), k(352, 158, "0.01 %"),
        k(150, 186, "Al"), k(175, 186, "< 5"), k(215, 186, "Ba"), k(240, 186, "<1"),
        k(270, 186, "Na"), k(348, 186, "Sb"), k(377, 186, "< 1"),
        k(270, 200, "Metal"),
        k(180, 214, "Values given in ppb"),
        k(150, 240, "Retest date: 2027"),
    )
    testler = coa_satirlari(s)
    assert [(t.ad, t.deger) for t in testler[:2]] == [("UV absorbance vs H2O: 195 nm", "0.35 AU"), ("Water", "0.01 %")]
    izgara = {t.ad: (t.deger, t.birim) for t in testler if t.izgara}
    assert izgara == {"Al": ("< 5", "ppb"), "Ba": ("<1", "ppb"), "Na": ("matris (Metal)", "ppb"), "Sb": ("< 1", "ppb")}
    assert {t.duzen for t in testler} == {"sınırsız"} and all(t.sinir == "" for t in testler)


# --- Şartname -------------------------------------------------------------------------


def test_urun_sartnamesi_tasan_ve_bolunen_adlar():
    s = satirlar(
        k(400, 50, "Product Specification"),
        k(40, 80, "Product Name:"), k(180, 80, "Toluene"),
        k(40, 120, "Product Specification"),
        k(40, 140, "Form:"), k(180, 140, "Liquid"),
        k(40, 156, "Water Content (Karl Fischer"), k(178, 156, "≤0.03%"),  # ad değer sütununa dayanıyor
        k(40, 172, "Titration):"),
        k(40, 188, "Assay from Supplier's CofA: ≥99.0%"),  # ad değer sütununa taşıyor
        k(40, 204, "Elemental Analysis:"), k(180, 204, "≤10 ppb for"),
        k(180, 220, "Al,Ba,Cd"),
        k(40, 236, "Comment:"), k(180, 236, "not"),
        k(40, 260, "Date Of Print:"), k(180, 260, "11/23/2026"),
    )
    kalemler = [(x.ad, x.sinir) for x in sartname_kalemleri(s)]
    assert kalemler == [
        ("Form", "Liquid"),
        ("Water Content (Karl Fischer Titration)", "≤0.03%"),
        ("Assay from Supplier's CofA", "≥99.0%"),
        ("Elemental Analysis", "≤10 ppb for Al,Ba,Cd"),
    ]


def test_gercek_spectrum_sartnamesi_min_max_ve_bolumler():
    from deney.coa_eslestirme import pdf_satirlari

    kalemler = {x.ad: x.sinir for x in sartname_kalemleri(pdf_satirlari(COA / "spectrum_IS115_spec.pdf"))}
    assert kalemler["ASSAY (USP)"] == "min 99.0%"
    assert kalemler["SPECIFIC GRAVITY (USP)"] == "0.783 - 0.787"
    assert kalemler["LIMIT OF VOLATILE IMPURITIES (USP): METHANOL"] == "max 0.02 %"
    assert kalemler["ULTRAVIOLET ABSORPTION (USP): 310 nm"] == "max 0.01"
    assert kalemler["CURVE"].endswith("OBSERVABLE PEAKS OR SHOULDERS")  # beş satırlık hücre tek kalemde
    assert "EXPIRATION DATE" not in kalemler


# --- Sınır karşılaştırması --------------------------------------------------------------


@pytest.mark.parametrize(
    "sertifika, sartname, beklenen",
    [
        ("10 max", "≤10", "aynı"),
        ("99.0% min", "≥99.0% (non-U.S. specification)", "aynı"),
        ("0.003 % max", "Sulfuric compounds (as S); ≤0.003%", "aynı"),
        ("To pass test", "Substances darkened by sulfuric acid P.T.", "aynı"),
        ("94.0 – 96.0 %", "Within 94.0-96.0% (V/V) methanol and ethyl alcohol", "aynı"),
        ("10 ppm max", "≤0.001%", "aynı (birim çevrilerek)"),
        ("0.50%", "max 0.5 %", "aynı (yön yazılmamış)"),
        ("1.500-1.640 at 20^oC", "1.500-1.640 at 20°C", "aynı"),
        ("99.7 % min", "≥99.5%", "farklı"),
        ("Clear liquid", "Clear colorless", "farklı"),
    ],
)
def test_sinir_karsilastirma(sertifika, sartname, beklenen):
    assert sinir_karsilastir(sertifika, sartname) == beklenen


def test_oransal_sinir_kesin_oranla_cevrilir_ve_siklik():
    assert oransal_sinir("10 ppm max") == ("≤", (1e-05,))
    assert oransal_sinir("0.001 %") == ("", (1e-05,))
    assert oransal_sinir("44.7-47.6%") == ("aralık", (0.447, 0.476))
    assert oransal_sinir("Clear") is None
    assert sikilik("99.7 % min", "≥99.5%") == "sertifika daha sıkı"
    assert sikilik("0.2 % max", "≤0.5%") == "sertifika daha sıkı"
    assert sikilik("1 % max", "≤0.5%") == "sertifika daha gevşek"
    assert sikilik("Clear", "Clear") == ""


# --- Eşleştirme -------------------------------------------------------------------------


def _durum(testler, kalemler, katalog="X"):
    return {(s["test"], s["durum"], s["eslesme"], s["sartname_kalemi"]) for s in eslestir(testler, kalemler, katalog)}


def test_ad_kok_elle_bilesen_ve_karsiligi_olmayan():
    kalemler = [
        Kalem("Assay (GC)", "≥99.0%"), Kalem("Residue on Evaporation", "≤10 ppm"),
        Kalem("Impurity content", "Cl: ≤2.0 ppm"), Kalem("Impurity content", "PO₄: ≤0.5 ppm"),
        Kalem("Appearance (Color)", ""),
    ]
    testler = [
        TestSatiri("Assay (GC, corrected for water)", deger="99.9 %"),
        TestSatiri("Evaporation residue", sinir="10 ppm max", deger="< 10 ppm"),
        TestSatiri("Chloride", deger="< 2 ppm"),
        TestSatiri("Appearance", sinir="Clear", deger="Clear"),
        TestSatiri("Heavy metals (as Pb)", deger="< 50 ppb"),
    ]
    assert _durum(testler, kalemler) == {
        ("Assay (GC, corrected for water)", SINIRSIZ, "ad", "Assay (GC)"),
        ("Evaporation residue", SINIR_AYNI, "elle", "Residue on Evaporation"),
        ("Chloride", SINIRSIZ, "elle", "Impurity content"),  # iki "Impurity content" kaleminden Cl olanı
        ("Appearance", SARTNAME_SINIRSIZ, "ad", "Appearance (Color)"),  # parantezli niteleyici atılınca aynı
        ("Heavy metals (as Pb)", YOK, "", ""),
    }


def test_element_izgarasi_listeye_ve_toplam_kalemine_baglanir():
    kalemler = [Kalem("Elemental Analysis", "≤10 ppb for all of the following: Al,Ba,Cd"),
                Kalem("Trace Metal", "Potassium, K: ≤0.1ppm")]
    testler = [TestSatiri("Ba", deger="< 1", izgara=True), TestSatiri("K", deger="< 10", izgara=True),
               TestSatiri("Zn", deger="< 1", izgara=True)]
    assert _durum(testler, kalemler) == {
        ("Ba", SINIRSIZ, "element", "Elemental Analysis"),
        ("K", SINIRSIZ, "element", "Trace Metal"),
        ("Zn", YOK, "", ""),
    }
    toplam = eslestir([TestSatiri("Fe", deger="3", izgara=True)], [Kalem("Total Metal Impurities", "≤0.001%")], "044227")
    assert toplam[0]["eslesme"] == "toplam" and "toplamı" in toplam[0]["not"]


def test_farkli_sinirda_siklik_ve_sicaklik_notu():
    kalemler = [Kalem("Assay (GC)", "≥99.5%"), Kalem("Refractive Index", "1.3580-1.3610 @ 20°C")]
    sonuc = {s["test"]: s for s in eslestir([
        TestSatiri("Assay (GC)", sinir="99.7 % min"),
        TestSatiri("Refractive index at 25°C", sinir="1.3589-1.3599"),
    ], kalemler, "X")}
    assert sonuc["Assay (GC)"]["durum"] == SINIR_FARKLI and sonuc["Assay (GC)"]["not"] == "sertifika daha sıkı"
    assert "ölçüm sıcaklığı farklı (25 °C ↔ 20 °C)" in sonuc["Refractive index at 25°C"]["not"]


# --- Gerçek sertifikalar ----------------------------------------------------------------


@pytest.fixture(scope="module")
def hepsi():
    return eslestirme_yap()


def test_thermo_fisher_eslesmesi_onceki_sonucu_tekrarlar(hepsi):
    """PR #43'teki Thermo Fisher eşleştirmesi: 50 sertifika, 259 satır, 223 aynı / 6 farklı / 30 sınırsız."""
    satirlar, ozet = hepsi
    thermo = [s for s in satirlar if s["tedarikci"] == "Thermo Fisher Scientific"]
    assert sum(o["tedarikci"] == "Thermo Fisher Scientific" for o in ozet) == 50
    durumlar = [s["durum"] for s in thermo]
    assert (len(thermo), durumlar.count(SINIR_AYNI), durumlar.count(SINIR_FARKLI), durumlar.count(SINIRSIZ)) == (
        259, 223, 6, 30,
    )


def test_alfa_aesar_ve_spectrum_eslesir(hepsi):
    satirlar, ozet = hepsi
    tedarikciler = {o["tedarikci"] for o in ozet}
    assert tedarikciler == {"Thermo Fisher Scientific", "Alfa Aesar", "Spectrum Chemical"}
    alfa = [o for o in ozet if o["tedarikci"] == "Alfa Aesar"]
    spectrum = [o for o in ozet if o["tedarikci"] == "Spectrum Chemical"]
    assert len(alfa) == 31 and len(spectrum) == 2  # şartnamesi olan bütün sertifikalar
    assert all(o["test"] > 0 for o in alfa + spectrum)  # her düzen okundu
    # bilinen satırlar: CoA'nın 310 nm sınırı şartnameden farklı; Acetone örneği gibi sıkı su sınırı
    spec = {(s["sertifika"], s["test"]): s for s in satirlar}
    assert spec[("spectrum_IS115_1HI0678_coa.pdf", "ABSORBANCE: 310 nm")]["durum"] == SINIR_FARKLI
    su = spec[("alfa_033361_Y04G031_coa.pdf", "Water")]
    assert su["durum"] == SINIR_FARKLI and su["not"] == "sertifika daha sıkı"


def test_depodaki_eslesme_dosyalari_guncel(hepsi, tmp_path):
    """data/coa_eslesme/ betiğin çıktısıyla aynı olmalı (betik değişince yeniden üretilir)."""
    assert main(["--cikti", str(tmp_path)]) == 0
    for ad in ("test_satirlari.csv", "sertifika_ozeti.csv"):
        depodaki = (KOK / "data" / "coa_eslesme" / ad).read_text(encoding="utf-8")
        assert (tmp_path / ad).read_text(encoding="utf-8") == depodaki, f"{ad} eski: python deney/coa_eslestirme.py"
    with (tmp_path / "test_satirlari.csv").open(encoding="utf-8") as f:
        assert {s["durum"] for s in csv.DictReader(f)} <= {SINIR_AYNI, SINIR_FARKLI, SINIRSIZ, SARTNAME_SINIRSIZ, YOK}
