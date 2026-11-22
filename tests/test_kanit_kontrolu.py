"""Doğru cevap dosyasındaki sayısal değerlerin PDF'te kanıtını arayan kontrolün testleri."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from conftest import betik_yukle
from pdf_uretici import pdf_yaz

from malzeme_kabul.kanit_kontrolu import kanit_kontrol, metindeki_sayilar
from malzeme_kabul.pdf_okuyucu import pdf_oku
from malzeme_kabul.sema import (
    KabulDokumani, Kaynak, Kosul, NumuneHazirlama, RafOmru, Sinir, StandartBilgisi,
)
from malzeme_kabul.sema import TestSarti as Sart


def kaynak(madde, sayfa=None):
    return Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde=madde, sayfa=sayfa)


def sayisal(alt=None, ust=None, birim=None):
    return Sinir(kriter_turu="sayisal", alt=alt, ust=ust, birim=birim, orijinal_metin="x")


def sart(id, sinir, madde="3.6.3", sayfa=1):
    return Sart(id=id, test_adi=id, sinir=sinir, kaynak=kaynak(madde, sayfa), test_turleri={"kabul"})


def dok(testler=(), raf=(), kosullar=(), numune=()):
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        testler=list(testler), raf_omurleri=list(raf), kosullar=list(kosullar), numune_hazirlama=list(numune),
    )


@pytest.fixture
def pdf(tmp_path) -> Path:
    return pdf_yaz(tmp_path / "standart.pdf", [
        {"metin": [
            "3.6.3 Viscosity. The viscosity shall be 20 to 40 seconds.",
            "3.6.4 Humidity. Relative humidity shall be 50 ±5 percent.",
            "3.4 Cadmium shall be not greater than one part per million.",
            "3.7.1 Lifting. Temperature -40 °C. Exposure 2,000 hours.",
        ]},
        {"metin": [
            "continued from 3.7.1: the film shall withstand 0.5 mm.",
            "3.8 Shelf life. Twelve months at 4 to 38 °C.",
        ]},
        {"metin": ["4.4.2 Panels. Film thickness 0.6 to 0.9 mils."]},
    ])


def _durum(sonuclar, kayit, alan):
    [s] = [s for s in sonuclar if s.kayit == kayit and s.alan == alan]
    return s.durum


# --- Sayı ayıklama ----------------------------------------------------------------


def test_metindeki_sayilar_rakam_binlik_ve_sozcukleri_tanir():
    sayilar = metindeki_sayilar("shall be 2,000 hours, 0.05 percent, .5 mm, one ppm and twelve months")
    assert {2000.0, 0.05, 0.5, 1.0, 12.0} <= sayilar
    assert 0.125 in metindeki_sayilar("a slight widening (1/8 inch)")


def test_metindeki_sayilar_eksi_isaretini_ve_arti_eksi_toleransini_bilir():
    sayilar = metindeki_sayilar("-40 °C and 50 ±5 percent")
    assert -40.0 in sayilar and 40.0 in sayilar
    assert {45.0, 55.0} <= metindeki_sayilar("50 ±5 percent", turetilmis=True)
    assert 45.0 not in metindeki_sayilar("50 ±5 percent")


# --- Kanıt arama ------------------------------------------------------------------


def test_sayfadaki_degerler_bulunur(pdf):
    d = dok([sart("viscosity", sayisal(20, 40, "second"))])
    sonuc = kanit_kontrol(d, pdf_oku(pdf))
    assert _durum(sonuc, "viscosity", "test.sinir.alt") == "bulundu"
    assert _durum(sonuc, "viscosity", "test.sinir.ust") == "bulundu"


def test_sayfada_olmayan_deger_bulunamadi_olur(pdf):
    d = dok([sart("viscosity", sayisal(ust=47, birim="second"))])
    [s] = kanit_kontrol(d, pdf_oku(pdf))
    assert (s.durum, s.deger, s.sayfa, s.madde) == ("bulunamadi", 47.0, 1, "3.6.3")


def test_baska_sayfadaki_deger_o_sayfada_aranmaz(pdf):
    # 0.6 yalnız 3. sayfada geçiyor; kayıt 1. sayfayı gösteriyor.
    d = dok([sart("viscosity", sayisal(ust=0.6, birim="mil"))])
    [s] = kanit_kontrol(d, pdf_oku(pdf))
    assert s.durum == "bulunamadi"


def test_arti_eksiden_hesaplanan_sinir_turetildi_olur(pdf):
    d = dok([sart("humidity", sayisal(45, 55, "%"), madde="3.6.4")])
    sonuc = kanit_kontrol(d, pdf_oku(pdf))
    assert _durum(sonuc, "humidity", "test.sinir.alt") == "turetildi"
    assert _durum(sonuc, "humidity", "test.sinir.ust") == "turetildi"


def test_sozle_yazilmis_sayi_bulunur(pdf):
    d = dok([sart("cadmium", sayisal(ust=1, birim="ppm"), madde="3.4")])
    [s] = kanit_kontrol(d, pdf_oku(pdf))
    assert s.durum == "bulundu"


def test_madde_sonraki_sayfaya_tasiyorsa_sonraki_sayfada_olur(pdf):
    d = dok([sart("lifting", sayisal(ust=0.5, birim="mm"), madde="3.7.1")])
    [s] = kanit_kontrol(d, pdf_oku(pdf))
    assert s.durum == "sonraki_sayfada"


def test_madde_numarasi_sayfada_yoksa_isaretlenir(pdf):
    d = dok([sart("viscosity", sayisal(ust=40, birim="second"), madde="3.9.9")])
    [s] = kanit_kontrol(d, pdf_oku(pdf))
    assert s.madde_sayfada is False


def test_sayfa_verilmemisse_maddenin_gectigi_sayfa_kullanilir(pdf):
    d = dok([sart("panel", sayisal(0.6, 0.9, "mil"), madde="4.4.2", sayfa=None)])
    sonuc = kanit_kontrol(d, pdf_oku(pdf))
    assert {s.durum for s in sonuc} == {"bulundu"}
    assert {s.sayfa for s in sonuc} == {3}


def test_sayfa_da_madde_de_bulunamazsa_sayfa_yok_olur(pdf):
    d = dok([sart("x", sayisal(ust=40, birim="second"), madde="9.9", sayfa=None)])
    [s] = kanit_kontrol(d, pdf_oku(pdf))
    assert s.durum == "sayfa_yok"


def test_raf_omru_kosul_ve_numune_degerleri_de_kontrol_edilir(pdf):
    d = dok(
        raf=[RafOmru(sure=12, birim="month", kosul=sayisal(4, 38, "°C"), kaynak=kaynak("3.8", 2))],
        kosullar=[Kosul(kategori="depolama", ad="Sıcaklık", sinir=sayisal(alt=-40, birim="°C"), kaynak=kaynak("3.7.1", 1))],
        numune=[NumuneHazirlama(id="panel_A", kuru_film_kalinligi=sayisal(0.6, 0.9, "mil"), kaynak=kaynak("4.4.2", 3))],
    )
    sonuc = kanit_kontrol(d, pdf_oku(pdf))
    alanlar = {(s.alan, s.kayit): s.durum for s in sonuc}
    assert alanlar == {
        ("raf_omru.sure", "genel"): "bulundu",
        ("raf_omru.kosul.alt", "genel"): "bulundu",
        ("raf_omru.kosul.ust", "genel"): "bulundu",
        ("kosul.sinir.alt", "depolama:Sıcaklık"): "bulundu",
        ("numune.kuru_film_kalinligi.alt", "panel_A"): "bulundu",
        ("numune.kuru_film_kalinligi.ust", "panel_A"): "bulundu",
    }


def test_sayisal_olmayan_kriterler_atlanir(pdf):
    metinsel = Sinir(kriter_turu="metinsel", orijinal_metin="no lifting")
    assert kanit_kontrol(dok([sart("lifting", metinsel)]), pdf_oku(pdf)) == []


def test_pdf_sayfa_sayisini_asan_sayfa_sayfa_yok_olur(pdf):
    d = dok([sart("viscosity", sayisal(ust=40, birim="second"), sayfa=99)])
    [s] = kanit_kontrol(d, pdf_oku(pdf))
    assert s.durum == "sayfa_yok"


# --- Betik ------------------------------------------------------------------------


@pytest.fixture
def gold(tmp_path):
    d = dok([sart("viscosity", sayisal(20, 47, "second")), sart("humidity", sayisal(45, 55, "%"), madde="3.6.4")])
    yol = tmp_path / "gold.json"
    yol.write_text(d.model_dump_json(), encoding="utf-8")
    return yol


def test_betik_bulunamayanlari_listeler_ve_1_doner(gold, pdf, tmp_path, capsys):
    betik = betik_yukle("scripts/kanit_kontrol.py")
    md, cs = tmp_path / "out" / "kanit.md", tmp_path / "out" / "kanit.csv"
    assert betik.main([str(gold), str(pdf), "--md", str(md), "--csv", str(cs)]) == 1
    cikti = capsys.readouterr().out
    assert "bulunamadı: 1" in cikti
    metin = md.read_text(encoding="utf-8")
    assert "## Bulunamayan değerler (1)" in metin and "viscosity" in metin and "47" in metin
    assert "## ± toleransından hesaplanan değerler (2)" in metin
    with open(cs, encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    assert len(satirlar) == 4 and {s["durum"] for s in satirlar} == {"bulundu", "bulunamadi", "turetildi"}


def test_betik_hepsi_bulunursa_0_doner(tmp_path, pdf):
    betik = betik_yukle("scripts/kanit_kontrol.py")
    yol = tmp_path / "g.json"
    yol.write_text(dok([sart("viscosity", sayisal(20, 40, "second"))]).model_dump_json(), encoding="utf-8")
    assert betik.main([str(yol), str(pdf)]) == 0


def test_betik_gecersiz_girdide_2_doner(gold, tmp_path):
    betik = betik_yukle("scripts/kanit_kontrol.py")
    assert betik.main([str(gold), str(tmp_path / "yok.pdf")]) == 2


def test_betik_data_gold_altina_yazmaz(gold, pdf, tmp_path):
    betik = betik_yukle("scripts/kanit_kontrol.py")
    hedef = tmp_path / "data" / "gold" / "kanit.md"
    assert betik.main([str(gold), str(pdf), "--md", str(hedef)]) == 2
    assert not hedef.exists()
