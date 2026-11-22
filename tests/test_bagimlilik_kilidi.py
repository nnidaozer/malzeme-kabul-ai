"""Sabitlenmiş bağımlılık sürümlerinin ve CI pip-audit taramasının testleri.

docs/guvenlik.md, tehdit 3: bağımlılık sürümleri kilit dosyalarında tam
sürümle sabitlenir; CI bu dosyalardan kurar ve pip-audit ile tarar.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

KOK = Path(__file__).resolve().parents[1]
CALISMA = KOK / "requirements.lock"
GELISTIRME = KOK / "requirements-dev.lock"
TEST_AKISI = KOK / ".github" / "workflows" / "test.yml"
SATIR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*==[A-Za-z0-9.+!-]+$")


def kilit_oku(yol: Path) -> dict[str, str]:
    """Kilit dosyasını {normal ad: sürüm} olarak okur; her satır ad==sürüm olmalı."""
    surumler = {}
    for satir in yol.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#"):
            continue
        assert SATIR.match(satir), f"{yol.name}: tam sürümle sabitlenmemiş satır: {satir!r}"
        ad, surum = satir.split("==")
        surumler[canonicalize_name(ad)] = surum
    return surumler


def pyproject_bagimliliklari() -> tuple[list[Requirement], list[Requirement]]:
    proje = tomllib.loads((KOK / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    calisma = [Requirement(r) for r in proje["dependencies"]]
    gelistirme = [Requirement(r) for r in proje["optional-dependencies"]["dev"]]
    return calisma, gelistirme


@pytest.mark.parametrize("yol", [CALISMA, GELISTIRME], ids=lambda p: p.name)
def test_kilit_satirlari_tam_surumle_sabit(yol):
    assert kilit_oku(yol)


def test_calisma_bagimliliklari_kilitte_ve_araliga_uyar():
    kilit = kilit_oku(CALISMA)
    for r in pyproject_bagimliliklari()[0]:
        ad = canonicalize_name(r.name)
        assert ad in kilit, f"{r.name} requirements.lock içinde yok"
        assert r.specifier.contains(kilit[ad], prereleases=True), f"{r.name}=={kilit[ad]} pyproject aralığına ({r.specifier}) uymuyor"


def test_gelistirme_kilidi_hepsini_icerir():
    kilit = kilit_oku(GELISTIRME)
    calisma, gelistirme = pyproject_bagimliliklari()
    for r in calisma + gelistirme:
        ad = canonicalize_name(r.name)
        assert ad in kilit, f"{r.name} requirements-dev.lock içinde yok"
        assert r.specifier.contains(kilit[ad], prereleases=True)


def test_iki_kilit_ayni_surumleri_kullanir():
    calisma, gelistirme = kilit_oku(CALISMA), kilit_oku(GELISTIRME)
    assert {ad: gelistirme.get(ad) for ad in calisma} == calisma


def test_ci_kilitten_kurar():
    akis = TEST_AKISI.read_text(encoding="utf-8")
    assert "pip install -r requirements-dev.lock" in akis
    assert "pip install -e . --no-deps" in akis
    assert 'pip install -e ".[dev]"' not in akis


def test_ci_pip_audit_ile_tarar():
    akis = TEST_AKISI.read_text(encoding="utf-8")
    assert re.search(r"pip install pip-audit==\d", akis), "pip-audit sürümü sabitlenmeli"
    assert re.search(r"pip-audit .*-r requirements-dev\.lock", akis)
    assert "--strict" in akis
