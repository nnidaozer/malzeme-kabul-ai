"""Sentetik sertifika üreticisinin testleri."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from conftest import betik_yukle
from malzeme_kabul.sozlesme.sema import KabulDokumani
from malzeme_kabul.sozlesme.sertifika import Sertifika
from deney.sertifika_uretici import DAGILIM, uret, uygulanir

KOK = Path(__file__).resolve().parents[1]
DOKUMAN_YOLU = KOK / "data" / "cikti" / "MIL-PRF-23377K_kabul_dokumani.json"


@pytest.fixture(scope="module")
def dokuman() -> KabulDokumani:
    return KabulDokumani.model_validate_json(DOKUMAN_YOLU.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def uretilen(dokuman):
    return uret(dokuman)


def test_150_sertifika_ve_dagilim(uretilen):
    assert len(uretilen) == 150
    assert Counter(u.dogru.hata_turu for u in uretilen) == Counter({k: v for k, v in DAGILIM.items()})
    hatali = sum(u.dogru.hata_turu is not None for u in uretilen)
    assert 70 <= hatali <= 85  # yaklaşık yarısı


def test_ayni_tohum_ayni_sonuc(dokuman, uretilen):
    tekrar = uret(dokuman)
    assert [u.sertifika for u in tekrar] == [u.sertifika for u in uretilen]
    assert [u.dogru for u in tekrar] == [u.dogru for u in uretilen]


def test_farkli_tohum_farkli_sonuc(dokuman, uretilen):
    assert [u.sertifika for u in uret(dokuman, tohum=1)] != [u.sertifika for u in uretilen]


def test_sertifika_numaralari_benzersiz(uretilen):
    nolar = [u.sertifika.sertifika_no for u in uretilen]
    assert len(set(nolar)) == len(nolar)
    assert all(u.dogru.sertifika_no == u.sertifika.sertifika_no for u in uretilen)


def test_yeterlilik_testleri_sertifikada_yok(dokuman, uretilen):
    yalniz_yeterlilik = {t.test_adi for t in dokuman.testler if not t.kabul_testi}
    for u in uretilen:
        assert not {s.test_adi for s in u.sertifika.satirlar} & yalniz_yeterlilik


@pytest.mark.parametrize("uyg, tip, sinif, beklenen", [([], "I", "C1", True), (["Type II"], "I", "N", False), (["Class N"], "II", "N", True)])
def test_uygulanir(dokuman, uyg, tip, sinif, beklenen):
    test = dokuman.kabul_testleri[0].model_copy(update={"uygulanabilirlik": uyg})
    assert uygulanir(test, tip, sinif) is beklenen


def test_temiz_sertifikalar_kabul_ve_degerler_sinir_icinde(dokuman, uretilen):
    testler = {t.test_adi: t for t in dokuman.kabul_testleri}
    for u in (u for u in uretilen if u.dogru.hata_turu is None):
        assert u.dogru.belge_karari == "kabul"
        assert set(u.dogru.satirlar.values()) == {"uygun"}
        for s in u.sertifika.satirlar:
            sinir = testler[s.test_adi].sinir
            if sinir.kriter_turu != "sayisal":
                continue
            deger = float(s.sonuc.rstrip("A").replace(",", "."))
            assert sinir.alt is None or deger >= sinir.alt
            assert sinir.ust is None or deger <= sinir.ust


def test_her_uygulanan_test_icin_dogru_karar_var(dokuman, uretilen):
    for u in uretilen:
        atif = u.sertifika.urun  # "Epoxy primer, Type I, Class C2"
        tip = atif.split("Type ")[1].split(",")[0]
        sinif = atif.split("Class ")[1]
        beklenen = {t.id for t in dokuman.kabul_testleri if uygulanir(t, tip, sinif)}
        assert set(u.dogru.satirlar) == beklenen


@pytest.mark.parametrize(
    "tur, belge_kararlari",
    [
        ("sinir_disi", {"red"}),
        ("eksik_test", {"inceleme"}),
        ("revizyon", {"inceleme"}),
        ("ad_farki", {"kabul"}),
        ("birim", {"kabul", "red", "inceleme"}),
        ("sinira_yakin", {"kabul", "red"}),
        ("algilama_siniri", {"kabul", "inceleme"}),
    ],
)
def test_hata_turune_gore_dogru_belge_karari(uretilen, tur, belge_kararlari):
    assert {u.dogru.belge_karari for u in uretilen if u.dogru.hata_turu == tur} == belge_kararlari


def test_eksik_testte_satir_gercekten_yok(dokuman, uretilen):
    adlar = {t.id: t.test_adi for t in dokuman.testler}
    for u in (u for u in uretilen if u.dogru.hata_turu == "eksik_test"):
        eksik = [k for k, v in u.dogru.satirlar.items() if v == "insan_incelemeli"]
        assert len(eksik) == 1
        assert adlar[eksik[0]] not in {s.test_adi for s in u.sertifika.satirlar}


def test_yanlis_revizyon_atfi(uretilen):
    for u in (u for u in uretilen if u.dogru.hata_turu == "revizyon"):
        assert "23377K" not in u.sertifika.standart_atfi and "Rev. K" not in u.sertifika.standart_atfi
        assert u.dogru.revizyon == "insan_incelemeli"


def test_ad_farkinda_standart_ad_kullanilmaz(dokuman, uretilen):
    standart = {t.test_adi for t in dokuman.testler}
    for u in (u for u in uretilen if u.dogru.hata_turu == "ad_farki"):
        assert len({s.test_adi for s in u.sertifika.satirlar} - standart) == 1


def test_betik_json_ve_dogru_kararlari_yazar(tmp_path):
    betik = betik_yukle("deney/sertifika_uret.py")
    assert betik.main([str(DOKUMAN_YOLU), "--cikti", str(tmp_path), "--pdfsiz"]) == 0
    jsonlar = sorted((tmp_path / "json").glob("*.json"))
    assert len(jsonlar) == 150
    Sertifika.model_validate_json(jsonlar[0].read_text(encoding="utf-8"))
    dogrular = json.loads((tmp_path / "dogru_kararlar.json").read_text(encoding="utf-8"))
    assert len(dogrular) == 150
    assert (tmp_path / "ozet.csv").exists()


def test_betik_pdf_uretir(tmp_path):
    pytest.importorskip("reportlab")
    import pdfplumber

    betik = betik_yukle("deney/sertifika_uret.py")
    betik.main([str(DOKUMAN_YOLU), "--cikti", str(tmp_path)])
    with pdfplumber.open(tmp_path / "pdf" / "S-001.pdf") as pdf:
        metin = pdf.pages[0].extract_text()
    assert "S-001" in metin and "MIL-PRF-23377" in metin


def test_betik_gold_klasorune_yazmaz(tmp_path):
    betik = betik_yukle("deney/sertifika_uret.py")
    with pytest.raises(SystemExit):
        betik.main([str(DOKUMAN_YOLU), "--cikti", str(tmp_path / "data" / "gold" / "x"), "--pdfsiz"])
