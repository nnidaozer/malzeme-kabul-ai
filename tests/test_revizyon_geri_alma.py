"""`yeni_revizyon_yukle` tek işlemdir (PR #72 regresyonu).

Standart ekleme, malzeme/parti M&P işaretleri ve revizyon olayı aynı işlemde
yazılır. Olay yazılamazsa (fark özeti JSON'a çevrilemez ya da INSERT düşer)
hiçbiri kalmaz: yeni revizyon standardı yok, işaretler eski, olay tablosu boş.
Ardından geçerli veriyle tekrar çağrı tek olay yazar. Dıştaki bir işlemin
içinde çağrılırsa SAVEPOINT olarak katılır: hatada yalnız kendi yazdığını geri
alır, dış işlemin yazdıkları kalır.

Bellek içi katalog kullanılır; data/ altına yazılmaz.
"""

from __future__ import annotations

import sqlite3

import pytest

from malzeme_kabul.hat.revizyon_etkisi import yeni_revizyon_yukle
from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.sozlesme.sema import KabulDokumani, StandartBilgisi

BELGE = "MIL-PRF-23377"


def dok(belge_no=BELGE, rev="J"):
    return KabulDokumani(standart=StandartBilgisi(belge_no=belge_no, revizyon=rev))


@pytest.fixture
def katalog():
    k = Katalog()
    k.dokuman_onayla(dok(rev="J"), "mp1")
    k.malzeme_ekle("AST-J", BELGE, "J", tip="I", sinif="N")
    k.tedarikci_onayla("AST-J", "Ted A")
    k.parti_ekle("L1", "AST-J", "Ted A", "J", "2026-01-01", durum="serbest")
    k.parti_ekle("L2", "AST-J", "Ted A", "J", "2026-02-01", durum="karantina")
    yield k
    k.kapat()


def olay_sayisi(k: Katalog) -> int:
    b = k.baglanti
    if b.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='revizyon_olaylari'").fetchone() is None:
        return 0
    return b.execute("SELECT COUNT(*) FROM revizyon_olaylari").fetchone()[0]


def isaretler(k: Katalog) -> tuple:
    return k.malzeme("AST-J").mp_inceleme, [p.mp_inceleme for p in k.partiler("AST-J")]


def insert_reddeden_tetikleyici(k: Katalog) -> None:
    """Olay tablosunu önceden kurar ve her INSERT'i reddeden bir tetikleyici ekler."""
    k.baglanti.executescript("""
        CREATE TABLE revizyon_olaylari (
            sira INTEGER PRIMARY KEY, belge_no TEXT NOT NULL, yeni_revizyon TEXT NOT NULL,
            zaman TEXT NOT NULL, kullanici TEXT NOT NULL, etkilenen_malzemeler TEXT NOT NULL,
            etkilenen_partiler TEXT NOT NULL, fark_ozeti TEXT
        );
        CREATE TRIGGER olay_reddi BEFORE INSERT ON revizyon_olaylari
        BEGIN SELECT RAISE(ABORT, 'olay yazilamadi'); END;
    """)


def test_fark_ozeti_json_a_cevrilemezse_yeni_revizyon_standardi_eklenmez(katalog):
    with pytest.raises(TypeError):
        yeni_revizyon_yukle(katalog, BELGE, "K", "mp1", fark_ozeti={"x": object()})
    assert katalog.standart_var_mi(BELGE, "K") is False


def test_fark_ozeti_json_a_cevrilemezse_mp_isaretleri_degismez(katalog):
    once = isaretler(katalog)
    with pytest.raises(TypeError):
        yeni_revizyon_yukle(katalog, BELGE, "K", "mp1", fark_ozeti={"x": object()})
    assert isaretler(katalog) == once == (None, [None, None])


def test_fark_ozeti_json_a_cevrilemezse_revizyon_olayi_yazilmaz(katalog):
    with pytest.raises(TypeError):
        yeni_revizyon_yukle(katalog, BELGE, "K", "mp1", fark_ozeti={"x": object()})
    assert olay_sayisi(katalog) == 0
    assert not katalog.baglanti.in_transaction


def test_fark_ozeti_hatasindan_sonra_gecerli_veriyle_tekrar_tek_olay_yazar(katalog):
    with pytest.raises(TypeError):
        yeni_revizyon_yukle(katalog, BELGE, "K", "mp1", fark_ozeti={"x": object()})
    etki = yeni_revizyon_yukle(katalog, BELGE, "K", "mp1", fark_ozeti={"degisen_sart": 1})
    assert etki.etkilenen_malzemeler == ["AST-J"]
    assert olay_sayisi(katalog) == 1
    assert katalog.standart_var_mi(BELGE, "K")
    mal, partiler = isaretler(katalog)
    assert mal and all(partiler)


def test_olay_insert_hatasinda_standart_isaret_ve_olay_geri_alinir(katalog):
    insert_reddeden_tetikleyici(katalog)
    once = isaretler(katalog)
    with pytest.raises(sqlite3.DatabaseError, match="olay yazilamadi"):
        yeni_revizyon_yukle(katalog, BELGE, "K", "mp1", fark_ozeti={"degisen_sart": 1})
    assert katalog.standart_var_mi(BELGE, "K") is False
    assert isaretler(katalog) == once
    assert olay_sayisi(katalog) == 0


def test_olay_insert_hatasi_giderilince_tekrar_tek_olay_yazar(katalog):
    insert_reddeden_tetikleyici(katalog)
    with pytest.raises(sqlite3.DatabaseError):
        yeni_revizyon_yukle(katalog, BELGE, "K", "mp1")
    katalog.baglanti.execute("DROP TRIGGER olay_reddi")
    yeni_revizyon_yukle(katalog, BELGE, "K", "mp1")
    assert olay_sayisi(katalog) == 1
    assert katalog.standart_var_mi(BELGE, "K")


def test_dis_islem_icinde_hata_yalniz_kendi_yazdigini_geri_alir(katalog):
    with katalog.islem():
        katalog.malzeme_ekle("DIS-1", BELGE, "J")  # dış işlemin yazdığı
        with pytest.raises(TypeError):
            yeni_revizyon_yukle(katalog, BELGE, "K", "mp1", fark_ozeti={"x": object()})
        assert katalog.baglanti.in_transaction  # dış işlem bitmedi
    assert katalog.malzeme("DIS-1").kod == "DIS-1"
    assert katalog.standart_var_mi(BELGE, "K") is False
    assert katalog.malzeme("AST-J").mp_inceleme is None
    assert katalog.malzeme("DIS-1").mp_inceleme is None
    assert olay_sayisi(katalog) == 0


def test_dis_islem_icinde_basarili_cagri_dis_islemi_bitirmez_ve_geri_alinirsa_iz_kalmaz(katalog):
    class DisHata(Exception):
        pass

    with pytest.raises(DisHata):
        with katalog.islem():
            yeni_revizyon_yukle(katalog, BELGE, "K", "mp1")
            assert katalog.baglanti.in_transaction
            raise DisHata
    assert katalog.standart_var_mi(BELGE, "K") is False
    assert katalog.malzeme("AST-J").mp_inceleme is None
    assert olay_sayisi(katalog) == 0
