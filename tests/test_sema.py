"""Kabul dokümanı şemasının (Pydantic) testleri."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from malzeme_kabul.sema import (
    KabulDokumani,
    Kaynak,
    Kosul,
    NumuneHazirlama,
    RafOmru,
    Sinir,
    StandartBilgisi,
)
from malzeme_kabul.sema import TestSarti as Sart  # "Test" önekli ad pytest'e sınıf gibi görünmesin


def kaynak(madde="3.5.1", belge_no="MIL-PRF-23377", revizyon="K", **ek):
    return Kaynak(belge_no=belge_no, revizyon=revizyon, madde=madde, **ek)


def sayisal(alt=None, ust=None, birim=None, metin="20 to 30 seconds", **ek):
    return Sinir(kriter_turu="sayisal", alt=alt, ust=ust, birim=birim, orijinal_metin=metin, **ek)


def ornek_sart(**ek):
    veri = dict(
        id="viskozite",
        test_adi="Viscosity",
        test_metodu="ASTM D 1200",
        sinir=sayisal(20, 30, "s"),
        kaynak=kaynak(),
        test_turleri={"kabul"},
    )
    return Sart(**(veri | ek))


# --- Kaynak ----------------------------------------------------------------------


def test_kaynak_belge_no_revizyon_ve_madde_zorunlu():
    with pytest.raises(ValidationError):
        Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde="")
    with pytest.raises(ValidationError):
        Kaynak(belge_no="", revizyon="K", madde="3.5")
    with pytest.raises(ValidationError):
        Kaynak(belge_no="MIL-PRF-23377", revizyon="", madde="3.5")


@pytest.mark.parametrize("madde", ["3.5.1", "4.6.12.3", "3.4", "TABLE I", "TABLE II", "A.3.1"])
def test_kaynak_gecerli_madde_bicimleri(madde):
    assert kaynak(madde).madde == madde


@pytest.mark.parametrize("madde", ["madde 3", "3..4", "abc"])
def test_kaynak_gecersiz_madde_reddedilir(madde):
    with pytest.raises(ValidationError):
        kaynak(madde)


def test_kaynak_etiketi_belge_revizyon_ve_madde_icerir():
    assert kaynak("3.5.1").etiket == "MIL-PRF-23377K, 3.5.1"


def test_musteri_sartnamesi_kaynagi_rev_ile_ayri_yazilir():
    k = kaynak("2.1", belge_no="MUSTERI-SPEC-001", revizyon="B")
    assert k.etiket == "MUSTERI-SPEC-001 Rev. B, 2.1"


# --- Sınır -----------------------------------------------------------------------


def test_sayisal_sinir_alt_ve_ust_istege_bagli_ama_en_az_biri_gerekli():
    assert sayisal(alt=4, birim="hour").ust is None
    assert sayisal(ust=340, birim="g/L").alt is None
    assert sayisal(20, 30, "s").alt == 20
    with pytest.raises(ValidationError):
        sayisal(birim="s")


def test_sayisal_sinirda_alt_usttan_buyuk_olamaz():
    with pytest.raises(ValidationError):
        sayisal(30, 20, "s")


def test_alt_ust_esitse_tam_deger_sartidir():
    assert sayisal(7, 7).alt == 7


def test_birim_pintin_tanidigi_bicimde_olmali():
    assert sayisal(alt=40, ust=100, birim="°F").birim == "°F"
    with pytest.raises(ValidationError):
        sayisal(alt=4, birim="saat")


def test_birimsiz_sayisal_sinir_kabul_edilir():
    # pH, oran gibi birimsiz büyüklükler.
    assert sayisal(alt=7).birim is None


def test_orijinal_metin_zorunlu():
    with pytest.raises(ValidationError):
        Sinir(kriter_turu="sayisal", alt=1, orijinal_metin="")


def test_metinsel_kriter_sayi_ve_birim_almaz():
    s = Sinir(kriter_turu="metinsel", orijinal_metin="There shall be no blistering")
    assert s.alt is None and s.ust is None and s.birim is None
    with pytest.raises(ValidationError):
        Sinir(kriter_turu="metinsel", orijinal_metin="x", alt=1)
    with pytest.raises(ValidationError):
        Sinir(kriter_turu="metinsel", orijinal_metin="x", birim="s")


def test_gecti_kaldi_kriteri_sayi_almaz():
    assert Sinir(kriter_turu="gecti_kaldi", orijinal_metin="Shall pass").kriter_turu == "gecti_kaldi"
    with pytest.raises(ValidationError):
        Sinir(kriter_turu="gecti_kaldi", orijinal_metin="x", ust=3)


def test_bilinmeyen_kriter_turu_reddedilir():
    with pytest.raises(ValidationError):
        Sinir(kriter_turu="aralik", alt=1, orijinal_metin="x")


def test_sinirlarin_varsayilani_dahil():
    s = sayisal(20, 30, "s")
    assert s.alt_dahil and s.ust_dahil


# --- TestSarti -------------------------------------------------------------------


def test_test_sarti_en_az_bir_test_turu_ister():
    with pytest.raises(ValidationError):
        ornek_sart(test_turleri=set())


def test_test_sarti_hem_kabul_hem_omur_uzatma_olabilir():
    t = ornek_sart(test_turleri={"kabul", "omur_uzatma"})
    assert t.kabul_testi and t.omur_uzatma_testi


def test_bilinmeyen_test_turu_reddedilir():
    with pytest.raises(ValidationError):
        ornek_sart(test_turleri={"rastgele"})


def test_test_sarti_kaynak_zorunlu():
    with pytest.raises(ValidationError):
        ornek_sart(kaynak=None)


def test_uygulanabilirlik_bossa_tum_tip_ve_siniflara_gecerli():
    assert ornek_sart().uygulanabilirlik == []
    t = ornek_sart(uygulanabilirlik=["Type I", "Class C2"])
    assert t.uygulanabilirlik == ["Type I", "Class C2"]


def test_test_metodu_maddesi_baska_belgeden_olabilir():
    t = ornek_sart(metot_kaynagi=kaynak("4.6.3"))
    assert t.metot_kaynagi.madde == "4.6.3"


# --- Raf ömrü, koşullar, numune -------------------------------------------------


def test_raf_omru_sure_birim_ve_kosul_yapilandirilmis():
    r = RafOmru(
        sure=12, birim="month",
        kosul=sayisal(4, 38, "°C", metin="stored between 40 and 100 °F"),
        kaynak=kaynak("3.7"),
    )
    assert r.sure == 12 and r.birim == "month" and r.kosul.ust == 38


def test_raf_omru_pozitif_sure_ve_zaman_birimi_ister():
    with pytest.raises(ValidationError):
        RafOmru(sure=0, birim="month", kaynak=kaynak("3.7"))
    with pytest.raises(ValidationError):
        RafOmru(sure=12, birim="g/L", kaynak=kaynak("3.7"))
    with pytest.raises(ValidationError):
        RafOmru(sure=12, birim="ay", kaynak=kaynak("3.7"))


def test_kosul_sinir_ya_da_aciklama_ister():
    with pytest.raises(ValidationError):
        Kosul(kategori="depolama", ad="Depolama sıcaklığı", kaynak=kaynak("3.7"))
    k = Kosul(kategori="depolama", ad="Depolama sıcaklığı", sinir=sayisal(4, 38, "°C"), kaynak=kaynak("3.7"))
    assert k.kategori == "depolama"


def test_kosul_kategorisi_depolama_ya_da_kullanim():
    Kosul(kategori="kullanim", ad="Kap ömrü", aciklama="4 saat", kaynak=kaynak("3.5.2"))
    with pytest.raises(ValidationError):
        Kosul(kategori="nakliye", ad="x", aciklama="y", kaynak=kaynak())


def test_numune_hazirlama_kupon_uygulama_kurlenme_alanlari():
    n = NumuneHazirlama(
        id="genel_panel",
        kupon_malzemesi="2024-T3 aluminyum",
        kupon_boyutu="3 x 6 x 0.020 inch",
        yuzey_hazirligi="MIL-DTL-81706 kimyasal dönüşüm kaplaması",
        uygulama_yontemi="Püskürtme",
        kuru_film_kalinligi=sayisal(0.6, 0.9, "mil", metin="0.6 to 0.9 mil"),
        kurlenme="7 gün, oda sıcaklığında",
        kaynak=kaynak("4.5.2"),
    )
    assert n.kuru_film_kalinligi.ust == 0.9


def test_test_sarti_numune_hazirligina_id_ile_baglanir():
    assert ornek_sart(numune_hazirlama_id="genel_panel").numune_hazirlama_id == "genel_panel"


# --- KabulDokumani ---------------------------------------------------------------


def dokuman(**ek):
    veri = dict(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K", baslik="Primer coatings: epoxy, high-solids"),
        testler=[ornek_sart()],
    )
    return KabulDokumani(**(veri | ek))


def test_kabul_dokumani_varsayilan_durumu_taslak():
    assert dokuman().durum == "taslak"


def test_test_kimlikleri_benzersiz_olmali():
    with pytest.raises(ValidationError):
        dokuman(testler=[ornek_sart(), ornek_sart()])


def test_sartlar_farkli_belgelere_dayanabilir():
    # Müşteri şartnamesi ve revizyon takibi için her şart kendi kaynağını taşır.
    musteri = ornek_sart(id="musteri_viskozite", kaynak=kaynak("2.1", belge_no="MUSTERI-SPEC-001", revizyon="B"))
    d = dokuman(testler=[ornek_sart(), musteri])
    assert {t.kaynak.belge_no for t in d.testler} == {"MIL-PRF-23377", "MUSTERI-SPEC-001"}


def test_bilinmeyen_numune_hazirligina_bagli_test_reddedilir():
    with pytest.raises(ValidationError):
        dokuman(testler=[ornek_sart(numune_hazirlama_id="olmayan")])


def test_kabul_dokumani_json_gidis_donus():
    d = dokuman(
        raf_omurleri=[RafOmru(sure=12, birim="month", kosul=sayisal(4, 38, "°C"), kaynak=kaynak("3.7"))],
        kosullar=[Kosul(kategori="kullanim", ad="Kap ömrü", aciklama="4 saat", kaynak=kaynak("3.5.2"))],
    )
    assert KabulDokumani.model_validate_json(d.model_dump_json()) == d


def test_kabul_ve_omur_uzatma_testleri_ayri_listelenir():
    d = dokuman(
        testler=[
            ornek_sart(id="a", test_turleri={"kabul"}),
            ornek_sart(id="b", test_turleri={"omur_uzatma"}),
            ornek_sart(id="c", test_turleri={"kabul", "omur_uzatma"}),
            ornek_sart(id="d", test_turleri={"yeterlilik"}),
        ]
    )
    assert [t.id for t in d.kabul_testleri] == ["a", "c"]
    assert [t.id for t in d.omur_uzatma_testleri] == ["b", "c"]
    # Çapraz kontrol yalnızca kabul testlerine bakar; yeterlilik testleri aranmaz.
    assert "d" not in [t.id for t in d.kabul_testleri]


def test_test_turleri_json_da_sirali_yazilir():
    t = ornek_sart(test_turleri={"yeterlilik", "kabul", "omur_uzatma"})
    assert t.model_dump(mode="json")["test_turleri"] == ["kabul", "omur_uzatma", "yeterlilik"]


def test_kap_turune_gore_birden_cok_raf_omru_kaydi():
    d = dokuman(raf_omurleri=[
        RafOmru(kap_turu="metal", sure=1, birim="year", kaynak=kaynak("3.5.3")),
        RafOmru(kap_turu="plastik", sure=6, birim="month", kaynak=kaynak("3.5.3")),
    ])
    assert [(r.kap_turu, r.sure, r.birim) for r in d.raf_omurleri] == [("metal", 1, "year"), ("plastik", 6, "month")]


def test_ayni_kap_turu_icin_iki_raf_omru_kaydi_reddedilir():
    with pytest.raises(ValidationError):
        dokuman(raf_omurleri=[
            RafOmru(kap_turu="metal", sure=1, birim="year", kaynak=kaynak("3.5.3")),
            RafOmru(kap_turu="Metal", sure=2, birim="year", kaynak=kaynak("3.5.3")),
        ])


def test_raf_omru_kap_turu_bossa_genel_kayittir():
    assert RafOmru(sure=12, birim="month", kaynak=kaynak("3.7")).kap_turu is None
