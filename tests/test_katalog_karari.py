"""Karar motorunun katalogla bağlanması ve parti kuralı (docs/mimari.md madde 2 ve 5)."""

from __future__ import annotations

import pytest

from malzeme_kabul.hat.katalog_karari import PARTI_DURUMU, malzeme_koduyla_kontrol
from malzeme_kabul.katalog.veritabani import Katalog, KatalogHatasi
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.kural.karar_motoru import kontrol_et, parti_karari
from malzeme_kabul.sozlesme.sema import KabulDokumani, Kaynak, Sinir, StandartBilgisi, TestSarti
from malzeme_kabul.sozlesme.sertifika import Sertifika, SertifikaSatiri


def _test(id_, ad, ust, uyg=(), birim="g/L"):
    return TestSarti(
        id=id_, test_adi=ad,
        sinir=Sinir(kriter_turu="sayisal", ust=ust, birim=birim, orijinal_metin=f"{ust} max"),
        kaynak=Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde="3.5.1"),
        test_turleri={"kabul"}, uygulanabilirlik=list(uyg),
    )


def dokuman(voc_ust=340.0):
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        testler=[
            _test("voc", "VOC content", voc_ust),
            _test("krom", "Chromium content", 0.1, ["Class N"], birim="percent"),
        ],
    )


def sertifika(voc="300", atif="MIL-PRF-23377K Type I Class N", krom="0.05", tedarikci="Ted A"):
    satirlar = [SertifikaSatiri(test_adi="VOC content", sonuc=voc, birim="g/L")]
    if krom is not None:
        satirlar.append(SertifikaSatiri(test_adi="Chromium content", sonuc=krom, birim="%"))
    return Sertifika(sertifika_no="S1", standart_atfi=atif, tedarikci=tedarikci, satirlar=satirlar)


def denetimli(katalog: Katalog, kullanici: str = "gk1") -> dict:
    """Parti durumu yazan karar için gereken denetim argümanları (denetim B5).

    Defter katalogla aynı bağlantıyı paylaşır; durum ve kayıt tek işlemdir.
    """
    return {"defter": DenetimKaydi(katalog.baglanti), "kullanici": kullanici}


@pytest.fixture
def katalog():
    k = Katalog()
    k.dokuman_onayla(dokuman(), "mp1")
    k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
    k.malzeme_ekle("AST-C", "MIL-PRF-23377", "K", tip="I", sinif="C2")
    for kod in ("AST-N", "AST-C"):
        k.tedarikci_onayla(kod, "Ted A")
    k.parti_ekle("L1", "AST-N", "Ted A", "K", "2026-06-01")
    yield k
    k.kapat()


# --- parti kuralı ---------------------------------------------------------------


@pytest.mark.parametrize(
    "kararlar, beklenen",
    [
        (["uygun", "uygun"], "kabul"),
        (["uygun", "insan_incelemeli"], "inceleme"),
        (["uygun", "uygun_degil"], "red"),
        (["insan_incelemeli", "uygun_degil"], "red"),
        ([], "inceleme"),  # hiç karar yoksa kabul edilmez (K6)
    ],
)
def test_parti_kurali(kararlar, beklenen):
    assert parti_karari(kararlar) == beklenen


def test_parti_durum_eslemesi():
    assert PARTI_DURUMU == {"kabul": "serbest", "red": "karantina", "inceleme": "bekliyor"}


# --- karar motoru: katalogdan tip/sınıf ------------------------------------------


def test_tip_sinif_katalogdan_gelir_sertifikada_yoksa():
    s = sertifika(atif="MIL-PRF-23377K")  # sertifikada tip/sınıf yok
    eski = kontrol_et(dokuman(), s)
    assert [x.karar for x in eski.satirlar if x.test_id == "krom"] == ["uygun"]  # bilinmiyor → aranıyor
    yeni = kontrol_et(dokuman(), sertifika(atif="MIL-PRF-23377K", krom=None), tip="I", sinif="C2")
    assert [x.test_id for x in yeni.satirlar] == ["voc"]  # Class N şartı C2 için uygulanmaz
    assert yeni.tip_sinif.karar == "uygun" and yeni.belge_karari == "kabul"


def test_katalog_ile_sertifika_celisirse_insan_incelemeli():
    k = kontrol_et(dokuman(), sertifika(atif="MIL-PRF-23377K Type I Class C2"), tip="I", sinif="N")
    assert k.tip_sinif.karar == "insan_incelemeli" and "sınıf katalogda N" in k.tip_sinif.gerekce
    assert k.belge_karari == "inceleme"


def test_katalog_sinif_kodu_romen_rakamina_cevrilir():
    d = KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        testler=[_test("a", "VOC content", 340, ["Class 1"])],
    )
    s = Sertifika(sertifika_no="S", standart_atfi="MIL-PRF-23377K", satirlar=[SertifikaSatiri(test_adi="VOC", sonuc="1", birim="g/L")])
    assert [x.test_id for x in kontrol_et(d, s, tip="i", sinif="1").satirlar] == ["a"]
    k2 = kontrol_et(d, s, tip="I", sinif="2")
    assert "a" not in [x.test_id for x in k2.satirlar]  # Class I şartı Class II için uygulanmaz
    assert k2.belge_karari == "inceleme"  # uygulanan kabul testi yok -> kabul edilmez (K6)


def test_katalog_verilmezse_eski_davranis():
    assert kontrol_et(dokuman(), sertifika()).tip_sinif is None


# --- hat: katalogdan karar ----------------------------------------------------------


def test_dokuman_katalogdan_malzeme_koduna_gore_gelir(katalog):
    k = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika())
    assert k.dokuman_surumu == "MIL-PRF-23377K v1"
    assert k.parti_karari == "kabul" and k.parti_durumu == "serbest"
    assert [s.test_id for s in k.kontrol.satirlar] == ["voc", "krom"]


def test_yeni_onayli_surum_kullanilir(katalog):
    katalog.dokuman_onayla(dokuman(voc_ust=250), "mp2")
    k = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(voc="300"))
    assert k.dokuman_surumu == "MIL-PRF-23377K v2" and k.parti_karari == "red"


def test_bir_test_uygun_degilse_parti_karantinaya(katalog):
    k = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(voc="400"), lot_no="L1", **denetimli(katalog))
    assert k.parti_karari == "red" and k.parti_durumu == "karantina"
    assert katalog.parti("AST-N", "L1").durum == "karantina"


def test_insan_incelemeli_varsa_parti_bekliyor(katalog):
    katalog.parti_durumu_ata("AST-N", "L1", "serbest", kaynak="insan")
    k = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(krom=None), lot_no="L1", **denetimli(katalog))  # krom eksik
    assert k.parti_karari == "inceleme" and katalog.parti("AST-N", "L1").durum == "bekliyor"


def test_hepsi_uygunsa_parti_serbest(katalog):
    s = sertifika().model_copy(update={"parti_no": "L1"})  # parti no denetimi (K3)
    k = malzeme_koduyla_kontrol(katalog, "AST-N", s, lot_no="L1", **denetimli(katalog))
    assert k.parti_karari == "kabul" and katalog.parti("AST-N", "L1").durum == "serbest"
    assert {"tedarikci", "siparis_revizyonu", "parti_no", "parti_tedarikcisi"} <= {s.test_id for s in k.ek_denetimler}


def test_durumu_yaz_kapaliysa_parti_degismez(katalog):
    malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(voc="400"), lot_no="L1", durumu_yaz=False)
    assert katalog.parti("AST-N", "L1").durum == "bekliyor"


def test_onaysiz_tedarikci_insan_incelemeli(katalog):
    k = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(tedarikci="Başka Firma"))
    assert k.ek_denetimler[0].karar == "insan_incelemeli" and k.parti_karari == "inceleme"


def test_tedarikci_adi_buyuk_kucuk_harf_ve_bosluk_duyarsiz(katalog):
    k = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(tedarikci="  ted   a "))
    assert k.ek_denetimler[0].karar == "uygun"


def test_siparis_revizyonu_farkliysa_insan_incelemeli(katalog):
    katalog.parti_ekle("L2", "AST-N", "Ted A", "J", "2026-06-01")
    k = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(), lot_no="L2", **denetimli(katalog))
    siparis = [s for s in k.ek_denetimler if s.test_id == "siparis_revizyonu"]
    assert [s.karar for s in siparis] == ["insan_incelemeli"] and k.parti_karari == "inceleme"


def test_bilinmeyen_kod_ve_onaysiz_dokuman():
    with Katalog() as k:
        with pytest.raises(KatalogHatasi, match="bilinmeyen malzeme"):
            malzeme_koduyla_kontrol(k, "YOK", sertifika())
        k.standart_ekle("MIL-PRF-23377", "J")
        k.malzeme_ekle("AST-J", "MIL-PRF-23377", "J")
        with pytest.raises(KatalogHatasi, match="onaylı kabul dokümanı yok"):
            malzeme_koduyla_kontrol(k, "AST-J", sertifika())


def test_bilinmeyen_lot(katalog):
    with pytest.raises(KatalogHatasi, match="bilinmeyen parti"):
        malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(), lot_no="YOK")


def test_karar_ver_betigi(tmp_path, capsys):
    from tests.conftest import KOK, betik_yukle

    db = tmp_path / "k.sqlite"
    assert betik_yukle("scripts/katalog_kur.py").main(["--db", str(db), "--ornek"]) == 0
    ser = KOK / "data/sentetik/sertifikalar/MIL-PRF-23377K/json/S-001.json"
    assert betik_yukle("scripts/karar_ver.py").main(
        ["--malzeme", "AST-001", "--sertifika", str(ser), "--lot", "A-2512-01", "--db", str(db)]) == 0
    cikti = capsys.readouterr().out
    assert "MIL-PRF-23377K v1 ile karar" in cikti and "Tip ve sınıf (katalog)" in cikti
