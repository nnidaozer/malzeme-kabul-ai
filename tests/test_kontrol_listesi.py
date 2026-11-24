"""Gold taslağından elle kontrol listesi üreten betiğin testleri."""

from __future__ import annotations

import pytest

from conftest import betik_yukle

from malzeme_kabul.sozlesme.sema import KabulDokumani, Kaynak, Kosul, RafOmru, Sinir, StandartBilgisi
from malzeme_kabul.sozlesme.sema import TestSarti as Sart


@pytest.fixture
def betik():
    return betik_yukle("deney/kontrol_listesi_uret.py")


def kaynak(madde, sayfa):
    return Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde=madde, sayfa=sayfa)


@pytest.fixture
def dokuman():
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        testler=[
            Sart(id="voc", test_adi="VOC solvent content",
                 sinir=Sinir(kriter_turu="sayisal", ust=340, birim="g/L", orijinal_metin="not greater than 340 g/L"),
                 kaynak=kaynak("3.4.2", 6), test_turleri={"kabul", "yeterlilik"}),
            Sart(id="odor", test_adi="Odor | koku",
                 sinir=Sinir(kriter_turu="metinsel", orijinal_metin="The odor shall be characteristic."),
                 kaynak=kaynak("3.6.2", 7), test_turleri={"kabul"}),
        ],
        raf_omurleri=[RafOmru(kap_turu="plastik", sure=6, birim="month", kaynak=kaynak("3.5.3", 6))],
        kosullar=[Kosul(kategori="kullanim", ad="Kap ömrü",
                        sinir=Sinir(kriter_turu="sayisal", ust=4, birim="hour", orijinal_metin="within 4 hours"),
                        kaynak=kaynak("3.11", 9))],
    )


def test_her_satirda_bos_kutu_ad_deger_birim_madde_ve_sayfa(betik, dokuman):
    md = betik.kontrol_listesi(dokuman)
    satir = next(s for s in md.splitlines() if "VOC solvent content" in s)
    hucreler = [h.strip() for h in satir.strip("|").split("|")]
    assert hucreler == ["[ ]", "VOC solvent content", "≤ 340", "g/L", "3.4.2", "6", "sayısal", "kabul, yeterlilik"]


def test_metinsel_kriter_metniyle_birimsiz_yazilir(betik, dokuman):
    satir = next(s for s in betik.kontrol_listesi(dokuman).splitlines() if "koku" in s)
    assert "The odor shall be characteristic." in satir
    assert "Odor \\| koku" in satir


def test_raf_omru_ve_kosullar_da_listelenir(betik, dokuman):
    md = betik.kontrol_listesi(dokuman)
    assert "| [ ] | Raf ömrü (plastik) | 6 | month | 3.5.3 | 6 |" in md
    assert "| [ ] | Kap ömrü | ≤ 4 | hour | 3.11 | 9 |" in md


def test_sayfa_numarasi_yoksa_soru_isareti(betik, dokuman):
    d = dokuman.model_copy(update={"raf_omurleri": [
        RafOmru(sure=1, birim="year", kaynak=Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde="3.5.3"))]})
    assert "| [ ] | Raf ömrü (tümü) | 1 | year | 3.5.3 | ? |" in betik.kontrol_listesi(d)


def test_giris_metni_belgenin_kendi_json_dosyasini_gosterir(betik, dokuman):
    d = dokuman.model_copy(update={"standart": StandartBilgisi(belge_no="MIL-PRF-85285", revizyon="E")})
    md = betik.kontrol_listesi(d)
    assert "`MIL-PRF-85285E.json`" in md
    assert "23377K" not in md.split("## Testler")[0]
