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


TIRNAKLAR = "'\"‘’“”«»"


def tirnak_icinde(kelime: str, metin: str) -> bool:
    """Not, verilen kap türünü tırnak içinde anıyor mu (ör. 'cam' ya da "cam")?"""
    return any(f"{a}{kelime}{b}" in metin for a in TIRNAKLAR for b in TIRNAKLAR)


# Kap türü bilinmiyor (4b): genel kayıt olsa bile en kısa alınır.


def test_kap_bilinmiyor_genel_ve_daha_kisa_kap_kaydi_varsa_en_kisa_alinir():
    d = dokuman([raf(1, "year"), raf(6, "month", "plastik")])
    secilen, notlar = raf_omru_sec(d)
    assert secilen == raf(6, "month", "plastik")
    assert len(notlar) == 1 and "kap türü bilinmiyor" in notlar[0] and "en kısa" in notlar[0]


def test_kap_bilinmiyor_genel_en_kisaysa_genel_notla_alinir():
    d = dokuman([raf(1, "year", "metal"), raf(6, "month")])
    secilen, notlar = raf_omru_sec(d)
    assert secilen == raf(6, "month")
    assert len(notlar) == 1 and "kap türü bilinmiyor" in notlar[0] and "en kısa" in notlar[0]


# Kap türü verilmiş, eşleşmiyor (3b, 3c).


def test_kap_verilmis_eslesmiyor_tek_genel_varsa_genel_notla_alinir():
    # Genel kayıt daha uzun olsa da kap türü verildiğinde tek genel kayıt alınır.
    d = dokuman([raf(1, "year"), raf(6, "month", "plastik")])
    secilen, notlar = raf_omru_sec(d, "cam")
    assert secilen == raf(1, "year")
    assert len(notlar) == 1 and tirnak_icinde("cam", notlar[0]) and "genel" in notlar[0]


def test_kap_verilmis_eslesmiyor_genel_yoksa_en_kisa_notla_alinir():
    d = dokuman([raf(1, "year", "metal"), raf(6, "month", "plastik")])
    secilen, notlar = raf_omru_sec(d, "cam")
    assert secilen == raf(6, "month", "plastik")
    assert len(notlar) == 1 and "eşleşmedi" in notlar[0] and "en kısa" in notlar[0]


# Tek aday (3a, 3b, 4a).


def test_tek_aday_kap_turu_farkliysa_notla_alinir():
    secilen, notlar = raf_omru_sec(dokuman([raf(1, "year", "metal")]), "plastik")
    assert secilen == raf(1, "year", "metal")
    assert len(notlar) == 1 and tirnak_icinde("plastik", notlar[0]) and "metal" in notlar[0]


def test_tek_genel_kayit_kap_verilince_notla_alinir():
    secilen, notlar = raf_omru_sec(dokuman([raf(9, "month")]), "metal")
    assert secilen == raf(9, "month")
    assert len(notlar) == 1 and tirnak_icinde("metal", notlar[0]) and "genel" in notlar[0]


def test_tek_genel_kayit_kap_bilinmiyorsa_notsuz_alinir():
    assert raf_omru_sec(dokuman([raf(9, "month")])) == (raf(9, "month"), [])


def test_tek_kap_kaydi_kap_bilinmiyorsa_notla_alinir():
    secilen, notlar = raf_omru_sec(dokuman([raf(1, "year", "metal")]))
    assert secilen == raf(1, "year", "metal")
    assert len(notlar) == 1 and notlar[0].strip()


@pytest.mark.parametrize("kap", ["", " ", "  \t "])
def test_bos_kap_turu_bilinmiyor_sayilir(kap):
    # Birden çok kayıt: bilinmeyen kap gibi en kısa alınır, "eşleşmedi" denmez.
    secilen, notlar = raf_omru_sec(dokuman([raf(1, "year"), raf(6, "month", "plastik")]), kap)
    assert secilen == raf(6, "month", "plastik")
    assert len(notlar) == 1 and "kap türü bilinmiyor" in notlar[0] and "eşleşmedi" not in notlar[0]
    # Tek genel kayıt: bilinmeyen kap gibi notsuz alınır.
    assert raf_omru_sec(dokuman([raf(9, "month")]), kap) == (raf(9, "month"), [])


# En kısa: süreler sure_ekle ile tarihe eklenerek karşılaştırılır (birim karışıklığı).


@pytest.mark.parametrize(
    "kayitlar, beklenen",
    [
        ([raf(1, "year", "metal"), raf(400, "day", "plastik")], "metal"),
        ([raf(12, "month", "metal"), raf(360, "day", "plastik")], "plastik"),
        # 6 ay her başlangıçta 181–184 gündür: 180 gün hemen altı, 185 gün hemen üstü.
        ([raf(6, "month", "metal"), raf(180, "day", "plastik")], "plastik"),
        ([raf(6, "month", "metal"), raf(185, "day", "plastik")], "metal"),
        # 52 hafta = 364 gün < 1 yıl; 400 gün > 1 yıl.
        ([raf(1, "year", "metal"), raf(52, "week", "plastik")], "plastik"),
        # 1 hafta = 168 saat: 167 saat (6 gün) hemen altı.
        ([raf(1, "week", "metal"), raf(167, "hour", "plastik")], "plastik"),
    ],
)
def test_en_kisa_birim_cevrilerek_secilir(kayitlar, beklenen):
    assert raf_omru_sec(dokuman(kayitlar))[0].kap_turu == beklenen
    assert raf_omru_sec(dokuman(kayitlar), "cam")[0].kap_turu == beklenen


@pytest.mark.parametrize(
    "kayitlar, beklenen",
    [
        ([raf(12, "month", "metal"), raf(1, "year", "plastik")], "metal"),
        ([raf(1, "year", "plastik"), raf(12, "month", "metal")], "plastik"),
        ([raf(2, "year", "metal"), raf(24, "month", "plastik")], "metal"),
        ([raf(1, "week", "metal"), raf(168, "hour", "plastik")], "metal"),
    ],
)
def test_esit_surede_belge_sirasi_korunur(kayitlar, beklenen):
    assert raf_omru_sec(dokuman(kayitlar))[0].kap_turu == beklenen
    assert raf_omru_sec(dokuman(kayitlar), "cam")[0].kap_turu == beklenen


# En kısa, verilen üretim tarihinden ölçülür (sabit başlangıç tarihinden değil).


@pytest.mark.parametrize("kap", [None, "cam"])
def test_en_kisa_uretim_tarihinden_olculur(kap):
    d = dokuman([raf(1, "month", "metal"), raf(30, "day", "plastik")])
    # 2026-02-01: 1 ay 03-01'de, 30 gün 03-03'te biter.
    assert raf_omru_sec(d, kap, uretim_tarihi=date(2026, 2, 1))[0] == raf(1, "month", "metal")
    # 2026-01-01: 1 ay 02-01'de, 30 gün 01-31'de biter.
    assert raf_omru_sec(d, kap, uretim_tarihi=date(2026, 1, 1))[0] == raf(30, "day", "plastik")


@pytest.mark.parametrize(
    "uretim, gun, beklenen_ilk_sirada, beklenen_ters_sirada",
    [
        # Artık olmayan yıl: 1 yıl = 365 gün.
        (date(2026, 3, 1), 366, "yil", "yil"),       # hemen üstü: 1 yıl kazanır
        (date(2026, 3, 1), 365, "yil", "gun"),       # tam sınır: eşitlik, belge sırası
        (date(2026, 3, 1), 364, "gun", "gun"),       # hemen altı: gün kazanır
        # Artık yıl (29 Şubat aralıkta): 1 yıl = 366 gün.
        (date(2024, 1, 1), 366, "yil", "gun"),       # tam sınır: eşitlik, belge sırası
        (date(2024, 1, 1), 367, "yil", "yil"),
    ],
)
def test_366_gun_ve_1_yil_uretim_tarihine_gore(uretim, gun, beklenen_ilk_sirada, beklenen_ters_sirada):
    yil, gunluk = raf(1, "year", "metal"), raf(gun, "day", "plastik")
    adlar = {"yil": yil, "gun": gunluk}
    for kap in (None, "cam"):
        assert raf_omru_sec(dokuman([yil, gunluk]), kap, uretim_tarihi=uretim)[0] == adlar[beklenen_ilk_sirada]
        assert raf_omru_sec(dokuman([gunluk, yil]), kap, uretim_tarihi=uretim)[0] == adlar[beklenen_ters_sirada]


def test_raf_durumu_uretim_tarihiyle_en_kisayi_secer():
    d = dokuman([raf(1, "month", "metal"), raf(30, "day", "plastik")])
    b = raf_durumu(d, date(2026, 2, 1), date(2026, 2, 10))
    assert b.raf_omru == raf(1, "month", "metal")
    assert b.son_kullanma == date(2026, 3, 1)
    assert b.kalan_gun == 19


# kap_turu "" olan kayıt (şema izin verir; yalnız boşluk da ""ye kırpılır) genel sayılır.


@pytest.mark.parametrize("bos", ["", " "])
def test_sema_bos_kap_turunu_bos_dizgi_olarak_tutar(bos):
    assert raf(1, "year", bos).kap_turu == ""
    # Şemada "" ile None aynı genel kayıttır; ikisi birlikte olamaz.
    with pytest.raises(ValueError, match="tek raf ömrü kaydı"):
        dokuman([raf(1, "year", bos), raf(6, "month")])


@pytest.mark.parametrize("bos", ["", " "])
def test_bos_kap_turlu_kayit_genel_sayilir(bos):
    d = dokuman([raf(1, "year", bos), raf(6, "month", "plastik")])
    secilen, notlar = raf_omru_sec(d, "cam")
    assert secilen == raf(1, "year", bos)
    assert len(notlar) == 1 and tirnak_icinde("cam", notlar[0]) and "genel" in notlar[0]
    assert "en kısa" not in notlar[0]


@pytest.mark.parametrize("bos", ["", " "])
def test_tek_bos_kap_turlu_kayit_kap_bilinmiyorsa_notsuz_alinir(bos):
    assert raf_omru_sec(dokuman([raf(9, "month", bos)])) == (raf(9, "month", bos), [])


def test_sema_iki_genel_kayda_izin_vermez():
    # Kural 3c'deki "birden çok genel kayıt" durumu şemada oluşamaz.
    with pytest.raises(ValueError, match="tek raf ömrü kaydı"):
        dokuman([raf(1, "year"), raf(6, "month")])


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


def test_raf_raporu_kap_turu_bilinmeyen_partide_en_kisa_ve_not():
    with Katalog() as k:
        k.dokuman_onayla(dokuman([raf(1, "year"), raf(6, "month", "plastik")]), "mp1")
        k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
        k.tedarikci_onayla("AST-N", "Ted A")
        k.parti_ekle("KAPSIZ", "AST-N", "Ted A", "K", "2026-03-10")
        (s,) = raf_raporu(k, date(2026, 4, 1))
    assert s.parti.kap_turu in (None, "")
    assert s.raf.son_kullanma == date(2026, 9, 10)  # üretim + 6 ay, genel 1 yıl değil
    assert s.raf.raf_omru == raf(6, "month", "plastik")
    assert any("kap türü bilinmiyor" in n for n in s.raf.notlar)


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


# --- demo onayı (plan adım 8): raf raporu demo işaretini taşır ----------------------------------------


def test_raf_satiri_demo_alani_var():
    import dataclasses

    from malzeme_kabul.hat.raf_omru_raporu import RafSatiri

    assert "demo_onayi" in {a.name for a in dataclasses.fields(RafSatiri)}


def test_raf_raporu_demo_isaretini_tasir():
    with Katalog() as k:
        k.dokuman_onayla(dokuman([raf(1, "year")]), "ornek-veri", demo_onayi=True)  # MIL-PRF-23377K demo
        k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
        gercek = dokuman([raf(1, "year")]).model_copy(update={
            "standart": StandartBilgisi(belge_no="MIL-PRF-81733", revizyon="D")})
        k.dokuman_onayla(gercek, "mp1")
        k.malzeme_ekle("SZD-N", "MIL-PRF-81733", "D", tip="I", sinif="1")
        k.standart_ekle("MIL-PRF-1", "A")
        k.malzeme_ekle("X-1", "MIL-PRF-1", "A")
        for kod in ("AST-N", "SZD-N", "X-1"):
            k.tedarikci_onayla(kod, "Ted A")
        k.parti_ekle("DEMO", "AST-N", "Ted A", "K", "2026-01-01")
        k.parti_ekle("GERCEK", "SZD-N", "Ted A", "D", "2026-02-01")
        k.parti_ekle("BELGESIZ", "X-1", "Ted A", "A", "2026-03-01")
        satirlar = {s.parti.lot_no: s for s in raf_raporu(k, date(2026, 4, 1))}
    assert satirlar["DEMO"].demo_onayi is True and satirlar["DEMO"].dokuman_surumu == "MIL-PRF-23377K v1"
    assert satirlar["GERCEK"].demo_onayi is False
    assert satirlar["BELGESIZ"].demo_onayi is False  # onaylı doküman yoksa demo da değil
