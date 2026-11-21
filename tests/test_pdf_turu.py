"""PDF'in metin tabanlı mı taranmış mı olduğunu belirleyen modülün testleri."""

from __future__ import annotations

import csv

import pytest

from conftest import betik_yukle
from pdf_uretici import pdf_yaz

from malzeme_kabul.pdf_turu import (
    KARMA,
    METIN,
    OCR_KATMANLI,
    TARANMIS,
    pdf_turunu_belirle,
)

UZUN = "3.4.2 Viscosity. The admixed primer shall have a viscosity within limits."


def test_metin_sayfali_pdf_metin_tabanli(tmp_path):
    yol = pdf_yaz(tmp_path / "a.pdf", [{"metin": [UZUN, UZUN]}, {"metin": [UZUN]}])
    sonuc = pdf_turunu_belirle(yol)
    assert sonuc.tur == METIN
    assert sonuc.sayfa_sayisi == 2
    assert sonuc.taranmis_sayfalar == []


def test_yalniz_resimli_pdf_taranmis(tmp_path):
    yol = pdf_yaz(tmp_path / "b.pdf", [{"gorsel": True}, {"gorsel": True}])
    sonuc = pdf_turunu_belirle(yol)
    assert sonuc.tur == TARANMIS
    assert sonuc.taranmis_sayfalar == [1, 2]


def test_resim_ustunde_metin_katmani_ocr_katmanli_sayilir(tmp_path):
    yol = pdf_yaz(tmp_path / "c.pdf", [{"gorsel": True, "metin": [UZUN, UZUN]}])
    sonuc = pdf_turunu_belirle(yol)
    assert sonuc.tur == OCR_KATMANLI
    assert sonuc.ocr_katmanli_sayfalar == [1]


def test_metin_ve_taranmis_sayfa_karisik_pdf_karma(tmp_path):
    yol = pdf_yaz(tmp_path / "d.pdf", [{"metin": [UZUN, UZUN]}, {"gorsel": True}])
    sonuc = pdf_turunu_belirle(yol)
    assert sonuc.tur == KARMA
    assert sonuc.taranmis_sayfalar == [2]


def test_bos_sayfa_karari_etkilemez(tmp_path):
    yol = pdf_yaz(tmp_path / "e.pdf", [{"metin": [UZUN, UZUN]}, {}])
    assert pdf_turunu_belirle(yol).tur == METIN


def test_birkac_karakterlik_sayfa_numarasi_taranmis_sayfayi_metin_yapmaz(tmp_path):
    yol = pdf_yaz(tmp_path / "f.pdf", [{"gorsel": True, "metin": ["12"]}])
    assert pdf_turunu_belirle(yol).tur == TARANMIS


def test_pdf_olmayan_dosya_hata_verir(tmp_path):
    yol = tmp_path / "bozuk.pdf"
    yol.write_text("bu bir pdf değil")
    with pytest.raises(ValueError):
        pdf_turunu_belirle(yol)


# --- scripts/pdf_tur_kontrol.py ------------------------------------------------


@pytest.fixture
def kontrol():
    return betik_yukle("scripts/pdf_tur_kontrol.py")


def test_betik_klasordeki_pdfleri_listeler_ve_taranmislari_isaretler(tmp_path, kontrol, capsys):
    ham = tmp_path / "raw"
    ham.mkdir()
    pdf_yaz(ham / "MIL-PRF-23377K.pdf", [{"metin": [UZUN, UZUN]}])
    pdf_yaz(ham / "MIL-PRF-23377G.pdf", [{"gorsel": True}])
    cikti = tmp_path / "liste.csv"

    kod = kontrol.main([str(ham), "--cikti", str(cikti)])

    assert kod == 0
    with cikti.open(encoding="utf-8") as f:
        satirlar = {s["dosya"]: s for s in csv.DictReader(f)}
    assert satirlar["MIL-PRF-23377K.pdf"]["tur"] == METIN
    assert satirlar["MIL-PRF-23377G.pdf"]["tur"] == TARANMIS
    assert satirlar["MIL-PRF-23377G.pdf"]["ocr_gerekli"] == "evet"
    assert satirlar["MIL-PRF-23377K.pdf"]["ocr_gerekli"] == "hayır"
    assert "MIL-PRF-23377G.pdf" in capsys.readouterr().out


def test_betik_bozuk_pdfi_atlamaz_hata_olarak_yazar(tmp_path, kontrol):
    ham = tmp_path / "raw"
    ham.mkdir()
    (ham / "bozuk.pdf").write_text("x")
    cikti = tmp_path / "liste.csv"
    assert kontrol.main([str(ham), "--cikti", str(cikti)]) == 0
    with cikti.open(encoding="utf-8") as f:
        satir = next(csv.DictReader(f))
    assert satir["tur"] == "hata"


def test_betik_bos_klasorde_uyari_verir(tmp_path, kontrol, capsys):
    (tmp_path / "raw").mkdir()
    assert kontrol.main([str(tmp_path / "raw"), "--cikti", str(tmp_path / "l.csv")]) == 1
    assert "PDF bulunamadı" in capsys.readouterr().err
