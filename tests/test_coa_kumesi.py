"""Gerçek CoA'ların ölçüme girip girmeyeceğini belirleyen kuralın testleri (deney/coa_kumesi.py)."""

from __future__ import annotations

import csv

from conftest import KOK
from deney.coa_kumesi import ALANLAR, coa_durumlari, main, olcum_sertifikalari

BASLIK = ["urun", "tedarikci", "katalog_numarasi", "lot_numarasi", "sertifika_dosya_adi", "sartname_dosya_adi"]


def _liste(tmp_path, satirlar, dosyalar=()):
    klasor = tmp_path / "coa"
    klasor.mkdir()
    for ad in dosyalar:
        (klasor / ad).write_bytes(b"%PDF")
    with (klasor / "liste.csv").open("w", encoding="utf-8", newline="") as f:
        yazici = csv.writer(f)
        yazici.writerow(BASLIK)
        yazici.writerows(satirlar)
    return klasor


def test_iki_lot_ve_ayri_sartname_tamdir(tmp_path):
    klasor = _liste(tmp_path, [
        ["Aseton", "T1", "A1", "L1", "a1_l1.pdf", "a1_spec.pdf"],
        ["Aseton", "T1", "A1", "L2", "a1_l2.pdf", "a1_spec.pdf"],
    ], ["a1_l1.pdf", "a1_l2.pdf", "a1_spec.pdf"])
    durum = {d["sertifika"]: d for d in coa_durumlari(klasor)}
    assert durum["a1_l1.pdf"]["durum"] == "tam" and durum["a1_l1.pdf"]["lot_sayisi"] == 2
    assert durum["a1_l1.pdf"]["neden"] == ""


def test_tek_lot_ya_da_sartnamesiz_urun_eksiktir(tmp_path):
    klasor = _liste(tmp_path, [
        ["Tek lot", "T1", "B1", "L1", "b1_l1.pdf", "b1_spec.pdf"],
        ["Şartnamesiz", "T2", "C1", "L1", "c1_l1.pdf", ""],
        ["Şartnamesiz", "T2", "C1", "L2", "c1_l2.pdf", ""],
        ["Kayıp şartname", "T3", "D1", "L1", "d1_l1.pdf", "d1_spec.pdf"],
        ["Kayıp şartname", "T3", "D1", "L2", "d1_l2.pdf", "d1_spec.pdf"],
        ["Kendisi şartname", "T4", "E1", "L1", "e1_l1.pdf", "e1_l1.pdf"],
        ["Kendisi şartname", "T4", "E1", "L2", "e1_l2.pdf", "e1_l2.pdf"],
    ], ["b1_l1.pdf", "b1_spec.pdf", "c1_l1.pdf", "c1_l2.pdf", "d1_l1.pdf", "d1_l2.pdf", "e1_l1.pdf", "e1_l2.pdf"])
    durum = {d["sertifika"]: d for d in coa_durumlari(klasor)}
    assert durum["b1_l1.pdf"]["durum"] == "eksik" and "tek lot" in durum["b1_l1.pdf"]["neden"]
    assert durum["c1_l1.pdf"]["durum"] == "eksik" and "şartname yok" in durum["c1_l1.pdf"]["neden"]
    assert durum["d1_l1.pdf"]["durum"] == "eksik" and "şartname dosyası yok" in durum["d1_l1.pdf"]["neden"]
    assert durum["e1_l1.pdf"]["durum"] == "eksik" and "şartname yok" in durum["e1_l1.pdf"]["neden"]


def test_ayni_lot_iki_kez_sayilmaz_ve_urun_tedarikciyle_ayrilir(tmp_path):
    klasor = _liste(tmp_path, [
        ["X", "T1", "K1", "L1", "x1.pdf", "s.pdf"],
        ["X", "T1", "K1", "L1", "x1b.pdf", "s.pdf"],  # aynı lotun ikinci kopyası
        ["X", "T2", "K1", "L2", "x2.pdf", "s.pdf"],  # aynı katalog numarası, başka tedarikçi
    ], ["x1.pdf", "x1b.pdf", "x2.pdf", "s.pdf"])
    assert {d["durum"] for d in coa_durumlari(klasor)} == {"eksik"}


def test_olcume_yalniz_tam_sertifikalar_girer(tmp_path):
    klasor = _liste(tmp_path, [
        ["A", "T", "A", "1", "a1.pdf", "as.pdf"],
        ["A", "T", "A", "2", "a2.pdf", "as.pdf"],
        ["B", "T", "B", "1", "b1.pdf", ""],
    ], ["a1.pdf", "a2.pdf", "as.pdf", "b1.pdf"])
    assert olcum_sertifikalari(klasor) == ["a1.pdf", "a2.pdf"]


def test_main_listeyi_yazar(tmp_path, capsys):
    klasor = _liste(tmp_path, [["A", "T", "A", "1", "a1.pdf", ""]], ["a1.pdf"])
    cikti = tmp_path / "kume.csv"
    assert main([str(klasor), "--cikti", str(cikti)]) == 0
    with cikti.open(encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    assert list(satirlar[0]) == ALANLAR and satirlar[0]["durum"] == "eksik"
    assert "tam: 0, eksik: 1" in capsys.readouterr().out


def test_depodaki_liste_guncel():
    """data/coa_kumesi.csv, data/raw/gercek_coa/liste.csv'den yeniden üretilince aynı çıkmalı."""
    with (KOK / "data" / "coa_kumesi.csv").open(encoding="utf-8") as f:
        kayitli = list(csv.DictReader(f))
    hesap = [{k: str(v) for k, v in d.items()} for d in coa_durumlari(KOK / "data" / "raw" / "gercek_coa")]
    assert kayitli == hesap
