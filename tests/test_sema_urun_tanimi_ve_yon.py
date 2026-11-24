"""Şema genişlemesinin testleri: ürün tanımı, uygulanabilirlik, sınır yönü, sonuç kaynağı (docs/mimari.md)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from malzeme_kabul.sozlesme.sema import (
    KabulDokumani,
    Kaynak,
    Kosul,
    NumuneHazirlama,
    RafOmru,
    Sinir,
    StandartBilgisi,
    TanimKaydi,
    UrunTanimi,
)
from malzeme_kabul.sozlesme.sema import TestSarti as Sart


def kaynak(madde="1.2.2"):
    return Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde=madde)


def sayisal(**k):
    return Sinir(kriter_turu="sayisal", orijinal_metin="metin", **k)


def urun_tanimi():
    return UrunTanimi(
        tipler=[TanimKaydi(kod="Type I", aciklama="Standard pigments", kaynak=kaynak())],
        siniflar=[
            TanimKaydi(kod="Class C2", aciklama="Strontium chromate", kaynak=kaynak()),
            TanimKaydi(kod="Class N", aciklama="Non-chromate", kaynak=kaynak()),
        ],
    )


def sart(id_="krom", uyg=(), sinir=None, **k):
    return Sart(
        id=id_, test_adi="Chromium content (class N only)", sinir=sinir or sayisal(ust=0.1, birim="%"),
        kaynak=kaynak("3.4"), test_turleri={"kabul"}, uygulanabilirlik=list(uyg), **k,
    )


def dokuman(**k):
    return KabulDokumani(standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"), **k)


# --- Sınır yönü ------------------------------------------------------------------


@pytest.mark.parametrize(
    "sinir, yon",
    [
        (dict(alt=5), "en_az"),
        (dict(ust=340), "en_cok"),
        (dict(alt=15, ust=30), "aralik"),
        (dict(alt=5, ust=5), "tam"),
    ],
)
def test_yon_bos_birakilinca_sinirdan_cikarilir(sinir, yon):
    assert sayisal(**sinir).yonu == yon
    assert sayisal(yon=yon, **sinir).yonu == yon  # açıkça yazılan tutarlıysa kabul edilir


@pytest.mark.parametrize("sinir, yon", [(dict(alt=5), "tam"), (dict(alt=5, ust=5), "en_az"), (dict(ust=3), "aralik")])
def test_tutarsiz_yon_reddedilir(sinir, yon):
    with pytest.raises(ValidationError, match="uyuşmuyor"):
        sayisal(yon=yon, **sinir)


@pytest.mark.parametrize("sinir", [dict(alt=5), dict(alt=5, ust=5)])
def test_yon_belirsiz_her_sayisal_sinirla_yazilabilir(sinir):
    s = sayisal(yon="belirsiz", **sinir)
    assert s.yon_belirsiz and s.yonu == "belirsiz"


def test_sayisal_olmayan_kriter_yon_almaz():
    with pytest.raises(ValidationError, match="yön almaz"):
        Sinir(kriter_turu="metinsel", orijinal_metin="No blistering", yon="belirsiz")
    assert Sinir(kriter_turu="gecti_kaldi", orijinal_metin="Pass").yonu is None


def test_eski_json_yonsuz_okunur():
    s = Sinir.model_validate({"kriter_turu": "sayisal", "alt": 4, "orijinal_metin": "4A min"})
    assert s.yon is None and s.yonu == "en_az" and not s.yon_belirsiz


# --- Sonuç kaynağı -----------------------------------------------------------------


def test_sonuc_kaynagi_varsayilan_coc():
    assert sart().sonuc_kaynagi == "coc"
    assert sart(sonuc_kaynagi="ic_laboratuvar").sonuc_kaynagi == "ic_laboratuvar"
    with pytest.raises(ValidationError):
        sart(sonuc_kaynagi="tedarikci")


# --- Ürün tanımı ve uygulanabilirlik -------------------------------------------------


def test_urun_tanimi_kod_eslesmesi_bosluk_ve_harf_buyuklugune_duyarsiz():
    u = urun_tanimi()
    assert u.kod_tanimli_mi("class  n") and u.kod_tanimli_mi("Type I")
    assert not u.kod_tanimli_mi("Class C1")


def test_urun_tanimi_tekrar_eden_kodu_reddeder():
    with pytest.raises(ValidationError, match="tekrar eden"):
        UrunTanimi(siniflar=[TanimKaydi(kod="Class N", kaynak=kaynak()), TanimKaydi(kod="class n", kaynak=kaynak())])


def test_urun_tanimi_varsa_uygulanabilirlik_tanimli_koda_bakar():
    d = dokuman(urun_tanimi=urun_tanimi(), testler=[sart(uyg=["Class N"])])
    assert d.testler[0].uygulanabilirlik == ["Class N"]
    with pytest.raises(ValidationError, match="Class C1"):
        dokuman(urun_tanimi=urun_tanimi(), testler=[sart(uyg=["Class C1"])])


@pytest.mark.parametrize(
    "alan",
    [
        dict(kosullar=[Kosul(kategori="kullanim", ad="Pot life", aciklama="4 h", kaynak=kaynak("3.6"), uygulanabilirlik=["Type III"])]),
        dict(raf_omurleri=[RafOmru(sure=1, birim="year", kaynak=kaynak("3.10"), uygulanabilirlik=["Type III"])]),
        dict(numune_hazirlama=[NumuneHazirlama(id="panel", kaynak=kaynak("4.6.1"), uygulanabilirlik=["Type III"])]),
    ],
    ids=["kosul", "raf_omru", "numune"],
)
def test_her_sart_turu_uygulanabilirlik_tasir_ve_denetlenir(alan):
    dokuman(**alan)  # ürün tanımı yoksa serbest
    with pytest.raises(ValidationError, match="Type III"):
        dokuman(urun_tanimi=urun_tanimi(), **alan)


def test_urun_tanimi_json_gidis_donus():
    d = dokuman(urun_tanimi=urun_tanimi(), testler=[sart(uyg=["Class N"], sinir=sayisal(alt=5, ust=5, yon="belirsiz"))])
    geri = KabulDokumani.model_validate_json(d.model_dump_json())
    assert geri == d
    assert geri.testler[0].sinir.yon_belirsiz
