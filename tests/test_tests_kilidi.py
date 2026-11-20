"""scripts/hooks/tests_kilidi.py: yalnızca uygulayici ajanı için tests/ kilidi."""

from __future__ import annotations

import pytest

from conftest import betik_yukle, hook_calistir

tests_kilidi = betik_yukle("scripts/hooks/tests_kilidi.py")
BETIK = "scripts/hooks/tests_kilidi.py"


def girdi(arac, proje, ajan=None, **arac_girdisi):
    g = {"tool_name": arac, "tool_input": arac_girdisi, "cwd": str(proje)}
    if ajan:
        g["agent_type"] = ajan
    return g


@pytest.mark.parametrize("arac", ["Write", "Edit", "MultiEdit"])
def test_uygulayici_tests_e_yazamaz(proje, arac):
    g = girdi(arac, proje, "uygulayici", file_path=str(proje / "tests/test_birim.py"))
    assert tests_kilidi.karar_ver(g) == 2


@pytest.mark.parametrize(
    "komut",
    [
        "sed -i 's/assert/# assert/' tests/test_birim.py",
        "rm tests/test_birim.py",
        "echo 'def test_x(): pass' > tests/test_x.py",
        "git checkout main -- tests/",
        "mv tests/test_birim.py /tmp/",
    ],
)
def test_uygulayici_bash_ile_tests_i_degistiremez(proje, komut):
    assert tests_kilidi.karar_ver(girdi("Bash", proje, "uygulayici", command=komut)) == 2


@pytest.mark.parametrize(
    "komut",
    ["pytest", "pytest tests/test_birim.py -x", "cat tests/test_birim.py", "grep -rn def tests/"],
)
def test_uygulayici_testleri_okuyup_calistirabilir(proje, komut):
    assert tests_kilidi.karar_ver(girdi("Bash", proje, "uygulayici", command=komut)) == 0


def test_uygulayici_src_ye_yazabilir(proje):
    g = girdi("Write", proje, "uygulayici", file_path=str(proje / "src/malzeme_kabul/birim.py"))
    assert tests_kilidi.karar_ver(g) == 0


def test_uygulayici_baska_klasordeki_tests_adli_klasore_yazabilir(proje):
    g = girdi("Write", proje, "uygulayici", file_path=str(proje / "src/malzeme_kabul/tests/x.py"))
    assert tests_kilidi.karar_ver(g) == 0


@pytest.mark.parametrize("ajan", ["test-yazari", None, "planlayici"])
def test_diger_ajanlar_ve_ana_oturum_tests_e_yazabilir(proje, ajan):
    g = girdi("Write", proje, ajan, file_path=str(proje / "tests/test_birim.py"))
    assert tests_kilidi.karar_ver(g) == 0


def test_betik_uygulayiciyi_2_ile_engeller(proje):
    g = girdi("Edit", proje, "uygulayici", file_path=str(proje / "tests/test_birim.py"))
    sonuc = hook_calistir(BETIK, g, proje)
    assert sonuc.returncode == 2
    assert "uygulayici" in sonuc.stderr


def test_betik_test_yazariya_izin_verir(proje):
    g = girdi("Edit", proje, "test-yazari", file_path=str(proje / "tests/test_birim.py"))
    assert hook_calistir(BETIK, g, proje).returncode == 0
