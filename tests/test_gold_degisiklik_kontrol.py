"""scripts/ci/gold_degisiklik_kontrol.py: PR'da data/gold/ değişikliği denetimi."""

from __future__ import annotations

import os
import subprocess
import sys

from conftest import KOK, betik_yukle

kontrol = betik_yukle("scripts/ci/gold_degisiklik_kontrol.py")


def test_gold_dosyalari_ayiklanir():
    dosyalar = ["src/a.py", "data/gold/etiket.json", "./data/gold/b.json", "data/golden.txt"]
    assert kontrol.gold_dosyalari(dosyalar) == ["data/gold/etiket.json", "data/gold/b.json"]


def test_gold_degismediyse_gecer():
    gecti, _ = kontrol.kontrol_et(["src/a.py", "tests/test_a.py"], [])
    assert gecti


def test_gold_degistiyse_etiketsiz_basarisiz_olur():
    gecti, mesaj = kontrol.kontrol_et(["data/gold/etiket.json"], ["belgeler"])
    assert not gecti
    assert "data/gold/etiket.json" in mesaj
    assert "gold-guncelleme" in mesaj


def test_gold_degistiyse_etiketle_gecer():
    gecti, _ = kontrol.kontrol_et(["data/gold/etiket.json"], ["gold-guncelleme"])
    assert gecti


def test_etiketler_json_dan_okunur():
    assert kontrol.etiketleri_oku('["gold-guncelleme", "x"]') == ["gold-guncelleme", "x"]
    assert kontrol.etiketleri_oku("[]") == []
    assert kontrol.etiketleri_oku(None) == []
    assert kontrol.etiketleri_oku("bozuk") == []


def _calistir(dosyalar, etiketler):
    ortam = dict(os.environ, PR_ETIKETLERI=etiketler)
    return subprocess.run(
        [sys.executable, str(KOK / "scripts/ci/gold_degisiklik_kontrol.py")],
        input="\n".join(dosyalar),
        capture_output=True,
        text=True,
        env=ortam,
    )


def test_betik_etiketsiz_gold_degisikliginde_1_ile_cikar():
    assert _calistir(["data/gold/a.json"], "[]").returncode == 1


def test_betik_etiketli_gold_degisikliginde_0_ile_cikar():
    assert _calistir(["data/gold/a.json"], '["gold-guncelleme"]').returncode == 0
