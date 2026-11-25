"""Raf ömrü hesabı, uyarı ve ömür uzatma testleri."""

from __future__ import annotations

from datetime import date

import pytest

from malzeme_kabul.hat.raf_omru_raporu import raf_raporu
from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kural.raf_omru import ay_ekle, omur_uzatma_testleri, raf_durumu, raf_omru_sec, sure_ekle
from malzeme_kabul.sozlesme.sema import KabulDokumani, Kaynak, RafOmru, Sinir, StandartBilgisi, TestSarti
from tests.conftest import betik_yukle

KAYNAK = Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde="3.9")


def raf(sure, birim, kap=None, uyg=()):
    return RafOmru(kap_turu=kap, sure=sure, birim=birim, kaynak=KAYNAK, uygulanabilirlik=list(uyg))


def test_(id_, turler, uyg=()):
    return TestSarti(
        id=id_, test_adi=id_.title(), test_turleri=set(turler), kaynak=KAYNAK, uygulanabilirlik=list(uyg),
        sinir=Sinir(kriter_turu="gecti_kaldi", orijinal_metin="shall pass"),
    )


test_.__test__ = False


def dokuman(raflar=(), testler=()):
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        raf_omurleri=list(raflar), testler=list(testler),
    )


@pytest.mark.parametrize(
    "tarih, ay, beklenen",
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2024, 1, 31), 1, date(2024, 2, 29)),
        (date(2026, 11, 15), 2, date(2027, 1, 15)),
        (date(2024, 2, 29), 12, date(2025, 2, 28)),
    ],
)
def test_ay_ekle(tarih, ay, beklenen):
    assert ay_ekle(tarih, ay) == beklenen


@pytest.mark.parametrize(
    "sure, birim, beklenen",
    [
        (1, "year", date(2027, 3, 10)),
        (6, "month", date(2026, 9, 10)),
        (9, "month", date(2026, 12, 10)),
        (90, "day", date(2026, 6, 8)),
        (2, "week", date(2026, 3, 24)),
        (36, "hour", date(2026, 3, 11)),  # 1,5 gün aşağı yuvarlanır
    ],
)
def test_sure_ekle(sure, birim, beklenen):
    assert sure_ekle(date(2026, 3, 10), sure, birim) == beklenen


@pytest.mark.parametrize(
    "bugun, durum, kalan",
    [
        (date(2026, 11, 1), "gecerli", 31),
        (date(2026, 11, 2), "yaklasiyor", 30),
        (date(2026, 12, 2), "yaklasiyor", 0),
        (date(2026, 12, 3), "doldu", -1),
    ],
)
def test_otuz_gun_esigi(bugun, durum, kalan):
    b = raf_durumu(dokuman([raf(1, "year")]), date(2025, 12, 2), bugun)
    assert (b.durum, b.kalan_gun, b.son_kullanma) == (durum, kalan, date(2026, 12, 2))
    assert b.uyari == (durum != "gecerli")


def test_esik_degistirilebilir():
    b = raf_durumu(dokuman([raf(1, "year")]), date(2025, 12, 2), date(2026, 11, 1), uyari_esigi_gun=60)
    assert b.durum == "yaklasiyor"


def test_raf_omru_yoksa_bilinmiyor():
    b = raf_durumu(dokuman(), date(2026, 1, 1), date(2026, 1, 2))
    assert b.durum == "bilinmiyor" and b.son_kullanma is None and not b.uyari


def test_kap_turu_eslesir():
    d = dokuman([raf(1, "year", "metal"), raf(6, "month", "plastik")])
    assert raf_omru_sec(d, "Metal")[0].sure == 1
    assert raf_omru_sec(d, "plastik")[0].sure == 6


def test_kap_turu_bilinmiyorsa_en_kisa_alinir():
    d = dokuman([raf(1, "year", "metal"), raf(6, "month", "plastik")])
    secilen, notlar = raf_omru_sec(d)
    assert secilen.kap_turu == "plastik" and "en kısa" in notlar[0]
    assert "eşleşmedi" in raf_omru_sec(d, "cam")[1][0]


def test_tek_genel_kayit_notsuz_secilir():
    assert raf_omru_sec(dokuman([raf(9, "month")]), "metal") == (raf(9, "month"), [])


def test_uygulanabilirlik_tip_sinifa_gore():
    d = dokuman([raf(1, "year", uyg=["Class N"]), raf(6, "month", "plastik", uyg=["Class C2"])])
    assert raf_omru_sec(d, sinif="C2")[0].sure == 6
    assert raf_omru_sec(d, sinif="N")[0].sure == 1


def test_omur_uzatma_testleri_tip_sinifa_gore():
    d = dokuman(testler=[
        test_("viskozite", {"kabul", "omur_uzatma"}),
        test_("krom", {"omur_uzatma"}, ["Class N"]),
        test_("renk", {"kabul"}),
    ])
    assert [t.id for t in omur_uzatma_testleri(d, sinif="N")] == ["viskozite", "krom"]
    assert [t.id for t in omur_uzatma_testleri(d, sinif="C2")] == ["viskozite"]


# --- depo raporu -----------------------------------------------------------------


@pytest.fixture
def katalog():
    k = Katalog()
    k.dokuman_onayla(dokuman([raf(1, "year", "metal"), raf(6, "month", "plastik")],
                             [test_("viskozite", {"kabul", "omur_uzatma"})]), "mp1")
    k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
    k.tedarikci_onayla("AST-N", "Ted A")
    k.parti_ekle("ESKI", "AST-N", "Ted A", "K", "2025-11-01", kap_turu="metal")   # doldu
    k.parti_ekle("YAKIN", "AST-N", "Ted A", "K", "2026-06-10", kap_turu="plastik")  # 15 gün
    k.parti_ekle("YENI", "AST-N", "Ted A", "K", "2026-11-01", kap_turu="metal")
    k.standart_ekle("MIL-PRF-1", "A")
    k.malzeme_ekle("X-1", "MIL-PRF-1", "A")
    k.tedarikci_onayla("X-1", "Ted A")
    k.parti_ekle("BELGESIZ", "X-1", "Ted A", "A", "2026-01-01")
    yield k
    k.kapat()


def test_rapor_sirali_ve_uyarili(katalog):
    r = raf_raporu(katalog, date(2026, 11, 25))
    assert [s.parti.lot_no for s in r] == ["ESKI", "YAKIN", "YENI", "BELGESIZ"]
    assert [s.raf.durum for s in r] == ["doldu", "yaklasiyor", "gecerli", "bilinmiyor"]
    assert r[1].raf.kalan_gun == 15 and r[1].dokuman_surumu == "MIL-PRF-23377K v1"
    assert [t.id for t in r[0].omur_uzatma_testleri] == ["viskozite"]
    assert r[2].omur_uzatma_testleri == []  # uyarı yoksa listelenmez
    assert "onaylı kabul dokümanı yok" in r[3].raf.notlar[0]


def test_rapor_yalniz_uyari(katalog):
    assert [s.parti.lot_no for s in raf_raporu(katalog, date(2026, 11, 25), yalniz_uyari=True)] == ["ESKI", "YAKIN"]


def test_eski_veritabanina_kap_turu_sutunu_eklenir(tmp_path):
    import sqlite3

    yol = tmp_path / "eski.sqlite"
    b = sqlite3.connect(yol)
    b.execute("CREATE TABLE partiler (lot_no TEXT, malzeme_kodu TEXT, tedarikci TEXT, siparis_revizyonu TEXT,"
              " uretim_tarihi TEXT, durum TEXT, PRIMARY KEY (malzeme_kodu, lot_no))")
    b.commit()
    b.close()
    with Katalog(yol) as k:
        assert "kap_turu" in {s["name"] for s in k.baglanti.execute("PRAGMA table_info(partiler)")}


def test_raf_omru_betigi(tmp_path, capsys):
    db = tmp_path / "k.sqlite"
    betik_yukle("scripts/katalog_kur.py").main(["--db", str(db), "--ornek"])
    capsys.readouterr()
    assert betik_yukle("scripts/raf_omru.py").main(["--db", str(db), "--bugun", "2026-11-25", "--yalniz-uyari"]) == 0
    cikti = capsys.readouterr().out
    assert "AST-001 / A-2512-01: son kullanma 2026-12-10 (15 gün) UYARI: yaklaşıyor" in cikti
    assert "ömür uzatma testleri" in cikti and "B-2606-07" not in cikti
