"""Revizyon karşılaştırıcının testleri.

Birim testleri elle kurulan şart ve tablo satırlarıyla, entegrasyon testleri
depodaki MIL-PRF-23377 H, J ve K PDF'leriyle çalışır.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import betik_yukle

from malzeme_kabul.revizyon_karsilastirici import (
    RevizyonFarki,
    Sart,
    TestSatiri,
    guncelleme_onerileri,
    karsilastir,
    markdown_raporu,
    revizyonlari_karsilastir,
    sart_farki,
    sartlari_eslestir,
    sayisal_degerler,
    tablo_satirlari,
    tablo_farklari,
)
from malzeme_kabul.sema import KabulDokumani, Kaynak, Sinir, StandartBilgisi, TestSarti

KOK = Path(__file__).resolve().parents[1]
RAW = KOK / "data" / "raw"


def sart(madde: str, baslik: str, metin: str = "", sayfa: int = 1) -> Sart:
    return Sart(madde=madde, baslik=baslik, metin=metin, sayfa=sayfa)


def sozluk(*sartlar: Sart) -> dict[str, Sart]:
    return {s.madde: s for s in sartlar}


# --- Sayısal değerler -------------------------------------------------------------


def test_sayisal_degerler_sayi_ve_birimi_birlikte_alir():
    metin = "after storage for not less than one year for metal containers and six months for plastic containers"
    assert sayisal_degerler(metin) == ["1 year", "6 month"]


def test_sayisal_degerler_sicaklik_birimlerini_birlestirir():
    metin = "maintained at 1.7 to 46° C (35 to 115° F)"
    assert sayisal_degerler(metin) == ["1.7 °C", "46 °C", "35 °F", "115 °F"]


def test_sayisal_degerler_aralik_ve_tolerans_birimi_paylasir():
    assert sayisal_degerler("dry for 0.5 to 1.0 mils at 65.5 ±3° C") == ["0.5 mil", "1.0 mil", "65.5 °C", "3 °C"]


def test_sayisal_degerler_madde_atiflarini_ve_belge_numaralarini_saymaz():
    metin = "shall conform to ASTM D3335 and MIL-PRF-23377 (see 4.5.2 and 6.3.1) as in table II"
    assert sayisal_degerler(metin) == []


# --- Eşleştirme ---------------------------------------------------------------------


def test_ayni_numara_ve_baslik_eslesir():
    eski = sozluk(sart("3.6.3", "Viscosity", "a"))
    yeni = sozluk(sart("3.6.3", "Viscosity", "b"))
    assert sartlari_eslestir(eski, yeni) == [(eski["3.6.3"], yeni["3.6.3"])]


def test_numarasi_degisen_sart_basligiyla_eslesir():
    eski = sozluk(sart("6.7", "Part or Identifying Number (PIN)", "x"), sart("6.8", "Impact tester source", "y"))
    yeni = sozluk(sart("1.3", "Part or Identifying Number (PIN)", "x"), sart("6.7", "Impact tester source", "y"))
    ciftler = {(e.madde, y.madde) for e, y in sartlari_eslestir(eski, yeni)}
    assert ciftler == {("6.7", "1.3"), ("6.8", "6.7")}


def test_eslesmeyenler_eklendi_ve_kaldirildi_olarak_kalir():
    eski = sozluk(sart("3.1", "Qualification", "q"), sart("3.4.1.1", "Class C", "c"))
    yeni = sozluk(sart("3.1", "Qualification", "q"), sart("3.12", "Strippability", "s"))
    ciftler = sartlari_eslestir(eski, yeni)
    assert (eski["3.4.1.1"], None) in ciftler
    assert (None, yeni["3.12"]) in ciftler
    assert (eski["3.1"], yeni["3.1"]) in ciftler


def test_kaydirilan_sinif_maddesi_ayni_basligla_eslesir():
    # H: 3.4.1.1 Class C, 3.4.1.2 Class N. J: 3.4.1.1 Class C1, 3.4.1.2 Class C2, 3.4.1.3 Class N.
    eski = sozluk(sart("3.4.1.1", "Class C", "c"), sart("3.4.1.2", "Class N", "n"))
    yeni = sozluk(sart("3.4.1.1", "Class C1", "c"), sart("3.4.1.2", "Class C2", "c2"), sart("3.4.1.3", "Class N", "n"))
    ciftler = {(e.madde if e else None, y.madde if y else None) for e, y in sartlari_eslestir(eski, yeni)}
    assert ciftler == {("3.4.1.1", "3.4.1.1"), ("3.4.1.2", "3.4.1.3"), (None, "3.4.1.2")}


def test_ayni_numarada_benzer_baslik_ama_farkli_metin_eslesmez():
    eski = sozluk(sart("3.4.1.2", "Class C2", "Coatings containing strontium chromate shall be class C2."))
    yeni = sozluk(sart("3.4.1.2", "Class C3", "Water-borne epoxy primers with zinc phosphate pigments only."))
    ciftler = sartlari_eslestir(eski, yeni)
    assert (eski["3.4.1.2"], None) in ciftler and (None, yeni["3.4.1.2"]) in ciftler


def test_sayisal_degerler_bolum_numarasina_benzemeyen_ondaliklari_tutar():
    assert sayisal_degerler("gloss of 85.0 and thickness between 0.5 and 1.0") == ["85.0", "0.5", "1.0"]


def test_ayni_numarada_baslik_hafif_degisirse_eslesir():
    eski = sozluk(sart("3.4.2", "Volatile organic compound (VOC) solvent content", "v"))
    yeni = sozluk(sart("3.4.2", "Volatile organic compound (VOC) content", "v"))
    assert sartlari_eslestir(eski, yeni) == [(eski["3.4.2"], yeni["3.4.2"])]


# --- Şart farkı ----------------------------------------------------------------------


def test_ayni_metin_fark_vermez():
    a = sart("3.6.3", "Viscosity", "The viscosity shall be 20 to 40 seconds.")
    assert sart_farki(a, sart("3.6.3", "Viscosity", "The  viscosity shall be 20 to 40 seconds.")) is None


def test_sayisal_degisiklik_degerleriyle_raporlanir():
    eski = sart("3.5.3", "Storage stability", "after storage for not less than one year (see 4.5).")
    yeni = sart("3.5.3", "Storage stability",
                "after storage for not less than one year for metal containers and six months for plastic containers (see 4.5).")
    fark = sart_farki(eski, yeni)
    assert fark.tur == "degisti"
    assert fark.onem == "sayisal"
    assert fark.eski_degerler == []
    assert fark.yeni_degerler == ["6 month"]
    assert any("six months for plastic" in d.yeni for d in fark.degisiklikler)


def test_sayi_degismeyen_degisiklik_metin_onemi_alir():
    eski = sart("4.2", "Qualification inspection", "The sample shall be retained by the laboratory. The samples shall be identified.")
    yeni = sart("4.2", "Qualification inspection", "The samples shall be identified.")
    fark = sart_farki(eski, yeni)
    assert fark.onem == "metin"
    assert fark.degisiklikler[0].eski.startswith("The sample shall be retained")
    assert fark.degisiklikler[0].yeni == ""


def test_yalniz_yazim_farki_bicimsel_sayilir():
    eski = sart("3.4", "Composition", "tested per ASTM-D3335 – lead")
    yeni = sart("3.4", "Composition", "tested per ASTM D3335 - lead")
    assert sart_farki(eski, yeni).onem == "bicimsel"


def test_derece_ve_tolerans_yazimi_fark_sayilmaz():
    eski = sart("4.5.2", "Accelerated storage stability", "at 49 ±3 °C (120 ± 5 °F) for 2 weeks")
    yeni = sart("4.5.2", "Accelerated storage stability", "at 49 ±3° C (120 ±5° F) for 2 weeks")
    assert sart_farki(eski, yeni) is None


def test_numara_degisimi_isaretlenir():
    fark = sart_farki(sart("6.12", "Subject term (key word) listing", "x"),
                      sart("6.14", "Subject term (key word) listing", "x"))
    assert fark.tur == "degisti"
    assert fark.yeniden_numaralandi
    assert fark.onem is None  # metin aynı


def test_eklenen_ve_kaldirilan_sart():
    yeni = sart("3.12", "Strippability", "shall be removable within 2 hours")
    assert sart_farki(None, yeni).tur == "eklendi"
    assert sart_farki(None, yeni).yeni_degerler == ["2 hour"]
    assert sart_farki(yeni, None).tur == "kaldirildi"


# --- Test tablosu ---------------------------------------------------------------------


H_TABLOSU = [
    ["Test", "Requirement\nParagraph", "Test\nParagraph", "FED-STD-141\nTest Method", "ASTM Test\nMethod"],
    ["Chlorinated solvent content", "3.4", "---", "---", "ASTM-D3742"],
    ["Storage stability 1/", "3.5.3", "---", "3022", "---"],
    ["Drying time 3/", "3.7.2", "---", "---", "ASTM-D1640"],
]
K_TABLOSU = [
    ["Test", "Requirement\nParagraph", "Test\nParagraph", "Test Method"],
    ["Storage stability", "3.5.3", "---", "---"],
    ["Drying time 1/", "3.7.2", "---", "ASTM D5895"],
    ["Strippability", "3.12", "4.5.13", "---"],
]


def test_tablo_satirlari_dipnot_isaretsiz_ve_metot_birlesik_okunur():
    satirlar = tablo_satirlari([(11, H_TABLOSU)])
    assert [s.ad for s in satirlar] == ["Chlorinated solvent content", "Storage stability", "Drying time"]
    assert satirlar[1].metot == "FED-STD-141 Method 3022"
    assert satirlar[2].metot == "ASTM-D1640"
    assert satirlar[0].test_maddesi is None
    assert satirlar[0].sayfa == 11


def test_test_tablosu_farklari():
    eski = tablo_satirlari([(11, H_TABLOSU)])
    yeni = tablo_satirlari([(12, K_TABLOSU)])
    farklar = {f.ad: f for f in tablo_farklari(eski, yeni)}
    assert farklar["Chlorinated solvent content"].tur == "kaldirildi"
    assert farklar["Strippability"].tur == "eklendi"
    assert farklar["Storage stability"].degisen_alanlar == ["metot"]
    assert farklar["Drying time"].degisen_alanlar == ["metot"]


def test_metotta_yalniz_yazim_farki_degisiklik_sayilmaz():
    eski = [TestSatiri(ad="Viscosity", sart_maddesi="3.6.3", test_maddesi=None, metot="ASTM-D1200", sayfa=11)]
    yeni = [TestSatiri(ad="Viscosity", sart_maddesi="3.6.3", test_maddesi=None, metot="ASTM D1200", sayfa=12)]
    assert tablo_farklari(eski, yeni) == []


# --- Bütün karşılaştırma ---------------------------------------------------------------


def _fark() -> RevizyonFarki:
    eski = sozluk(
        sart("3.5.3", "Storage stability", "not less than one year"),
        sart("3.6.3", "Viscosity", "20 to 40 seconds"),
        sart("4.3", "Conformance inspection",
             "all the tests specified in 4.5, with the exception of storage stability (see 3.5.3)."),
        sart("6.7", "Part or Identifying Number (PIN)", "pin"),
    )
    yeni = sozluk(
        sart("1.3", "Part or Identifying Number (PIN)", "pin"),
        sart("3.5.3", "Storage stability", "not less than one year for metal and six months for plastic"),
        sart("3.6.3", "Viscosity", "20 to 40 seconds"),
        sart("3.12", "Strippability", "removable"),
        sart("4.3", "Conformance inspection",
             "all the tests specified in 4.5, with the exception of storage stability (see table II), "
             "and strippability (see 4.5.13)."),
    )
    eski_tablo = tablo_satirlari([(11, H_TABLOSU)])
    yeni_tablo = tablo_satirlari([(12, K_TABLOSU)])
    return karsilastir("MIL-PRF-23377", "H", eski, eski_tablo, "K", yeni, yeni_tablo)


def test_karsilastirma_ozeti():
    fark = _fark()
    assert fark.ozet() == {
        "eklenen_sart": 1, "kaldirilan_sart": 0, "degisen_sart": 2, "sayisal_degisen_sart": 1,
        "yeniden_numaralanan_sart": 1, "ayni_kalan_sart": 1,
        "eklenen_test": 1, "kaldirilan_test": 1, "degisen_test": 2, "supheli_sart": 0,
    }
    assert fark.eski_kabul_disi == ["storage stability"]
    assert fark.yeni_kabul_disi == ["storage stability", "strippability"]


def test_karsilastirma_json_ve_markdown_uretir():
    fark = _fark()
    veri = json.loads(fark.json())
    assert veri["eski_revizyon"] == "H" and veri["yeni_revizyon"] == "K"
    assert {f["tur"] for f in veri["sart_farklari"]} == {"eklendi", "degisti"}
    md = markdown_raporu(fark)
    assert md.startswith("# MIL-PRF-23377H → MIL-PRF-23377K revizyon farkları")
    assert "3.12" in md and "Strippability" in md
    assert "6 month" in md
    assert "6.7 → 1.3" in md


def _dokuman(revizyon: str) -> KabulDokumani:
    def k(madde):
        return Kaynak(belge_no="MIL-PRF-23377", revizyon=revizyon, madde=madde)

    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon=revizyon),
        testler=[
            TestSarti(id="viscosity", test_adi="Viscosity", kaynak=k("3.6.3"), test_turleri={"kabul"},
                      sinir=Sinir(kriter_turu="sayisal", alt=20, ust=40, birim="s", orijinal_metin="20 to 40")),
            TestSarti(id="storage_stability", test_adi="Storage stability", kaynak=k("3.5.3"),
                      test_turleri={"yeterlilik"},
                      sinir=Sinir(kriter_turu="metinsel", orijinal_metin="one year")),
            TestSarti(id="chlorinated_solvent_content", test_adi="Chlorinated solvent content", kaynak=k("3.4"),
                      test_turleri={"kabul"}, sinir=Sinir(kriter_turu="metinsel", orijinal_metin="x")),
        ],
    )


def test_guncelleme_onerileri_eski_kabul_dokumani_icin():
    oneriler = guncelleme_onerileri(_fark(), _dokuman("H"))
    hedefler = {o.hedef: o for o in oneriler}
    assert "test:viscosity" not in hedefler  # değişmedi
    depolama = [o for o in oneriler if o.hedef == "test:storage_stability"]
    assert any(o.tur == "guncelle" and o.madde == "3.5.3" and "6 month" in o.oneri for o in depolama)
    assert any("FED-STD-141 Method 3022" in o.oneri for o in depolama)  # test tablosunda metot değişti
    klorlu = [o for o in oneriler if o.hedef == "test:chlorinated_solvent_content"]
    assert [o.tur for o in klorlu] == ["kaldir"]  # kaldırılan test için madde önerisi ayrıca verilmez
    assert hedefler["yeni_test:Strippability"].tur == "ekle"
    assert hedefler["yeni_test:Strippability"].madde == "3.12"
    # Yeni şart 3.12 yeni testle zaten önerildiği için ayrıca önerilmez.
    assert not any(o.hedef == "yeni_sart:3.12" for o in oneriler)
    assert hedefler["kabul_kapsami:strippability"].tur == "gozden_gecir"


def test_guncelleme_onerileri_ad_tutmazsa_test_tablosunu_sart_maddesiyle_bulur():
    dokuman = _dokuman("H")
    dokuman.testler[2].test_adi = "Chlorinated solvents"  # tablodaki ad farklı yazılmış
    oneriler = [o for o in guncelleme_onerileri(_fark(), dokuman) if o.hedef == "test:chlorinated_solvent_content"]
    assert [o.tur for o in oneriler] == ["kaldir"]


def test_kaldirilan_test_icin_kabul_kapsami_onerisi_verilmez():
    fark = _fark()
    fark.eski_kabul_disi = ["chlorinated solvent content", "storage stability"]
    oneriler = guncelleme_onerileri(fark, _dokuman("H"))
    assert not any(o.hedef == "kabul_kapsami:chlorinated solvent content" for o in oneriler)


def test_guncelleme_onerileri_raf_omru_kosul_ve_numune_icin():
    from malzeme_kabul.sema import Kosul, NumuneHazirlama, RafOmru

    dokuman = _dokuman("H")
    k = Kaynak(belge_no="MIL-PRF-23377", revizyon="H", madde="3.5.3")
    dokuman.raf_omurleri = [RafOmru(sure=1, birim="year", kaynak=k)]
    dokuman.kosullar = [Kosul(kategori="depolama", ad="Depolama", aciklama="x", kaynak=k)]
    dokuman.numune_hazirlama = [NumuneHazirlama(id="panel_A", kaynak=k.model_copy(update={"madde": "6.7"}))]
    hedefler = {o.hedef: o for o in guncelleme_onerileri(_fark(), dokuman)}
    assert hedefler["raf_omru"].tur == "guncelle"
    assert hedefler["kosul:Depolama"].tur == "guncelle"
    assert hedefler["numune:panel_A"].tur == "numara"
    assert "6.7 → 1.3" in hedefler["numune:panel_A"].oneri


def test_markdown_oneri_ve_yazim_farki_bolumleri():
    fark = _fark()
    fark.sart_farklari.append(sart_farki(sart("3.9", "Water", "ASTM-D1"), sart("3.9", "Water", "ASTM D1")))
    md = markdown_raporu(fark, guncelleme_onerileri(fark, _dokuman("H")))
    assert "## Yalnız yazım farkı olan maddeler" in md and "3.9 Water" in md
    assert "## Kabul dokümanı güncelleme önerileri" in md and "yeni_test:Strippability" in md


def test_guncelleme_onerileri_yanlis_revizyonu_reddeder():
    with pytest.raises(ValueError, match="H"):
        guncelleme_onerileri(_fark(), _dokuman("K"))


# --- Gerçek PDF'ler ------------------------------------------------------------------


@pytest.fixture(scope="module")
def h_j() -> RevizyonFarki:
    return revizyonlari_karsilastir(RAW / "MIL-PRF-23377H.pdf", RAW / "MIL-PRF-23377J.pdf", "MIL-PRF-23377", "H", "J")


@pytest.fixture(scope="module")
def j_k() -> RevizyonFarki:
    return revizyonlari_karsilastir(RAW / "MIL-PRF-23377J.pdf", RAW / "MIL-PRF-23377K.pdf", "MIL-PRF-23377", "J", "K")


def _bul(fark: RevizyonFarki, madde: str):
    return next(f for f in fark.sart_farklari if f.madde == madde)


def test_h_j_raf_omru_plastik_kap_icin_degisti(h_j):
    f = _bul(h_j, "3.5.3")
    assert f.onem == "sayisal"
    assert "6 month" in f.yeni_degerler


def test_h_j_pin_bolum_1e_tasindi_ve_toksisite_eklendi(h_j):
    pin = _bul(h_j, "1.3")
    assert pin.yeniden_numaralandi and pin.eski.madde == "6.7"
    c1 = _bul(h_j, "3.4.1.1")
    assert c1.tur == "degisti" and c1.eski.baslik == "Class C"
    n = _bul(h_j, "3.4.1.3")
    assert n.tur == "degisti" and n.eski.madde == "3.4.1.2"
    assert any(f.tur == "eklendi" and f.madde == "4.5.12" for f in h_j.sart_farklari)
    assert "toxicity" in h_j.yeni_kabul_disi and "toxicity" not in h_j.eski_kabul_disi
    assert any(t.ad == "Toxicity" and t.tur == "eklendi" for t in h_j.test_farklari)


def test_j_k_strippability_eklendi_klorlu_cozucu_testi_kaldirildi(j_k):
    assert any(f.tur == "eklendi" and f.madde == "3.12" for f in j_k.sart_farklari)
    testler = {t.ad: t for t in j_k.test_farklari}
    assert testler["Strippability"].tur == "eklendi"
    assert testler["Chlorinated solvent content"].tur == "kaldirildi"
    assert testler["Drying time"].degisen_alanlar == ["metot"]
    assert "strippability" in j_k.yeni_kabul_disi


def test_j_k_depolama_sicakligi_eklendi(j_k):
    f = _bul(j_k, "3.5.3")
    assert "46 °C" in f.yeni_degerler


def test_tablolar_ayri_madde_olarak_karsilastirilir(j_k):
    # Tablo metni paragrafa karışmaz; tablo kendi maddesi olur ("TABLE II").
    paragraf = _bul(j_k, "4.5")
    assert "TABLE II" not in paragraf.yeni.metin
    assert "3022" not in paragraf.eski_degerler
    # Test tablosunun satırları ayrıca karşılaştırıldığı için metinde yalnız dipnotlar kalır.
    # J'de depolama sıcaklığı TABLE II dipnotundaydı, K'de 3.5.3'e taşındı.
    tablo = _bul(j_k, "TABLE II")
    assert tablo.eski.metin.startswith("1/ ")
    assert "46 °C" in tablo.eski_degerler
    assert tablo.yeni.bolum == 4
    # Panel tablosu bütün metniyle karşılaştırılır.
    panel = _bul(j_k, "TABLE I")
    assert any("MIL-DTL-5541" in d.yeni for d in panel.degisiklikler)


def test_tablo_maddesi_sart_olarak_okunur(tmp_path):
    from malzeme_kabul.revizyon_karsilastirici import tablolari_ayir

    metin, tablolar = tablolari_ayir(
        "Panels shall be prepared. TABLE I. Aluminum test panels. Panel Substrate A 2024 "
        "1/ Immerse for 2 minutes.", "4.4", 10)
    assert metin == "Panels shall be prepared."
    assert len(tablolar) == 1
    t = tablolar[0]
    assert (t.madde, t.baslik, t.sayfa, t.ust) == ("TABLE I", "Aluminum test panels", 10, "4.4")
    assert t.metin == "Panel Substrate A 2024 1/ Immerse for 2 minutes."
    _, tablolar = tablolari_ayir("x. TABLE II. Test methods. Viscosity 3.6.3 --- 1/ Use panels A.", "4.5", 11)
    assert tablolar[0].metin == "1/ Use panels A."


def test_arka_kapak_metni_farka_girmez(j_k):
    for f in j_k.sart_farklari:
        for s in (f.eski, f.yeni):
            if s is not None:
                assert "Custodians" not in s.metin


# --- Betik ----------------------------------------------------------------------------


def test_betik_json_ve_markdown_yazar(tmp_path):
    betik = betik_yukle("scripts/revizyon_karsilastir.py")
    kod = betik.main([str(RAW / "MIL-PRF-23377J.pdf"), str(RAW / "MIL-PRF-23377K.pdf"), "--cikti", str(tmp_path)])
    assert kod == 0
    temel = tmp_path / "MIL-PRF-23377_J-K_revizyon_farklari"
    veri = json.loads(temel.with_suffix(".json").read_text(encoding="utf-8"))
    assert veri["yeni_revizyon"] == "K"
    assert "guncelleme_onerileri" in veri
    assert temel.with_suffix(".md").read_text(encoding="utf-8").startswith("# MIL-PRF-23377J → MIL-PRF-23377K")


def test_betik_farkli_belgeleri_reddeder(tmp_path):
    betik = betik_yukle("scripts/revizyon_karsilastir.py")
    with pytest.raises(SystemExit):
        betik.main([str(RAW / "MIL-PRF-23377J.pdf"), str(RAW / "MIL-PRF-85285E.pdf"), "--cikti", str(tmp_path)])


# --- Şüpheli değişiklikler ---------------------------------------------------------


def test_sifir_tolerans_supheli_isaretlenir():
    eski = sart("4.5", "Test methods", "a relative humidity of 50 ± 10 percent.")
    yeni = sart("4.5", "Test methods", "a relative humidity of 50 ±0 percent.")
    fark = sart_farki(eski, yeni)
    assert fark.onem == "sayisal"
    assert any("±0" in n for n in fark.supheli)


def test_sifira_inen_deger_supheli_isaretlenir():
    from malzeme_kabul.revizyon_karsilastirici import supheli_nedenleri

    assert any("sıfır" in n for n in supheli_nedenleri("x", "y", ["5 minute"], ["0 minute"]))


def test_on_kattan_buyuk_degisim_supheli_isaretlenir():
    from malzeme_kabul.revizyon_karsilastirici import supheli_nedenleri

    assert any("10 kat" in n for n in supheli_nedenleri("x", "y", ["24 hour"], ["240 hour"]))
    # Olağan sınır değişikliği şüpheli değildir.
    assert supheli_nedenleri("x", "y", ["0.06 %"], ["0.05 %"]) == []
    assert supheli_nedenleri("x", "y", [], ["6 month"]) == []


def test_supheli_fark_raporda_ve_oneride_insan_incelemeli_gorunur():
    fark = _fark()
    fark.sart_farklari.append(sart_farki(
        sart("3.6.3", "Viscosity", "20 to 40 seconds at 50 ± 10 percent"),
        sart("3.6.3", "Viscosity", "20 to 40 seconds at 50 ±0 percent")))
    assert fark.ozet()["supheli_sart"] == 1
    md = markdown_raporu(fark, guncelleme_onerileri(fark, _dokuman("H")))
    assert "## Şüpheli değişiklikler (insan incelemeli)" in md
    visk = [o for o in guncelleme_onerileri(fark, _dokuman("H")) if o.hedef == "test:viscosity"]
    assert visk and visk[0].tur == "gozden_gecir" and visk[0].oneri.startswith("Şüpheli, insan incelemeli")


def test_j_k_bagil_nem_toleransi_supheli(j_k):
    f = _bul(j_k, "4.5")
    assert f.supheli and any("±0" in n for n in f.supheli)
    assert sum(bool(x.supheli) for x in j_k.sart_farklari) <= 3  # gürültü üretmemeli
