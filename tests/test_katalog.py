"""SQLite kataloğunun testleri (docs/mimari.md madde 2 ve 3)."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from malzeme_kabul.katalog.ornek_veri import ornek_yukle
from malzeme_kabul.katalog.veritabani import Katalog, KatalogHatasi, icerik_ozeti
from malzeme_kabul.sozlesme.sema import KabulDokumani, Kaynak, Sinir, StandartBilgisi, TestSarti
from tests.conftest import KOK, betik_yukle


def dokuman(revizyon: str = "K", ust: float = 340) -> KabulDokumani:
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon=revizyon),
        testler=[
            TestSarti(
                id="voc", test_adi="VOC content",
                sinir=Sinir(kriter_turu="sayisal", ust=ust, birim="g/L", orijinal_metin=f"{ust} g/L max"),
                kaynak=Kaynak(belge_no="MIL-PRF-23377", revizyon=revizyon, madde="3.5.1"),
                test_turleri={"kabul"},
            )
        ],
    )


@pytest.fixture
def katalog():
    k = Katalog(":memory:")
    k.dokuman_onayla(dokuman(), "mp1")
    k.malzeme_ekle("AST-001", "MIL-PRF-23377", "K", tip="I", sinif="N")
    k.tedarikci_onayla("AST-001", "Ted A")
    yield k
    k.kapat()


def test_surumler_birden_baslar_ve_artar(katalog):
    v2 = katalog.dokuman_onayla(dokuman(ust=330), "mp2", not_="VOC düzeltildi")
    assert v2.surum == 2 and v2.etiket == "MIL-PRF-23377K v2"
    assert [s.surum for s in katalog.dokuman_surumleri("MIL-PRF-23377", "K")] == [1, 2]
    assert katalog.dokuman_surumu("MIL-PRF-23377", "K", 1).dokuman.testler[0].sinir.ust == 340


def test_onaylanan_surum_durumu_onaylandi(katalog):
    assert katalog.gecerli_dokuman("AST-001").dokuman.durum == "onaylandi"


def test_gecerli_dokuman_en_son_surum(katalog):
    katalog.dokuman_onayla(dokuman(ust=330), "mp2")
    g = katalog.gecerli_dokuman("AST-001")
    assert g.surum == 2 and g.onaylayan == "mp2"


def test_surum_guncellenemez_ve_silinemez(katalog):
    with pytest.raises(sqlite3.IntegrityError, match="değiştirilemez"):
        katalog.baglanti.execute("UPDATE dokuman_surumleri SET onaylayan = 'x'")
    with pytest.raises(sqlite3.IntegrityError, match="silinemez"):
        katalog.baglanti.execute("DELETE FROM dokuman_surumleri")


def test_kurcalanmis_icerik_okunurken_yakalanir(katalog):
    b = katalog.baglanti
    b.execute("DROP TRIGGER dokuman_surumu_degistirilemez")
    b.execute("UPDATE dokuman_surumleri SET icerik = replace(icerik, '340', '999')")
    with pytest.raises(KatalogHatasi, match="kurcalanmış"):
        katalog.gecerli_dokuman("AST-001")


def test_ozet_icerigin_sha256_si(katalog):
    s = katalog.gecerli_dokuman("AST-001")
    assert s.ozet == icerik_ozeti(s.dokuman.model_dump_json()) and len(s.ozet) == 64


def test_onayli_surum_yoksa_hata():
    with Katalog() as k:
        k.standart_ekle("MIL-PRF-23377", "J")
        k.malzeme_ekle("AST-009", "MIL-PRF-23377", "J")
        with pytest.raises(KatalogHatasi, match="onaylı kabul dokümanı yok"):
            k.gecerli_dokuman("AST-009")


def test_malzeme_standarti_once_eklenmeli():
    with Katalog() as k, pytest.raises(KatalogHatasi, match="önce standart"):
        k.malzeme_ekle("X", "MIL-PRF-1", "A")


def test_malzeme_kodu_tekil(katalog):
    with pytest.raises(KatalogHatasi, match="zaten var"):
        katalog.malzeme_ekle("AST-001", "MIL-PRF-23377", "K")


def test_bilinmeyen_malzeme(katalog):
    with pytest.raises(KatalogHatasi, match="bilinmeyen malzeme"):
        katalog.malzeme("YOK")


def test_malzeme_bilgisi(katalog):
    m = katalog.malzeme("AST-001")
    assert (m.tip, m.sinif, m.standart_etiketi) == ("I", "N", "MIL-PRF-23377K")
    assert [x.kod for x in katalog.malzemeler()] == ["AST-001"]


def test_onayli_tedarikci_listesi(katalog):
    katalog.tedarikci_onayla("AST-001", "Ted B")
    katalog.tedarikci_onayla("AST-001", "Ted B")  # tekrar zararsız
    assert katalog.onayli_tedarikciler("AST-001") == ["Ted A", "Ted B"]


def test_parti_eklenir_varsayilan_bekliyor(katalog):
    p = katalog.parti_ekle("L1", "AST-001", "Ted A", "K", "2026-01-15")
    assert p.durum == "bekliyor" and p.uretim_tarihi == date(2026, 1, 15)
    assert katalog.partiler() == [p] and katalog.partiler("AST-001") == [p]


def test_parti_onaysiz_tedarikciden_kaydedilemez(katalog):
    with pytest.raises(KatalogHatasi, match="onaylı tedarikçi değil"):
        katalog.parti_ekle("L1", "AST-001", "Ted Z", "K", "2026-01-15")


@pytest.mark.parametrize("durum", ["serbest", "karantina", "bekliyor"])
def test_parti_durumlari(katalog, durum):
    katalog.parti_ekle("L1", "AST-001", "Ted A", "K", date(2026, 1, 15))
    assert katalog.parti_durumu_ata("AST-001", "L1", durum, kaynak="insan").durum == durum


def test_gecersiz_parti_durumu(katalog):
    with pytest.raises(KatalogHatasi, match="geçersiz parti durumu"):
        katalog.parti_ekle("L1", "AST-001", "Ted A", "K", "2026-01-15", durum="kabul")
    katalog.parti_ekle("L1", "AST-001", "Ted A", "K", "2026-01-15")
    with pytest.raises(KatalogHatasi, match="geçersiz parti durumu"):
        katalog.parti_durumu_ata("AST-001", "L1", "red", kaynak="insan")


def test_veritabani_da_gecersiz_durumu_reddeder(katalog):
    katalog.parti_ekle("L1", "AST-001", "Ted A", "K", "2026-01-15")
    with pytest.raises(sqlite3.IntegrityError):
        katalog.baglanti.execute("UPDATE partiler SET durum = 'red'")


def test_parti_tekil_ve_tarih_bicimi(katalog):
    katalog.parti_ekle("L1", "AST-001", "Ted A", "K", "2026-01-15")
    with pytest.raises(KatalogHatasi, match="zaten var"):
        katalog.parti_ekle("L1", "AST-001", "Ted A", "K", "2026-01-15")
    with pytest.raises(KatalogHatasi, match="YYYY-AA-GG"):
        katalog.parti_ekle("L2", "AST-001", "Ted A", "K", "15.01.2026")


def test_bos_alanlar_reddedilir(katalog):
    with pytest.raises(KatalogHatasi):
        katalog.dokuman_onayla(dokuman(), " ")
    with pytest.raises(KatalogHatasi):
        katalog.tedarikci_ekle("")
    with pytest.raises(KatalogHatasi):
        katalog.parti_ekle("L1", "AST-001", "Ted A", " ", "2026-01-15")


def test_dosyada_kalici(tmp_path):
    yol = tmp_path / "alt" / "katalog.sqlite"
    with Katalog(yol) as k:
        k.dokuman_onayla(dokuman(), "mp1")
    with Katalog(yol) as k:
        assert len(k.dokuman_surumleri("MIL-PRF-23377", "K")) == 1


# --- örnek veri ---------------------------------------------------------------


def test_ornek_veri_yuklenir_ve_tekrar_yuklenince_cogalmaz():
    with Katalog() as k:
        ozet = ornek_yukle(k, KOK / "data/ornek/katalog.json", KOK)
        assert ozet.dokuman_surumleri == ["MIL-PRF-23377K v1", "MIL-PRF-81733D v1", "MIL-PRF-85285E v1"]
        kodlar = {m.kod: m for m in k.malzemeler()}
        assert {"AST-001", "AST-002", "SZD-001", "PUB-001"} <= set(kodlar)
        assert kodlar["AST-001"].standart_etiketi == "MIL-PRF-23377K"
        assert k.gecerli_dokuman("SZD-001").dokuman.standart.revizyon == "D"
        assert k.gecerli_dokuman("PUB-001").dokuman.standart.belge_no == "MIL-PRF-85285"
        assert len(k.partiler()) == 5
        ikinci = ornek_yukle(k, KOK / "data/ornek/katalog.json", KOK)
        assert ikinci.dokuman_surumleri == ikinci.malzemeler == ikinci.partiler == []
        assert len(k.dokuman_surumleri("MIL-PRF-23377", "K")) == 1


def test_ornek_veri_gold_klasorlerine_dayanmaz():
    import json

    veri = json.loads((KOK / "data/ornek/katalog.json").read_text(encoding="utf-8"))
    assert not [d for d in veri["dokumanlar"] if d.startswith("data/gold")]


def test_katalog_kur_betigi(tmp_path, capsys):
    betik = betik_yukle("scripts/katalog_kur.py")
    db = tmp_path / "k.sqlite"
    assert betik.main(["--db", str(db), "--ornek"]) == 0
    cikti = capsys.readouterr().out
    assert "AST-001: MIL-PRF-23377K Type I Class N (v1)" in cikti
    assert Path(db).is_file()
