"""SQLite kataloğunun testleri (docs/mimari.md madde 2 ve 3)."""

from __future__ import annotations

import dataclasses
import inspect
import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from malzeme_kabul.arayuz import ekran_verisi as ev
from malzeme_kabul.hat import katalog_karari
from malzeme_kabul.katalog import veritabani
from malzeme_kabul.katalog.ornek_veri import ornek_yukle
from malzeme_kabul.katalog.veritabani import DokumanSurumu, Katalog, KatalogHatasi, icerik_ozeti
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
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
    # Örnek veri demo onaylıdır; özet satırı bunu söyler (demo onayı planı adım 7).
    assert "AST-001: MIL-PRF-23377K Type I Class N (v1, demo onayı)" in cikti
    assert Path(db).is_file()


# --- demo onayı (plan adım 5): şema, Katalog.dokuman_onayla ve sürüm alanı ----------------------
#
# Proje sahibinin isteği: "Örnek kabul dokümanları onaylı sayılabilir, ama ekranda ve
# veritabanında 'demo onayı' olarak işaretlensin."

ORNEK = "ornek-veri"  # veritabani.ORNEK_ONAYLAYAN değeri; testler sabitin kendisini ayrıca denetler


def _surum_sayisi(k: Katalog, revizyon: str = "K") -> int:
    return len(k.dokuman_surumleri("MIL-PRF-23377", revizyon))


def _ham_surum_ekle(b: sqlite3.Connection, revizyon: str, onaylayan: str, surum: int = 1, **demo) -> None:
    """Python katmanını atlayıp dokuman_surumleri'ne doğrudan satır ekler (şema kısıtı testleri için).

    `demo` boşsa demo_onayi sütunu INSERT'te hiç anılmaz (varsayılan değer / eski şema);
    `demo_onayi=...` verilirse o değer yazılır.
    """
    icerik = dokuman(revizyon).model_copy(update={"durum": "onaylandi"}).model_dump_json()
    sutunlar = ["belge_no", "revizyon", "surum", "icerik", "ozet", "onaylayan", "onay_zamani", "not_", *demo]
    degerler = ["MIL-PRF-23377", revizyon, surum, icerik, icerik_ozeti(icerik), onaylayan,
                "2026-01-01T00:00:00+00:00", None, *demo.values()]
    b.execute(
        f"INSERT INTO dokuman_surumleri ({', '.join(sutunlar)}) VALUES ({', '.join('?' * len(sutunlar))})", degerler
    )


def test_ornek_onaylayan_sabiti_veritabani_modulunde_tanimli():
    assert veritabani.ORNEK_ONAYLAYAN == "ornek-veri"


def test_yeni_surum_varsayilan_demo_degil(katalog):
    s = katalog.gecerli_dokuman("AST-001")
    assert s.demo_onayi is False
    assert katalog.baglanti.execute("SELECT demo_onayi FROM dokuman_surumleri").fetchall()[0][0] == 0


def test_dokuman_surumu_demo_alani_sonda_ve_varsayilani_false():
    alanlar = dataclasses.fields(DokumanSurumu)
    assert alanlar[-1].name == "demo_onayi" and alanlar[-1].default is False


def test_ornek_onaylayan_demo_onayiyla_surum_yazar(katalog):
    s = katalog.dokuman_onayla(dokuman(ust=330), ORNEK, demo_onayi=True)
    assert (s.surum, s.onaylayan, s.demo_onayi) == (2, ORNEK, True)
    assert katalog.baglanti.execute(
        "SELECT demo_onayi FROM dokuman_surumleri WHERE surum = 2").fetchone()[0] == 1


@pytest.mark.parametrize(
    "onaylayan, demo",
    [
        ("mp1", True),        # demo işareti gerçek kullanıcıyla verilemez
        (ORNEK, False),       # ornek-veri demo işaretsiz onay veremez
        ("ORNEK-VERI", True),  # yalnız tam ORNEK_ONAYLAYAN demo verebilir
        ("ornek-veri ", True),
    ],
)
def test_demo_onayi_yalniz_ornek_onaylayanla_verilir(katalog, onaylayan, demo):
    with pytest.raises(KatalogHatasi):
        katalog.dokuman_onayla(dokuman(ust=330), onaylayan, demo_onayi=demo)
    assert _surum_sayisi(katalog) == 1  # hiçbir sürüm yazılmaz


def test_ornek_onaylayan_varsayilan_demo_parametresiyle_reddedilir(katalog):
    # demo_onayi verilmezse False'tur; ornek-veri ile bu bir gerçek onay gibi görünürdü.
    with pytest.raises(KatalogHatasi):
        katalog.dokuman_onayla(dokuman(ust=330), ORNEK)
    assert _surum_sayisi(katalog) == 1


def test_demo_onayi_yalniz_anahtar_kelimeyle_verilir():
    p = inspect.signature(Katalog.dokuman_onayla).parameters
    assert p["demo_onayi"].kind is inspect.Parameter.KEYWORD_ONLY and p["demo_onayi"].default is False


def test_demo_onayi_sutunu_not_null_ve_check(katalog):
    sutun = {s["name"]: s for s in katalog.baglanti.execute("PRAGMA table_info(dokuman_surumleri)")}["demo_onayi"]
    assert sutun["type"].upper() == "INTEGER" and sutun["notnull"] == 1 and sutun["dflt_value"] == "0"
    b = katalog.baglanti
    katalog.standart_ekle("MIL-PRF-23377", "J")
    for gecersiz in (None, 2, -1, "evet"):
        with pytest.raises(sqlite3.IntegrityError):
            _ham_surum_ekle(b, "J", ORNEK, demo_onayi=gecersiz)
    _ham_surum_ekle(b, "J", "mp1")  # sütun anılmazsa varsayılan 0
    _ham_surum_ekle(b, "J", ORNEK, surum=2, demo_onayi=1)
    assert [s.demo_onayi for s in katalog.dokuman_surumleri("MIL-PRF-23377", "J")] == [False, True]


def test_demo_onayi_guncellenemez(katalog):
    katalog.dokuman_onayla(dokuman(ust=330), ORNEK, demo_onayi=True)
    for sql in ("UPDATE dokuman_surumleri SET demo_onayi = 1 WHERE surum = 1",
                "UPDATE dokuman_surumleri SET demo_onayi = 0 WHERE surum = 2"):
        with pytest.raises(sqlite3.IntegrityError, match="değiştirilemez"):
            katalog.baglanti.execute(sql)
    assert [s.demo_onayi for s in katalog.dokuman_surumleri("MIL-PRF-23377", "K")] == [False, True]


@pytest.mark.parametrize(
    "fonksiyon",
    [Katalog.taslagi_onayla, katalog_karari.dokuman_onayla, ev.taslak_onayla],
    ids=["Katalog.taslagi_onayla", "katalog_karari.dokuman_onayla", "ekran_verisi.taslak_onayla"],
)
def test_normal_onay_yollari_demo_parametresi_almaz(fonksiyon):
    parametreler = inspect.signature(fonksiyon).parameters
    assert "demo_onayi" not in parametreler
    assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parametreler.values())


def test_taslak_onayi_ornek_onaylayanla_verilemez(katalog):
    t = katalog.taslak_kaydet(dokuman(ust=330), "mp1")
    with pytest.raises(KatalogHatasi):
        katalog.taslagi_onayla(t.id, ORNEK)
    assert _surum_sayisi(katalog) == 1 and katalog.taslak(t.id).durum == "taslak"


def test_denetimli_onay_ornek_onaylayanla_verilemez(katalog):
    defter = DenetimKaydi(katalog.baglanti)
    with pytest.raises(KatalogHatasi):
        katalog_karari.dokuman_onayla(katalog, defter, dokuman(ust=330), ORNEK)
    assert _surum_sayisi(katalog) == 1 and defter.kayitlar("onay") == []


def test_gecerli_dokuman_demo_alanini_tasir(katalog):
    katalog.dokuman_onayla(dokuman(ust=330), ORNEK, demo_onayi=True)
    assert katalog.gecerli_dokuman("AST-001").demo_onayi is True
    assert katalog.dokuman_surumu("MIL-PRF-23377", "K", 1).demo_onayi is False
    assert [s.demo_onayi for s in katalog.dokuman_surumleri("MIL-PRF-23377", "K")] == [False, True]


def test_demo_onayi_dosyada_kalici(tmp_path):
    yol = tmp_path / "k.sqlite"
    with Katalog(yol) as k:
        k.dokuman_onayla(dokuman(), ORNEK, demo_onayi=True)
    with Katalog(yol) as k:
        assert k.dokuman_surumu("MIL-PRF-23377", "K", 1).demo_onayi is True


# --- demo onayı göçü (plan adım 6): demo_onayi sütunu olmayan eski veritabanı ----------------------

_TETIKLEYICI = "dokuman_surumu_degistirilemez"
_BOZUCU = (
    "CREATE TRIGGER test_goc_bozucu BEFORE UPDATE ON dokuman_surumleri "
    "BEGIN SELECT RAISE(ABORT, 'test: dokuman_surumleri UPDATE düşürüldü'); END;"
)


def _sema(yol) -> tuple[dict[str, tuple], dict[str, str]]:
    """(dokuman_surumleri sütunları {ad: (tür, notnull, varsayılan)}, tetikleyiciler {ad: sql})."""
    b = sqlite3.connect(yol)
    try:
        sutunlar = {s[1]: (s[2].upper(), s[3], s[4]) for s in b.execute("PRAGMA table_info(dokuman_surumleri)")}
        tetik = dict(b.execute("SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'dokuman_surumleri'"))
        return sutunlar, tetik
    finally:
        b.close()


def _ham(yol, *sqller: str) -> None:
    b = sqlite3.connect(yol)
    try:
        for sql in sqller:
            b.execute(sql)
        b.commit()
    finally:
        b.close()


@pytest.fixture
def eski_demo_katalog_yolu(tmp_path):
    """demo_onayi sütunundan önceki şemada katalog: K v1 (mp1, gerçek) ve J v1 (ornek-veri).

    Katalog bugünkü kodla kurulur; demo_onayi sütunu varsa düşürülerek eski şema elde edilir
    (tests/test_karar_guvenligi.py durum_kaynagi göçü gibi). ornek-veri satırı eski şemaya
    doğrudan yazılır, çünkü eski kod onu işaretsiz yazıyordu.
    """
    yol = tmp_path / "eski_katalog.sqlite"
    k = Katalog(yol)
    k.dokuman_onayla(dokuman(), "mp1")
    k.malzeme_ekle("AST-001", "MIL-PRF-23377", "K", tip="I", sinif="N")
    k.standart_ekle("MIL-PRF-23377", "J")
    k.malzeme_ekle("AST-J", "MIL-PRF-23377", "J", tip="I", sinif="N")
    k.kapat()
    if "demo_onayi" in _sema(yol)[0]:
        _ham(yol, "ALTER TABLE dokuman_surumleri DROP COLUMN demo_onayi")
    b = sqlite3.connect(yol)
    _ham_surum_ekle(b, "J", ORNEK)
    b.commit()
    b.close()
    sutunlar, tetik = _sema(yol)
    assert "demo_onayi" not in sutunlar and _TETIKLEYICI in tetik
    return yol


def test_eski_veritabanina_demo_sutunu_eklenir_ve_ornek_satirlar_isaretlenir(eski_demo_katalog_yolu, tmp_path):
    with Katalog(eski_demo_katalog_yolu) as k:
        assert k.gecerli_dokuman("AST-J").demo_onayi is True
        assert k.gecerli_dokuman("AST-001").demo_onayi is False
        with pytest.raises(sqlite3.IntegrityError, match="değiştirilemez"):
            k.baglanti.execute("UPDATE dokuman_surumleri SET demo_onayi = 0")
    # Sütun tanımı ve tetikleyici yeni kurulan veritabanıyla aynı.
    yeni = tmp_path / "yeni.sqlite"
    Katalog(yeni).kapat()
    goc_sutun, goc_tetik = _sema(eski_demo_katalog_yolu)
    yeni_sutun, yeni_tetik = _sema(yeni)
    assert goc_sutun["demo_onayi"] == yeni_sutun["demo_onayi"] == ("INTEGER", 1, "0")
    assert goc_tetik[_TETIKLEYICI] == yeni_tetik[_TETIKLEYICI]


def test_eski_veritabaninda_goc_sonrasi_check_kisiti_calisir(eski_demo_katalog_yolu):
    with Katalog(eski_demo_katalog_yolu) as k:
        with pytest.raises(sqlite3.IntegrityError):
            _ham_surum_ekle(k.baglanti, "J", ORNEK, surum=2, demo_onayi=2)


def test_demo_gocu_duserse_sutun_ve_tetikleyici_geri_alinir(eski_demo_katalog_yolu):
    # Göçün UPDATE adımı düşerse ROLLBACK: sütun eklenmemiş, değiştirilemezlik tetikleyicisi yerinde.
    _ham(eski_demo_katalog_yolu, _BOZUCU)
    with pytest.raises(Exception):  # hata yutulmaz; türü uygulamaya kalır
        Katalog(eski_demo_katalog_yolu)
    sutunlar, tetik = _sema(eski_demo_katalog_yolu)
    assert "demo_onayi" not in sutunlar
    assert _TETIKLEYICI in tetik
    _ham(eski_demo_katalog_yolu, "DROP TRIGGER test_goc_bozucu")
    with pytest.raises(sqlite3.IntegrityError, match="değiştirilemez"):
        _ham(eski_demo_katalog_yolu, "UPDATE dokuman_surumleri SET onaylayan = 'x'")


def test_demo_gocu_dustukten_sonra_sonraki_acilista_yeniden_denenir(eski_demo_katalog_yolu):
    _ham(eski_demo_katalog_yolu, _BOZUCU)
    with pytest.raises(Exception):
        Katalog(eski_demo_katalog_yolu)
    _ham(eski_demo_katalog_yolu, "DROP TRIGGER test_goc_bozucu")
    with Katalog(eski_demo_katalog_yolu) as k:
        assert k.gecerli_dokuman("AST-J").demo_onayi is True
        assert k.gecerli_dokuman("AST-001").demo_onayi is False


def test_demo_gocu_ikinci_acilista_tekrarlanmaz(eski_demo_katalog_yolu):
    Katalog(eski_demo_katalog_yolu).kapat()  # ilk açılış göçü yapar
    _, ilk_tetik = _sema(eski_demo_katalog_yolu)
    # Her UPDATE'i düşüren tetikleyici: göç yeniden çalışsaydı ikinci açılış düşerdi.
    _ham(eski_demo_katalog_yolu, _BOZUCU)
    with Katalog(eski_demo_katalog_yolu) as k:
        assert k.gecerli_dokuman("AST-J").demo_onayi is True
    _, ikinci_tetik = _sema(eski_demo_katalog_yolu)
    assert ikinci_tetik[_TETIKLEYICI] == ilk_tetik[_TETIKLEYICI]


# --- örnek veri ve katalog_kur (plan adım 7) -------------------------------------------------------


def test_ornek_yukle_demo_onayli_surum_yazar():
    with Katalog() as k:
        ornek_yukle(k, KOK / "data/ornek/katalog.json", KOK)
        surumler = [k.gecerli_dokuman(kod) for kod in ("AST-001", "SZD-001", "PUB-001")]
        assert [(s.onaylayan, s.demo_onayi) for s in surumler] == [(ORNEK, True)] * 3


@pytest.mark.parametrize("onaylayan", ["mp1", "ORNEK-VERI", "ornek-veri "])
def test_ornek_yukle_baska_onaylayani_reddeder(tmp_path, onaylayan):
    veri = json.loads((KOK / "data/ornek/katalog.json").read_text(encoding="utf-8"))
    veri["onaylayan"] = onaylayan
    dosya = tmp_path / "katalog.json"
    dosya.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    with Katalog() as k:
        with pytest.raises(KatalogHatasi):
            ornek_yukle(k, dosya, KOK)
        # hiçbir şey yazılmaz
        assert k.baglanti.execute("SELECT COUNT(*) FROM dokuman_surumleri").fetchone()[0] == 0
        assert k.malzemeler() == [] and k.partiler() == []


def test_katalog_kur_onay_kaydinda_demo_isareti(tmp_path, capsys):
    db = tmp_path / "k.sqlite"
    assert betik_yukle("scripts/katalog_kur.py").main(["--db", str(db), "--ornek"]) == 0
    cikti = capsys.readouterr().out
    with Katalog(db) as k:
        onaylar = DenetimKaydi(k.baglanti).kayitlar("onay")
    assert len(onaylar) == 3
    assert all(json.loads(o.icerik)["demo_onayi"] is True for o in onaylar)
    assert all(o.kullanici == ORNEK for o in onaylar)
    for satir in ("AST-001: MIL-PRF-23377K Type I Class N (v1, demo onayı)",
                  "SZD-001: MIL-PRF-81733D Type I Class 1 (v1, demo onayı)"):
        assert satir in cikti


def test_katalog_kur_gercek_onayli_surumde_demo_yazmaz(tmp_path, capsys):
    db = tmp_path / "k.sqlite"
    betik = betik_yukle("scripts/katalog_kur.py")
    assert betik.main(["--db", str(db), "--ornek"]) == 0
    with Katalog(db) as k:
        k.dokuman_onayla(k.gecerli_dokuman("AST-001").dokuman, "mp1", not_="M&P onayı")
    capsys.readouterr()
    assert betik.main(["--db", str(db)]) == 0
    cikti = capsys.readouterr().out
    satir = next(s for s in cikti.splitlines() if s.startswith("AST-001:"))
    assert "(v2)" in satir and "demo" not in satir
    assert "(v1, demo onayı)" in next(s for s in cikti.splitlines() if s.startswith("SZD-001:"))


# --- ek plan madde 2: _demo_gocu sağlamlaştırma ------------------------------------------------------


class _VekilBaglanti:
    """sqlite3.Connection vekili: her execute önce `kanca(gercek, sql)` çağrılır, sonra iletilir.

    Diğer her şey (row_factory, in_transaction, commit, close...) gerçek bağlantıya gider.
    """

    def __init__(self, gercek: sqlite3.Connection, kanca):
        object.__setattr__(self, "_gercek", gercek)
        object.__setattr__(self, "_kanca", kanca)
        object.__setattr__(self, "komutlar", [])

    def __getattr__(self, ad):
        return getattr(self._gercek, ad)

    def __setattr__(self, ad, deger):
        setattr(self._gercek, ad, deger)

    def execute(self, sql, *args):
        self.komutlar.append(" ".join(sql.split()))
        self._kanca(self._gercek, sql)
        return self._gercek.execute(sql, *args)


def _ilk_baglantiyi_vekille(monkeypatch, kanca) -> list[_VekilBaglanti]:
    """veritabani'nın açtığı İLK bağlantıyı vekille sarar; sonrakiler (ör. ikinci açan) gerçektir."""
    gercek_connect = sqlite3.connect
    vekiller: list[_VekilBaglanti] = []

    def connect(*args, **kwargs):
        b = gercek_connect(*args, **kwargs)
        if vekiller:
            return b
        v = _VekilBaglanti(b, kanca)
        vekiller.append(v)
        return v

    monkeypatch.setattr(veritabani.sqlite3, "connect", connect)
    return vekiller


def _demo_sutunu_var_mi(yol) -> bool:
    return "demo_onayi" in _sema(yol)[0]


def test_demo_gocu_acik_islem_varken_commit_etmez_hata_verir(eski_demo_katalog_yolu):
    # Açık bir işlemin ortasında göç çağrılırsa o işlem sessizce commit edilmemeli.
    k = Katalog(eski_demo_katalog_yolu)
    try:
        b = k.baglanti
        b.execute("ALTER TABLE dokuman_surumleri DROP COLUMN demo_onayi")  # yeniden eski şema
        b.execute("BEGIN")
        b.execute("INSERT INTO tedarikciler (ad) VALUES ('islem-ortasi')")
        with pytest.raises(Exception):
            k._demo_gocu()
        assert b.in_transaction  # dış işlem bitirilmedi
        b.rollback()
        assert b.execute("SELECT COUNT(*) FROM tedarikciler WHERE ad = 'islem-ortasi'").fetchone()[0] == 0
        assert "demo_onayi" not in {s["name"] for s in b.execute("PRAGMA table_info(dokuman_surumleri)")}
    finally:
        k.kapat()


def test_demo_gocu_es_zamanli_ikinci_acan_sutunu_ekleyince_duplicate_column_vermez(eski_demo_katalog_yolu, monkeypatch):
    # Yarış: bu bağlantı sütunun yokluğunu gördükten sonra, BEGIN'den önce başka bir açılış göçü bitirir.
    # BEGIN IMMEDIATE + işlem içinde yeniden denetim: ikinci göç hiçbir şey yapmaz, "duplicate column" yok.
    durum = {"pragma_goruldu": False, "yaris_yapildi": False}

    def kanca(_gercek, sql):
        s = " ".join(sql.split()).lower()
        if "table_info(dokuman_surumleri)" in s:
            durum["pragma_goruldu"] = True
        elif s.startswith("begin") and durum["pragma_goruldu"] and not durum["yaris_yapildi"]:
            durum["yaris_yapildi"] = True
            Katalog(eski_demo_katalog_yolu).kapat()  # öteki açan (gerçek bağlantı) göçü yapar

    _ilk_baglantiyi_vekille(monkeypatch, kanca)
    with Katalog(eski_demo_katalog_yolu) as k:
        assert durum["yaris_yapildi"]
        assert k.gecerli_dokuman("AST-J").demo_onayi is True
        assert k.gecerli_dokuman("AST-001").demo_onayi is False
    _, tetik = _sema(eski_demo_katalog_yolu)
    assert _TETIKLEYICI in tetik


def test_demo_gocu_yazma_kilidini_bastan_alir(eski_demo_katalog_yolu, monkeypatch):
    vekiller = _ilk_baglantiyi_vekille(monkeypatch, lambda _g, _s: None)
    Katalog(eski_demo_katalog_yolu).kapat()
    komutlar = vekiller[0].komutlar
    ekleme = next(i for i, s in enumerate(komutlar) if "ADD COLUMN demo_onayi" in s)
    begin = [s for s in komutlar[:ekleme] if s.upper().startswith("BEGIN")][-1]
    assert begin.upper() == "BEGIN IMMEDIATE"


def test_demo_gocu_islem_kendiliginden_bittiyse_ozgun_hatayi_iletir(eski_demo_katalog_yolu, monkeypatch):
    # UPDATE adımında işlem SQLite tarafından geri alınmış (ör. disk dolu) ve hata yükselmiş olsun.
    # Göç ROLLBACK'i yalnız işlem açıksa çalıştırmalı; yoksa "no transaction is active" özgün hatayı örter.
    class OzgunHata(Exception):
        pass

    def kanca(gercek, sql):
        if " ".join(sql.split()).upper().startswith("UPDATE DOKUMAN_SURUMLERI") and gercek.in_transaction:
            gercek.rollback()
            raise OzgunHata("test: işlem kendiliğinden geri alındı")

    _ilk_baglantiyi_vekille(monkeypatch, kanca)
    with pytest.raises(OzgunHata):
        Katalog(eski_demo_katalog_yolu)
    assert not _demo_sutunu_var_mi(eski_demo_katalog_yolu)
    assert _TETIKLEYICI in _sema(eski_demo_katalog_yolu)[1]


def test_demo_gocu_begin_duserse_ozgun_hatayi_iletir(eski_demo_katalog_yolu, monkeypatch):
    # BEGIN (IMMEDIATE) kilit alamazsa işlem hiç açılmaz; kullanıcı "database is locked" görmeli.
    durum = {"pragma_goruldu": False}

    def kanca(_gercek, sql):
        s = " ".join(sql.split()).lower()
        if "table_info(dokuman_surumleri)" in s:
            durum["pragma_goruldu"] = True
        elif s.startswith("begin") and durum["pragma_goruldu"]:
            raise sqlite3.OperationalError("database is locked")

    _ilk_baglantiyi_vekille(monkeypatch, kanca)
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        Katalog(eski_demo_katalog_yolu)
    assert not _demo_sutunu_var_mi(eski_demo_katalog_yolu)


def test_eski_veritabani_ard_arda_iki_katalogla_acilabilir(eski_demo_katalog_yolu):
    with Katalog(eski_demo_katalog_yolu) as ilk, Katalog(eski_demo_katalog_yolu) as ikinci:
        assert ilk.gecerli_dokuman("AST-J").demo_onayi is True
        assert ikinci.gecerli_dokuman("AST-J").demo_onayi is True


# --- ek plan madde 3: ornek_yukle gerçek onaylı sürümün üstüne demo yazmaz -------------------------

_ORNEK_DOSYALARI = (
    "data/cikti/MIL-PRF-23377K_kabul_dokumani.json",
    "data/cikti/MIL-PRF-81733D_kabul_dokumani.json",
    "data/cikti/MIL-PRF-85285E_kabul_dokumani.json",
)


def _degistirilmis_ornek(tmp_path) -> tuple[Path, Path]:
    """Örnek verinin kopyası; MIL-PRF-23377K dokümanının içeriği değişik (aynı içerik atlaması devreye girmesin).

    Döner: (katalog.json yolu, kök).
    """
    kok = tmp_path / "kok"
    for goreli in _ORNEK_DOSYALARI:
        hedef = kok / goreli
        hedef.parent.mkdir(parents=True, exist_ok=True)
        metin = (KOK / goreli).read_text(encoding="utf-8")
        if "23377K" in goreli:
            d = KabulDokumani.model_validate_json(metin)
            d = d.model_copy(update={"standart": d.standart.model_copy(update={"baslik": "örnek verinin yeni taslağı"})})
            metin = d.model_dump_json()
        hedef.write_text(metin, encoding="utf-8")
    veri = (KOK / "data/ornek/katalog.json").read_text(encoding="utf-8")
    (kok / "katalog.json").write_text(veri, encoding="utf-8")
    return kok / "katalog.json", kok


def test_ornek_yukle_gercek_onayli_surumun_ustune_demo_yazmaz(tmp_path):
    with Katalog() as k:
        ornek_yukle(k, KOK / "data/ornek/katalog.json", KOK)  # demo v1
        k.dokuman_onayla(k.gecerli_dokuman("AST-001").dokuman, "mp1", not_="M&P onayı")  # gerçek v2
        veri, kok = _degistirilmis_ornek(tmp_path)
        ozet = ornek_yukle(k, veri, kok)  # atlar (not düşer), hata vermez
        g = k.gecerli_dokuman("AST-001")
        assert (g.surum, g.onaylayan, g.demo_onayi) == (2, "mp1", False)
        assert len(k.dokuman_surumleri("MIL-PRF-23377", "K")) == 2
        assert not any("MIL-PRF-23377K" in e for e in ozet.dokuman_surumleri)
        assert any("MIL-PRF-23377K" in n for n in ozet.atlanan_dokumanlar)


def test_ornek_yukle_gercek_onay_once_varsa_o_standarda_demo_yazmaz_digerlerini_yukler(tmp_path):
    with Katalog() as k:
        gercek = KabulDokumani.model_validate_json((KOK / _ORNEK_DOSYALARI[0]).read_text(encoding="utf-8"))
        gercek = gercek.model_copy(update={"standart": gercek.standart.model_copy(update={"baslik": "M&P sürümü"})})
        k.dokuman_onayla(gercek, "mp1")  # MIL-PRF-23377K v1 gerçek
        ozet = ornek_yukle(k, KOK / "data/ornek/katalog.json", KOK)
        assert [(s.onaylayan, s.demo_onayi) for s in k.dokuman_surumleri("MIL-PRF-23377", "K")] == [("mp1", False)]
        assert ozet.dokuman_surumleri == ["MIL-PRF-81733D v1", "MIL-PRF-85285E v1"]
        assert any("MIL-PRF-23377K" in n for n in ozet.atlanan_dokumanlar)
        assert k.gecerli_dokuman("SZD-001").demo_onayi is True


def test_ornek_yukle_demo_surumu_varken_yeni_demo_surumu_yazabilir(tmp_path):
    # Yalnız gerçek onay engeller: yalnız demo sürümü olan standarda yeni örnek içerik demo v2 olur.
    with Katalog() as k:
        ornek_yukle(k, KOK / "data/ornek/katalog.json", KOK)
        veri, kok = _degistirilmis_ornek(tmp_path)
        ozet = ornek_yukle(k, veri, kok)
        assert ozet.dokuman_surumleri == ["MIL-PRF-23377K v2"] and ozet.atlanan_dokumanlar == []
        g = k.gecerli_dokuman("AST-001")
        assert (g.surum, g.demo_onayi) == (2, True)


def test_katalog_kur_gercek_onayli_standarda_demo_onay_kaydi_yazmaz(tmp_path, capsys):
    db = tmp_path / "k.sqlite"
    with Katalog(db) as k:
        gercek = KabulDokumani.model_validate_json((KOK / _ORNEK_DOSYALARI[0]).read_text(encoding="utf-8"))
        gercek = gercek.model_copy(update={"standart": gercek.standart.model_copy(update={"baslik": "M&P sürümü"})})
        k.dokuman_onayla(gercek, "mp1")
    assert betik_yukle("scripts/katalog_kur.py").main(["--db", str(db), "--ornek"]) == 0
    with Katalog(db) as k:
        onaylar = [o.dokuman_surumu for o in DenetimKaydi(k.baglanti).kayitlar("onay")]
        assert onaylar == ["MIL-PRF-81733D v1", "MIL-PRF-85285E v1"]
        assert k.gecerli_dokuman("AST-001").demo_onayi is False
    assert "AST-001: MIL-PRF-23377K Type I Class N (v1)," in capsys.readouterr().out


# --- ek plan madde 4: demo_onayi anahtarı olmayan eski karar kayıtları zinciri bozmaz --------------


def test_eski_karar_kayitlari_yenilerle_birlikte_zinciri_dogrular(eski_demo_katalog_yolu, capsys):
    from malzeme_kabul.hat.katalog_karari import KatalogKarari, malzeme_koduyla_kontrol
    from tests import test_katalog_karari as tkk

    with Katalog() as bellek:  # eski biçimde bir karar içeriği (demo_onayi anahtarı yok)
        bellek.dokuman_onayla(tkk.dokuman(), "mp1")
        bellek.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
        eski = malzeme_koduyla_kontrol(bellek, "AST-N", tkk.sertifika()).model_dump(mode="json")
    eski.pop("demo_onayi", None)
    ham = sqlite3.connect(eski_demo_katalog_yolu)  # göçten önceki veritabanında eski kayıt
    DenetimKaydi(ham).ekle("karar", "gk1", eski, malzeme_kodu="AST-001", dokuman_surumu="MIL-PRF-23377K v1")
    ham.commit()
    ham.close()

    with Katalog(eski_demo_katalog_yolu) as k:  # göç + yeni biçimde kararlar
        defter = DenetimKaydi(k.baglanti)
        ser = tkk.sertifika(atif="MIL-PRF-23377J Type I Class N")
        malzeme_koduyla_kontrol(k, "AST-J", ser, defter=defter, kullanici="gk1")
        malzeme_koduyla_kontrol(k, "AST-001", tkk.sertifika(), defter=defter, kullanici="gk1")
        assert defter.zinciri_dogrula().gecerli
        kararlar = defter.kayitlar("karar")
        icerikler = [json.loads(x.icerik) for x in kararlar]
        assert "demo_onayi" not in icerikler[0]
        assert [i["demo_onayi"] for i in icerikler[1:]] == [True, False]
        assert KatalogKarari.model_validate_json(kararlar[0].icerik).demo_onayi is False

    capsys.readouterr()
    assert betik_yukle("scripts/denetim_dogrula.py").main(["--db", str(eski_demo_katalog_yolu)]) == 0
    assert "zincir sağlam: 3 kayıt" in capsys.readouterr().out


# --- Nida kararı (katalog düzeyi koruma): demo onaylı sürüme revizyon bağlanmaz ----------------------


@pytest.fixture
def revizyonlu_katalog():
    k = Katalog()
    k.dokuman_onayla(dokuman("J"), "mp1")
    k.malzeme_ekle("AST-J", "MIL-PRF-23377", "J", tip="I", sinif="N")
    yield k
    k.kapat()


def test_malzeme_revizyonu_ata_demo_onayli_gecerli_surumu_reddeder(revizyonlu_katalog):
    k = revizyonlu_katalog
    k.dokuman_onayla(dokuman("K"), veritabani.ORNEK_ONAYLAYAN, demo_onayi=True)
    with pytest.raises(KatalogHatasi, match="(?i)demo"):
        k.malzeme_revizyonu_ata("AST-J", "K")
    assert k.malzeme("AST-J").revizyon == "J"


def test_malzeme_revizyonu_ata_gercek_onay_ustune_demo_gelirse_reddeder(revizyonlu_katalog):
    k = revizyonlu_katalog
    k.dokuman_onayla(dokuman("K"), "mp1")
    k.dokuman_onayla(dokuman("K"), veritabani.ORNEK_ONAYLAYAN, demo_onayi=True)
    with pytest.raises(KatalogHatasi, match="(?i)demo"):
        k.malzeme_revizyonu_ata("AST-J", "K")
    assert k.malzeme("AST-J").revizyon == "J"


def test_malzeme_revizyonu_ata_demo_ustune_gercek_onay_gelirse_baglar(revizyonlu_katalog):
    k = revizyonlu_katalog
    k.dokuman_onayla(dokuman("K"), veritabani.ORNEK_ONAYLAYAN, demo_onayi=True)
    k.dokuman_onayla(dokuman("K"), "mp1")
    assert k.malzeme_revizyonu_ata("AST-J", "K").revizyon == "K"


def test_malzeme_revizyonu_ata_gercek_onayli_surume_baglar(revizyonlu_katalog):
    k = revizyonlu_katalog
    k.dokuman_onayla(dokuman("K"), "mp1")
    assert k.malzeme_revizyonu_ata("AST-J", "K").revizyon == "K"


def test_malzeme_revizyonu_ata_onayli_surum_yoksa_eskisi_gibi_reddeder(revizyonlu_katalog):
    k = revizyonlu_katalog
    with pytest.raises(KatalogHatasi, match="onaylı kabul dokümanı yok"):
        k.malzeme_revizyonu_ata("AST-J", "K")
    assert k.malzeme("AST-J").revizyon == "J"


def test_malzeme_revizyonu_ata_demo_reddi_dis_islemde_yalniz_kendini_geri_alir(revizyonlu_katalog):
    k = revizyonlu_katalog
    k.dokuman_onayla(dokuman("K"), veritabani.ORNEK_ONAYLAYAN, demo_onayi=True)
    with k.islem():
        k.tedarikci_onayla("AST-J", "Ted Dis")
        with pytest.raises(KatalogHatasi, match="(?i)demo"):
            k.malzeme_revizyonu_ata("AST-J", "K")
        assert k.malzeme("AST-J").revizyon == "J"
    assert k.malzeme("AST-J").revizyon == "J"
    assert "Ted Dis" in k.onayli_tedarikciler("AST-J")  # dış işlem sürdü ve bitti
