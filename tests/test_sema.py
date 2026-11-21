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

K = {"standart": "MIL-PRF-23377", "revizyon": "K", "madde": "3.5.1"}


def kaynak(madde="3.5.1", **ek):
    return Kaynak(**(K | {"madde": madde} | ek))


def ornek_sart(**ek):
    veri = dict(
        id="viskozite",
        test_adi="Viscosity",
        test_metodu="ASTM D 1200",
        sinir=Sinir(tur="aralik", alt=20, ust=30, birim="s"),
        kaynak=kaynak(),
        test_turleri={"kabul"},
    )
    return Sart(**(veri | ek))


# --- Kaynak ----------------------------------------------------------------------


def test_kaynak_madde_numarasi_zorunlu():
    with pytest.raises(ValidationError):
        Kaynak(standart="MIL-PRF-23377", revizyon="K", madde="")


@pytest.mark.parametrize("madde", ["3.5.1", "4.6.12.3", "3.4", "TABLE I", "TABLE II"])
def test_kaynak_gecerli_madde_bicimleri(madde):
    assert kaynak(madde).madde == madde


@pytest.mark.parametrize("madde", ["madde 3", "3..4", "abc"])
def test_kaynak_gecersiz_madde_reddedilir(madde):
    with pytest.raises(ValidationError):
        kaynak(madde)


def test_kaynak_etiketi_standart_revizyon_ve_madde_icerir():
    assert kaynak("3.5.1").etiket == "MIL-PRF-23377K, 3.5.1"


# --- Sınır -----------------------------------------------------------------------


def test_aralik_siniri_alt_ve_ust_ister():
    with pytest.raises(ValidationError):
        Sinir(tur="aralik", alt=20, birim="s")


def test_aralik_alt_usttan_buyuk_olamaz():
    with pytest.raises(ValidationError):
        Sinir(tur="aralik", alt=30, ust=20, birim="s")


def test_en_az_siniri_yalniz_alt_ister():
    assert Sinir(tur="en_az", alt=4, birim="saat").ust is None
    with pytest.raises(ValidationError):
        Sinir(tur="en_az", ust=4, birim="saat")
    with pytest.raises(ValidationError):
        Sinir(tur="en_az", alt=4, ust=5, birim="saat")


def test_en_cok_siniri_yalniz_ust_ister():
    assert Sinir(tur="en_cok", ust=340, birim="g/L").alt is None
    with pytest.raises(ValidationError):
        Sinir(tur="en_cok", alt=340, birim="g/L")


def test_nitel_sinir_ifade_ister_sayi_almaz():
    assert Sinir(tur="nitel", ifade="No blistering or lifting").ifade
    with pytest.raises(ValidationError):
        Sinir(tur="nitel")
    with pytest.raises(ValidationError):
        Sinir(tur="nitel", ifade="x", alt=1)


def test_sinirlarin_varsayilani_dahil():
    s = Sinir(tur="aralik", alt=20, ust=30, birim="s")
    assert s.alt_dahil and s.ust_dahil


def test_birimsiz_sayisal_sinir_kabul_edilir():
    # pH, oran gibi birimsiz büyüklükler.
    assert Sinir(tur="en_az", alt=7).birim is None


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


def test_test_metodu_maddesi_ayrica_tutulabilir():
    t = ornek_sart(metot_kaynagi=kaynak("4.6.3"))
    assert t.metot_kaynagi.madde == "4.6.3"


# --- Raf ömrü, koşullar, numune -------------------------------------------------


def test_raf_omru_pozitif_sure_ister():
    assert RafOmru(sure=12, birim="ay", kaynak=kaynak("3.7")).sure == 12
    with pytest.raises(ValidationError):
        RafOmru(sure=0, birim="ay", kaynak=kaynak("3.7"))
    with pytest.raises(ValidationError):
        RafOmru(sure=12, birim="hafta_sonu", kaynak=kaynak("3.7"))


def test_kosul_sinir_ya_da_aciklama_ister():
    with pytest.raises(ValidationError):
        Kosul(kategori="depolama", ad="Depolama sıcaklığı", kaynak=kaynak("3.7"))
    k = Kosul(
        kategori="depolama",
        ad="Depolama sıcaklığı",
        sinir=Sinir(tur="aralik", alt=4, ust=38, birim="°C"),
        kaynak=kaynak("3.7"),
    )
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
        kuru_film_kalinligi=Sinir(tur="aralik", alt=0.6, ust=0.9, birim="mil"),
        kurlenme="7 gün, oda sıcaklığında",
        kaynak=kaynak("4.5.2"),
    )
    assert n.kuru_film_kalinligi.ust == 0.9


def test_test_sarti_numune_hazirligina_id_ile_baglanir():
    assert ornek_sart(numune_hazirlama_id="genel_panel").numune_hazirlama_id == "genel_panel"


# --- KabulDokumani ---------------------------------------------------------------


def dokuman(**ek):
    veri = dict(
        standart=StandartBilgisi(
            standart="MIL-PRF-23377", revizyon="K", baslik="Primer coatings: epoxy, high-solids"
        ),
        testler=[ornek_sart()],
    )
    return KabulDokumani(**(veri | ek))


def test_kabul_dokumani_varsayilan_durumu_taslak():
    assert dokuman().durum == "taslak"


def test_test_kimlikleri_benzersiz_olmali():
    with pytest.raises(ValidationError):
        dokuman(testler=[ornek_sart(), ornek_sart()])


def test_test_baska_standardin_maddesine_dayanamaz():
    yabanci = ornek_sart(kaynak=Kaynak(standart="MIL-PRF-85285", revizyon="E", madde="3.5"))
    with pytest.raises(ValidationError):
        dokuman(testler=[yabanci])


def test_bilinmeyen_numune_hazirligina_bagli_test_reddedilir():
    with pytest.raises(ValidationError):
        dokuman(testler=[ornek_sart(numune_hazirlama_id="olmayan")])


def test_kabul_dokumani_json_gidis_donus():
    d = dokuman(
        raf_omru=RafOmru(sure=12, birim="ay", kaynak=kaynak("3.7")),
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
