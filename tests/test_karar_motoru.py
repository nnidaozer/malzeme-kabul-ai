"""Karar motorunun testleri.

Karar motoru sertifikadaki ham metinleri (test adı, sonuç, birim) kabul
dokümanıyla kesin kurallarla karşılaştırır (CLAUDE.md, kural 1).
"""

from __future__ import annotations

import pytest

from malzeme_kabul.karar_motoru import (
    KararAyarlari,
    atfi_coz,
    birimi_cevir,
    kontrol_et,
    sonucu_ayristir,
    eslestir,
    uygulanir_mi,
)
from malzeme_kabul.sema import KabulDokumani
from malzeme_kabul.sertifika import Sertifika, SertifikaSatiri


def _kaynak(madde: str) -> dict:
    return {"belge_no": "MIL-PRF-23377", "revizyon": "K", "madde": madde}


def _test(id_, ad, sinir, madde, turler=("kabul", "yeterlilik"), uyg=()):
    return {
        "id": id_,
        "test_adi": ad,
        "sinir": sinir,
        "kaynak": _kaynak(madde),
        "test_turleri": list(turler),
        "uygulanabilirlik": list(uyg),
    }


def _sayisal(alt=None, ust=None, birim=None, alt_dahil=True, ust_dahil=True):
    return {
        "kriter_turu": "sayisal",
        "alt": alt,
        "ust": ust,
        "birim": birim,
        "alt_dahil": alt_dahil,
        "ust_dahil": ust_dahil,
        "orijinal_metin": "metin",
    }


METINSEL = {"kriter_turu": "metinsel", "orijinal_metin": "free of grit"}


@pytest.fixture
def dokuman() -> KabulDokumani:
    return KabulDokumani.model_validate(
        {
            "standart": {"belge_no": "MIL-PRF-23377", "revizyon": "K"},
            "testler": [
                _test("voc_solvent_content", "VOC solvent content", _sayisal(ust=340, birim="g/L"), "3.4.2"),
                _test("drying_time", "Drying time", _sayisal(ust=5, birim="hour"), "3.7.2"),
                _test("fineness_of_grind", "Fineness of grind", _sayisal(alt=5), "3.5.1"),
                _test("adhesion", "Adhesion", _sayisal(alt=4), "3.7.4"),
                _test("application", "Application", _sayisal(alt=15, ust=23, birim="µm"), "3.9.2"),
                _test("condition_in_container", "Condition in container", METINSEL, "3.5.2"),
                _test(
                    "infrared_reflectance_type_ii_only",
                    "Infrared reflectance (type II only)",
                    _sayisal(ust=10, birim="%"),
                    "3.7.6",
                    uyg=["Type II"],
                ),
                _test(
                    "chromium_content_class_n_only",
                    "Chromium content (class N only)",
                    _sayisal(ust=5, birim="ppm"),
                    "3.4.1.3",
                    uyg=["Class N"],
                ),
                _test("toxicity", "Toxicity", METINSEL, "3.3", turler=("yeterlilik",)),
            ],
        }
    )


def _tam_sertifika(**degisiklik) -> Sertifika:
    satirlar = {
        "VOC solvent content": ("320", "g/L"),
        "Drying time": ("4", "h"),
        "Fineness of grind": ("6", None),
        "Adhesion": ("5A", None),
        "Application": ("20", "µm"),
        "Condition in container": ("Conforms", None),
    }
    satirlar.update(degisiklik.pop("satirlar", {}))
    veri = {
        "sertifika_no": "S-001",
        "standart_atfi": "MIL-PRF-23377K Type I Class C2",
        "satirlar": [
            {"test_adi": ad, "sonuc": s, "birim": b} for ad, v in satirlar.items() if v is not None for s, b in [v]
        ],
    }
    veri.update(degisiklik)
    return Sertifika.model_validate(veri)


# --- atıf -----------------------------------------------------------------


@pytest.mark.parametrize(
    "metin, beklenen",
    [
        ("MIL-PRF-23377K Type I Class C2", ("MIL-PRF-23377", "K", "I", "C2")),
        ("MIL-PRF-23377 Rev. J, Type II, Class N", ("MIL-PRF-23377", "J", "II", "N")),
        ("mil-prf-23377k type 1 class n", ("MIL-PRF-23377", "K", "I", "N")),
        ("MIL-PRF-23377H", ("MIL-PRF-23377", "H", None, None)),
        ("MIL-PRF-23377", ("MIL-PRF-23377", None, None, None)),
        ("Tip II, Sınıf C1, MIL-PRF-23377K", ("MIL-PRF-23377", "K", "II", "C1")),
    ],
)
def test_atfi_coz(metin, beklenen):
    a = atfi_coz(metin)
    assert (a.belge_no, a.revizyon, a.tip, a.sinif) == beklenen


def test_atif_bulunamazsa_belge_no_none():
    assert atfi_coz("Epoxy primer").belge_no is None


# --- uygulanabilirlik -----------------------------------------------------


@pytest.mark.parametrize(
    "uyg, tip, sinif, beklenen",
    [
        ([], "I", "C2", True),
        (["Type II"], "II", "C2", True),
        (["Type II"], "I", "N", False),
        (["Class N"], "I", "N", True),
        (["Class N"], "II", "C1", False),
        (["Type II"], None, "C1", None),
        (["Class N"], "I", None, None),
    ],
)
def test_uygulanir_mi(uyg, tip, sinif, beklenen):
    assert uygulanir_mi(uyg, tip, sinif) is beklenen


# --- sonuç ayrıştırma -----------------------------------------------------


@pytest.mark.parametrize(
    "metin, tur, alt, ust, alt_dahil, ust_dahil",
    [
        ("320", "sayi", 320.0, 320.0, True, True),
        ("1,5", "sayi", 1.5, 1.5, True, True),
        ("  339.8 ", "sayi", 339.8, 339.8, True, True),
        ("<1", "sayi", None, 1.0, True, False),
        ("≤ 1", "sayi", None, 1.0, True, True),
        ("> 10", "sayi", 10.0, None, False, True),
        ("5A", "sayi", 5.0, 5.0, True, True),
        ("4B", "sayi", 4.0, 4.0, True, True),
    ],
)
def test_sayisal_sonuc_araliga_cevrilir(metin, tur, alt, ust, alt_dahil, ust_dahil):
    s = sonucu_ayristir(metin)
    assert s.tur == tur
    assert (s.alt, s.ust, s.alt_dahil, s.ust_dahil) == (alt, ust, alt_dahil, ust_dahil)


@pytest.mark.parametrize("metin", ["Pass", "Conforms", "Complies", "Satisfactory", "Uygun", "Geçti", "OK", "Meets requirement"])
def test_gecti_ifadeleri(metin):
    assert sonucu_ayristir(metin).tur == "gecti"


@pytest.mark.parametrize("metin", ["Fail", "Failed", "Does not conform", "Uygun değil", "Kaldı", "Non-conforming"])
def test_kaldi_ifadeleri(metin):
    assert sonucu_ayristir(metin).tur == "kaldi"


@pytest.mark.parametrize("metin", ["ND", "Not detected", "see attached", "15-20", "", "Slight grit"])
def test_anlasilmayan_sonuc_belirsiz(metin):
    assert sonucu_ayristir(metin).tur == "belirsiz"


# --- birim dönüşümü -------------------------------------------------------


@pytest.mark.parametrize(
    "deger, kaynak, hedef, beklenen",
    [
        (270, "min", "hour", 4.5),
        (270, "dk", "hour", 4.5),
        (0.25, "day", "hour", 6.0),
        (2, "saat", "hour", 2.0),
        (0.8, "mil", "µm", 20.32),
        (0.8, "mils", "µm", 20.32),
        (20, "um", "µm", 20.0),
        (2.8, "lb/gal", "g/L", 335.514),
        (300, "g/l", "g/L", 300.0),
        (0.0001, "%", "ppm", 1.0),
        (45, "sec", "s", 45.0),
        (45, "sn", "s", 45.0),
    ],
)
def test_birimi_cevir(deger, kaynak, hedef, beklenen):
    assert birimi_cevir(deger, kaynak, hedef) == pytest.approx(beklenen, rel=1e-4)


@pytest.mark.parametrize("kaynak, hedef", [("cP", "s"), ("xyz", "hour"), ("g/L", "%")])
def test_cevrilemeyen_birim_valueerror(kaynak, hedef):
    with pytest.raises(ValueError):
        birimi_cevir(1, kaynak, hedef)


def test_birim_yoksa_ve_hedef_yoksa_deger_aynen_doner():
    assert birimi_cevir(6, None, None) == 6


@pytest.mark.parametrize("kaynak, hedef", [(None, "hour"), ("hour", None)])
def test_birimlerden_biri_eksikse_valueerror(kaynak, hedef):
    with pytest.raises(ValueError):
        birimi_cevir(1, kaynak, hedef)


# --- test eşleştirme ------------------------------------------------------


@pytest.mark.parametrize(
    "ad, beklenen",
    [
        ("VOC solvent content", "voc_solvent_content"),
        ("voc  solvent CONTENT", "voc_solvent_content"),
        ("Drying Time", "drying_time"),
        ("Chromium content", "chromium_content_class_n_only"),
        ("Infrared reflectance", "infrared_reflectance_type_ii_only"),
        ("Fineness of grind (Hegman)", "fineness_of_grind"),
    ],
)
def test_testi_esle_ad_ile(dokuman, ad, beklenen):
    assert eslestir(ad, dokuman.testler) == beklenen


def test_testi_esle_bilinmeyen_ad_none(dokuman):
    assert eslestir("Gloss at 60 degrees", dokuman.testler) is None


# --- kontrol_et: satır kararları -----------------------------------------


def _satir(sonuc, test_id):
    return next(s for s in sonuc.satirlar if s.test_id == test_id)


def test_temiz_sertifika_kabul(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika())
    assert sonuc.belge_karari == "kabul"
    assert {s.karar for s in sonuc.satirlar} == {"uygun"}


def test_yalniz_kabul_testleri_aranir(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika())
    idler = {s.test_id for s in sonuc.satirlar}
    assert "toxicity" not in idler  # yalnız yeterlilik


def test_uygulanmayan_testler_aranmaz(dokuman):
    # Type I Class C2: kızılötesi (Type II) ve krom (Class N) uygulanmaz
    sonuc = kontrol_et(dokuman, _tam_sertifika())
    idler = {s.test_id for s in sonuc.satirlar}
    assert "infrared_reflectance_type_ii_only" not in idler
    assert "chromium_content_class_n_only" not in idler


def test_tip_ii_icin_kizilotesi_aranir(dokuman):
    sert = _tam_sertifika(standart_atfi="MIL-PRF-23377K Type II Class C2")
    sonuc = kontrol_et(dokuman, sert)
    assert _satir(sonuc, "infrared_reflectance_type_ii_only").karar == "insan_incelemeli"  # eksik


def test_tip_bilinmiyorsa_kisitli_test_insan_incelemeli(dokuman):
    sert = _tam_sertifika(standart_atfi="MIL-PRF-23377K")
    sonuc = kontrol_et(dokuman, sert)
    assert _satir(sonuc, "infrared_reflectance_type_ii_only").karar == "insan_incelemeli"


def test_sinir_disi_deger_uygun_degil_ve_madde_gosterilir(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"VOC solvent content": ("365", "g/L")}))
    satir = _satir(sonuc, "voc_solvent_content")
    assert satir.karar == "uygun_degil"
    assert satir.madde == "MIL-PRF-23377K, 3.4.2"
    assert sonuc.belge_karari == "red"


def test_tam_sinirda_dahil_ise_uygun(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"VOC solvent content": ("340", "g/L")}))
    assert _satir(sonuc, "voc_solvent_content").karar == "uygun"


def test_sinirin_hemen_disi_uygun_degil(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"VOC solvent content": ("340.2", "g/L")}))
    assert _satir(sonuc, "voc_solvent_content").karar == "uygun_degil"


def test_dahil_olmayan_sinirda_uygun_degil():
    dok = KabulDokumani.model_validate(
        {
            "standart": {"belge_no": "MIL-PRF-23377", "revizyon": "K"},
            "testler": [_test("t", "Filament", _sayisal(ust=3.175, birim="mm", ust_dahil=False), "3.8.2.2", turler=("kabul",))],
        }
    )
    sert = Sertifika.model_validate(
        {"sertifika_no": "x", "standart_atfi": "MIL-PRF-23377K", "satirlar": [{"test_adi": "Filament", "sonuc": "3.175", "birim": "mm"}]}
    )
    assert kontrol_et(dok, sert).satirlar[0].karar == "uygun_degil"


def test_birim_cevrilerek_karsilastirilir(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"Drying time": ("270", "min")}))
    satir = _satir(sonuc, "drying_time")
    assert satir.karar == "uygun"
    assert satir.cevrilmis_deger == pytest.approx(4.5)


def test_kucuk_sayi_buyuk_birim_yanlis_kabul_edilmez(dokuman):
    # 0,25 gün = 6 saat > 5 saat
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"Drying time": ("0.25", "day")}))
    assert _satir(sonuc, "drying_time").karar == "uygun_degil"


def test_mil_uzunluk_olarak_cevrilir(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"Application": ("0.8", "mil")}))
    assert _satir(sonuc, "application").karar == "uygun"


def test_cevrilemeyen_birim_insan_incelemeli(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"Drying time": ("4", "cP")}))
    assert _satir(sonuc, "drying_time").karar == "insan_incelemeli"
    assert sonuc.belge_karari == "inceleme"


def test_birimli_sinirda_birimsiz_sonuc_insan_incelemeli(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"Drying time": ("4", None)}))
    assert _satir(sonuc, "drying_time").karar == "insan_incelemeli"


def test_kucuktur_ifadesi_sinirin_icindeyse_uygun(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"Drying time": ("<4", "hour")}))
    assert _satir(sonuc, "drying_time").karar == "uygun"


def test_kucuktur_ifadesi_sinirin_ustundeyse_insan_incelemeli(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"Drying time": ("<8", "hour")}))
    assert _satir(sonuc, "drying_time").karar == "insan_incelemeli"


def test_sayisal_teste_gecti_yazilmissa_insan_incelemeli(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"Drying time": ("Pass", None)}))
    assert _satir(sonuc, "drying_time").karar == "insan_incelemeli"


def test_metinsel_test_fail_uygun_degil(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"Condition in container": ("Fail", None)}))
    assert _satir(sonuc, "condition_in_container").karar == "uygun_degil"


def test_metinsel_test_belirsiz_sonuc_insan_incelemeli(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"Condition in container": ("slight grit", None)}))
    assert _satir(sonuc, "condition_in_container").karar == "insan_incelemeli"


def test_eksik_test_varsayilan_insan_incelemeli(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"Adhesion": None}))
    satir = _satir(sonuc, "adhesion")
    assert satir.karar == "insan_incelemeli"
    assert satir.okunan_sonuc is None


def test_eksik_test_karari_ayarlanabilir(dokuman):
    ayar = KararAyarlari(eksik_test="uygun_degil")
    sonuc = kontrol_et(dokuman, _tam_sertifika(satirlar={"Adhesion": None}), ayar)
    assert _satir(sonuc, "adhesion").karar == "uygun_degil"
    assert sonuc.belge_karari == "red"


def test_ayni_test_iki_kez_verilmisse_insan_incelemeli(dokuman):
    sert = _tam_sertifika()
    sert.satirlar.append(SertifikaSatiri(test_adi="Drying time", sonuc="6", birim="h"))
    assert _satir(kontrol_et(dokuman, sert), "drying_time").karar == "insan_incelemeli"


def test_eslesmeyen_sertifika_satirlari_raporlanir(dokuman):
    sert = _tam_sertifika()
    sert.satirlar.append(SertifikaSatiri(test_adi="Gloss", sonuc="85"))
    sonuc = kontrol_et(dokuman, sert)
    assert sonuc.eslesmeyen_satirlar == ["Gloss"]
    assert sonuc.belge_karari == "kabul"


# --- belge düzeyi: revizyon ----------------------------------------------


def test_yanlis_revizyon_varsayilan_inceleme(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(standart_atfi="MIL-PRF-23377J Type I Class C2"))
    assert sonuc.revizyon.karar == "insan_incelemeli"
    assert sonuc.belge_karari == "inceleme"


def test_yanlis_revizyon_karari_ayarlanabilir(dokuman):
    ayar = KararAyarlari(yanlis_revizyon="uygun_degil")
    sonuc = kontrol_et(dokuman, _tam_sertifika(standart_atfi="MIL-PRF-23377H Type I Class C2"), ayar)
    assert sonuc.belge_karari == "red"


def test_revizyonsuz_atif_insan_incelemeli(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(standart_atfi="MIL-PRF-23377 Type I Class C2"))
    assert sonuc.revizyon.karar == "insan_incelemeli"


def test_dogru_revizyon_uygun(dokuman):
    assert kontrol_et(dokuman, _tam_sertifika()).revizyon.karar == "uygun"


def test_baska_standart_atfi_uygun_degil(dokuman):
    sonuc = kontrol_et(dokuman, _tam_sertifika(standart_atfi="MIL-PRF-85285E Type I"))
    assert sonuc.revizyon.karar == "uygun_degil"
    assert sonuc.belge_karari == "red"


def test_red_incelemeden_onceliklidir(dokuman):
    sert = _tam_sertifika(standart_atfi="MIL-PRF-23377J Type I Class C2", satirlar={"VOC solvent content": ("400", "g/L")})
    assert kontrol_et(dokuman, sert).belge_karari == "red"


@pytest.mark.parametrize(
    "metin, ust, ust_dahil, birim",
    [
        ("ND (<0.5 ppm)", 0.5, False, "ppm"),
        ("ND, ≤ 1", 1.0, True, None),
        ("Not detected (< 0.2 ppm)", 0.2, False, "ppm"),
        ("Tespit edilmedi (<1 ppm)", 1.0, False, "ppm"),
    ],
)
def test_algilama_siniri_verilmis_nd(metin, ust, ust_dahil, birim):
    s = sonucu_ayristir(metin)
    assert (s.tur, s.alt, s.ust, s.ust_dahil, s.birim_ek) == ("sayi", None, ust, ust_dahil, birim)


@pytest.fixture
def kadmiyum_dokumani() -> KabulDokumani:
    return KabulDokumani.model_validate(
        {
            "standart": {"belge_no": "MIL-PRF-23377", "revizyon": "K"},
            "testler": [_test("cd", "Cadmium content", _sayisal(ust=1, birim="ppm"), "3.4", turler=("kabul",))],
        }
    )


@pytest.mark.parametrize(
    "sonuc, birim, karar",
    [
        ("<1", "ppm", "uygun"),
        ("< 1 ppm", None, "uygun"),
        ("ND (<0.5 ppm)", None, "uygun"),
        ("ND", "ppm", "insan_incelemeli"),
        ("ND (<2 ppm)", None, "insan_incelemeli"),
        ("<2", "ppm", "insan_incelemeli"),
    ],
)
def test_algilama_siniri_kararlari(kadmiyum_dokumani, sonuc, birim, karar):
    sert = Sertifika.model_validate(
        {
            "sertifika_no": "x",
            "standart_atfi": "MIL-PRF-23377K",
            "satirlar": [{"test_adi": "Cadmium content", "sonuc": sonuc, "birim": birim}],
        }
    )
    assert kontrol_et(kadmiyum_dokumani, sert).satirlar[0].karar == karar
