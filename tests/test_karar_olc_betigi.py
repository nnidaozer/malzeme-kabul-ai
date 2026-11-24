"""deney/karar_olc.py betiğinin testleri."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from conftest import betik_yukle
from malzeme_kabul.sozlesme.sema import KabulDokumani
from deney.sertifika_uretici import uret

KOK = Path(__file__).resolve().parents[1]
DOKUMAN_YOLU = KOK / "data" / "cikti" / "MIL-PRF-23377K_kabul_dokumani.json"


@pytest.fixture
def klasor(tmp_path) -> Path:
    dokuman = KabulDokumani.model_validate_json(DOKUMAN_YOLU.read_text(encoding="utf-8"))
    uretilen = uret(dokuman, dagilim={None: 3, "sinir_disi": 2, "eksik_test": 1, "birim": 2})
    (tmp_path / "json").mkdir()
    for u in uretilen:
        (tmp_path / "json" / f"{u.sertifika.sertifika_no}.json").write_text(u.sertifika.model_dump_json(), encoding="utf-8")
    (tmp_path / "dogru_kararlar.json").write_text(
        json.dumps([u.dogru.model_dump(mode="json") for u in uretilen]), encoding="utf-8"
    )
    return tmp_path


def test_rapor_ve_csv_yazilir(klasor, tmp_path):
    betik = betik_yukle("deney/karar_olc.py")
    cikti = tmp_path / "sonuc" / "olcum"
    assert betik.main([str(DOKUMAN_YOLU), str(klasor), "--cikti", str(cikti)]) == 0
    md = cikti.with_suffix(".md").read_text(encoding="utf-8")
    assert "Yanlış kabul oranı" in md and "Hata türüne göre" in md and "Belge başına süre" in md
    with open(cikti.with_suffix(".csv"), encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    assert len(satirlar) == 8
    assert {s["hata_turu"] for s in satirlar} == {"temiz", "sinir_disi", "eksik_test", "birim"}


def test_eksik_test_politikasi_degistirilebilir(klasor, tmp_path):
    betik = betik_yukle("deney/karar_olc.py")
    cikti = tmp_path / "olcum"
    betik.main([str(DOKUMAN_YOLU), str(klasor), "--cikti", str(cikti), "--eksik-test", "uygun_degil"])
    with open(cikti.with_suffix(".csv"), encoding="utf-8") as f:
        eksik = [s for s in csv.DictReader(f) if s["hata_turu"] == "eksik_test"]
    assert all(s["motor_belge_karari"] == "red" for s in eksik)


def test_gold_klasorune_yazmaz(klasor, tmp_path):
    betik = betik_yukle("deney/karar_olc.py")
    with pytest.raises(SystemExit):
        betik.main([str(DOKUMAN_YOLU), str(klasor), "--cikti", str(tmp_path / "data" / "gold" / "olcum")])


def test_ad_varyant_kapsami_sayilir():
    betik = betik_yukle("deney/karar_olc.py")
    dokuman = KabulDokumani.model_validate_json(DOKUMAN_YOLU.read_text(encoding="utf-8"))
    eslesen, toplam, kacan = betik.ad_varyant_kapsami(dokuman)
    assert 0 < eslesen <= toplam and len(kacan) == toplam - eslesen
