"""Revizyon etkisi: yeni revizyonda etkilenen malzeme ve partilerin işaretlenmesi."""

from __future__ import annotations

import pytest

from malzeme_kabul.hat.revizyon_etkisi import (
    MP_ISARETI,
    daha_eski_mi,
    mp_bekleyenler,
    mp_incelemesini_kapat,
    yeni_revizyon_yukle,
)
from malzeme_kabul.katalog.veritabani import Katalog, KatalogHatasi
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.sozlesme.sema import KabulDokumani, StandartBilgisi
from tests.conftest import KOK, betik_yukle


def dok(belge_no="MIL-PRF-23377", rev="J"):
    return KabulDokumani(standart=StandartBilgisi(belge_no=belge_no, revizyon=rev))


@pytest.fixture
def katalog():
    k = Katalog()
    k.dokuman_onayla(dok(rev="J"), "mp1")
    k.dokuman_onayla(dok("MIL-PRF-85285", "E"), "mp1")
    k.malzeme_ekle("AST-J", "MIL-PRF-23377", "J", tip="I", sinif="N")
    k.malzeme_ekle("PUB", "MIL-PRF-85285", "E")
    for kod in ("AST-J", "PUB"):
        k.tedarikci_onayla(kod, "Ted A")
    k.parti_ekle("L1", "AST-J", "Ted A", "J", "2026-01-01", durum="serbest")
    k.parti_ekle("L2", "AST-J", "Ted A", "J", "2026-02-01", durum="karantina")
    k.parti_ekle("P1", "PUB", "Ted A", "E", "2026-01-01")
    yield k
    k.kapat()


@pytest.mark.parametrize("eski, yeni, beklenen", [("J", "K", True), ("K", "K", False), ("K", "J", False), ("Z", "AA", True)])
def test_revizyon_sirasi(eski, yeni, beklenen):
    assert daha_eski_mi(eski, yeni) is beklenen


def test_yeni_revizyon_etkilenenleri_isaretler(katalog):
    etki = yeni_revizyon_yukle(katalog, "MIL-PRF-23377", "K", "mp1", fark_ozeti={"degisen_sart": 3})
    assert etki.etkilenen_malzemeler == ["AST-J"]
    assert etki.etkilenen_partiler == ["AST-J/L1", "AST-J/L2"]
    m = katalog.malzeme("AST-J")
    assert m.mp_inceleme.startswith(MP_ISARETI) and "MIL-PRF-23377K" in m.mp_inceleme
    assert all(p.mp_inceleme for p in katalog.partiler("AST-J"))
    assert katalog.malzeme("PUB").mp_inceleme is None and katalog.partiler("PUB")[0].mp_inceleme is None
    assert katalog.standart_var_mi("MIL-PRF-23377", "K")
    olay = katalog.baglanti.execute("SELECT * FROM revizyon_olaylari").fetchone()
    assert olay["yeni_revizyon"] == "K" and '"degisen_sart": 3' in olay["fark_ozeti"]


def test_isaret_kilitlemez_parti_durumu_degismez(katalog):
    yeni_revizyon_yukle(katalog, "MIL-PRF-23377", "K", "mp1")
    assert [p.durum for p in katalog.partiler("AST-J")] == ["serbest", "karantina"]
    assert katalog.gecerli_dokuman("AST-J").etiket == "MIL-PRF-23377J v1"  # karar eski revizyonla sürer


def test_eski_ya_da_ayni_revizyon_isaretlemez(katalog):
    assert yeni_revizyon_yukle(katalog, "MIL-PRF-23377", "J", "mp1").etkilenen_malzemeler == []
    assert yeni_revizyon_yukle(katalog, "MIL-PRF-23377", "H", "mp1").etkilenen_malzemeler == []
    assert mp_bekleyenler(katalog) == []


def test_gerek_yok_ile_kapatma(katalog):
    d = DenetimKaydi(katalog.baglanti)
    yeni_revizyon_yukle(katalog, "MIL-PRF-23377", "K", "mp1")
    assert mp_bekleyenler(katalog) == ["AST-J"]
    kayit = mp_incelemesini_kapat(katalog, d, "AST-J", "mp1", "gerek_yok", "fark krom şartını etkilemiyor")
    assert kayit.tur == "onay" and kayit.veri["karar"] == "gerek_yok"
    assert mp_bekleyenler(katalog) == [] and katalog.malzeme("AST-J").revizyon == "J"
    assert all(p.mp_inceleme is None for p in katalog.partiler("AST-J"))


def test_yeni_revizyona_gecis_onayli_dokuman_ister(katalog):
    d = DenetimKaydi(katalog.baglanti)
    yeni_revizyon_yukle(katalog, "MIL-PRF-23377", "K", "mp1")
    with pytest.raises(KatalogHatasi, match="onaylı kabul dokümanı yok"):
        mp_incelemesini_kapat(katalog, d, "AST-J", "mp1", "yeni_revizyona_gec", yeni_revizyon="K")
    assert mp_bekleyenler(katalog) == ["AST-J"]
    katalog.dokuman_onayla(dok(rev="K"), "mp1")
    kayit = mp_incelemesini_kapat(katalog, d, "AST-J", "mp1", "yeni_revizyona_gec", yeni_revizyon="K")
    assert katalog.malzeme("AST-J").revizyon == "K" and kayit.dokuman_surumu == "MIL-PRF-23377K v1"
    assert d.zinciri_dogrula().gecerli


def test_kapatma_hatalari(katalog):
    d = DenetimKaydi(katalog.baglanti)
    with pytest.raises(KatalogHatasi, match="bekleyen M&P incelemesi yok"):
        mp_incelemesini_kapat(katalog, d, "AST-J", "mp1", "gerek_yok")
    yeni_revizyon_yukle(katalog, "MIL-PRF-23377", "K", "mp1")
    with pytest.raises(KatalogHatasi, match="revizyon harfi gerekli"):
        mp_incelemesini_kapat(katalog, d, "AST-J", "mp1", "yeni_revizyona_gec")
    with pytest.raises(KatalogHatasi, match="bilinmeyen karar"):
        mp_incelemesini_kapat(katalog, d, "AST-J", "mp1", "sil")
    with pytest.raises(KatalogHatasi):
        yeni_revizyon_yukle(katalog, "MIL-PRF-23377", "L", " ")


def test_revizyon_yukle_betigi(tmp_path, capsys):
    db = tmp_path / "k.sqlite"
    betik_yukle("scripts/katalog_kur.py").main(["--db", str(db), "--ornek"])
    capsys.readouterr()
    fark = KOK / "data/cikti/MIL-PRF-23377_J-K_revizyon_farklari.json"
    assert betik_yukle("scripts/revizyon_yukle.py").main(
        ["--db", str(db), "--belge-no", "MIL-PRF-23377", "--revizyon", "L", "--fark", str(fark)]) == 0
    cikti = capsys.readouterr().out
    assert "M&P incelemesi bekleyen malzemeler: AST-001, AST-002" in cikti
    assert "SZD-001" not in cikti
