"""scripts/hooks/gold_koruma.py: data/gold/ yazma engeli."""

from __future__ import annotations

import pytest

from conftest import betik_yukle, hook_calistir

gold_koruma = betik_yukle("scripts/hooks/gold_koruma.py")
BETIK = "scripts/hooks/gold_koruma.py"


def bash(komut, proje, **ek):
    return {"tool_name": "Bash", "tool_input": {"command": komut}, "cwd": str(proje), **ek}


def dosya(arac, yol, proje):
    anahtar = "notebook_path" if arac == "NotebookEdit" else "file_path"
    return {"tool_name": arac, "tool_input": {anahtar: str(yol)}, "cwd": str(proje)}


# --- Dosya araçları -------------------------------------------------------------


@pytest.mark.parametrize("arac", ["Write", "Edit", "MultiEdit", "NotebookEdit"])
def test_dosya_araclari_gold_icine_yazamaz(proje, arac):
    assert gold_koruma.karar_ver(dosya(arac, proje / "data/gold/yeni.json", proje)) == 2


def test_gold_klasorunun_kendisine_yazilamaz(proje):
    assert gold_koruma.karar_ver(dosya("Write", proje / "data/gold", proje)) == 2


def test_goreli_ve_nokta_noktali_yol_da_yakalanir(proje):
    assert gold_koruma.karar_ver(dosya("Write", "data/raw/../gold/x.json", proje)) == 2


def test_gold_a_isaret_eden_sembolik_bag_yakalanir(proje):
    (proje / "kisayol").symlink_to(proje / "data/gold")
    assert gold_koruma.karar_ver(dosya("Write", proje / "kisayol/x.json", proje)) == 2


@pytest.mark.parametrize("yol", ["data/raw/x.json", "src/malzeme_kabul/a.py", "data/golden.txt"])
def test_dosya_araclari_gold_disina_yazabilir(proje, yol):
    assert gold_koruma.karar_ver(dosya("Write", proje / yol, proje)) == 0


def test_okuma_araci_engellenmez(proje):
    assert gold_koruma.karar_ver(dosya("Read", proje / "data/gold/etiket.json", proje)) == 0


# --- Bash -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "komut",
    [
        "echo '{}' > data/gold/x.json",
        "echo a >> data/gold/etiket.json",
        "cat data/raw/a.json | tee data/gold/a.json",
        "cp data/raw/a.json data/gold/",
        "cp -r data/raw data/gold/raw",
        "cp -t data/gold data/raw/a.json",
        "mv data/gold/etiket.json data/raw/",
        "rm data/gold/etiket.json",
        "rm -rf data/gold",
        "touch data/gold/yeni.json",
        "mkdir data/gold/alt",
        "sed -i 's/uygun/red/' data/gold/etiket.json",
        "perl -pi -e 's/a/b/' data/gold/etiket.json",
        "python -c \"open('data/gold/x.json','w').write('{}')\"",
        "python3 -c 'import shutil; shutil.rmtree(\"data/gold\")'",
        "bash -c 'echo x > data/gold/y'",
        "find data/gold -name '*.json' -delete",
        "find data/gold -exec rm {} +",
        "ls data/gold | xargs rm",
        "git checkout -- data/gold/etiket.json",
        "git rm data/gold/etiket.json",
        "cd data/gold && echo x > y.json",
        "ls; echo x > ./data/gold/a.json",
        "pytest && rm data/gold/etiket.json",
        "cat <<EOF > data/gold/x.json\n{}\nEOF",
        "sudo rm data/gold/etiket.json",
        "echo $(rm data/gold/etiket.json)",
        "truncate -s 0 data/gold/etiket.json",
        "dd if=/dev/zero of=data/gold/etiket.json",
        "echo 'kapanmamis > data/gold/x",
    ],
)
def test_bash_gold_a_yazamaz(proje, komut):
    assert gold_koruma.karar_ver(bash(komut, proje)) == 2, komut


def test_bash_mutlak_yolla_yazamaz(proje):
    komut = f"echo x > {proje}/data/gold/x.json"
    assert gold_koruma.karar_ver(bash(komut, proje)) == 2


def test_bash_baska_dizinden_goreli_yolla_yazamaz(proje):
    girdi = bash("touch gold/x.json", proje)
    girdi["cwd"] = str(proje / "data")
    assert gold_koruma.karar_ver(girdi) == 2


@pytest.mark.parametrize(
    "komut",
    [
        "cat data/gold/etiket.json",
        "ls -la data/gold",
        "grep -r uygun data/gold/",
        "head -n 5 data/gold/etiket.json",
        "wc -l data/gold/*.json",
        "python scripts/degerlendir.py --gold data/gold --cikti sonuclar/",
        "python scripts/degerlendir.py data/gold > sonuclar/rapor.txt",
        "pytest tests/ 2>&1 | tail -20",
        "cp data/gold/etiket.json /tmp/kopya.json",
        "diff data/gold/etiket.json sonuclar/tahmin.json",
        "git diff -- data/gold",
        "git log --oneline -- data/gold",
        "find data/gold -name '*.json'",
        "echo x > data/raw/x.json",
        "rm data/raw/eski.json",
        "pip install -e .[dev]",
        "cd src && ls",
    ],
)
def test_bash_gold_u_okuyabilir_ve_baska_yere_yazabilir(proje, komut):
    assert gold_koruma.karar_ver(bash(komut, proje)) == 0, komut


def test_kural_alt_ajanlarda_da_gecerli(proje):
    girdi = bash("rm data/gold/etiket.json", proje, agent_type="degerlendirme-kosucusu")
    assert gold_koruma.karar_ver(girdi) == 2


def test_diger_araclar_engellenmez(proje):
    assert gold_koruma.karar_ver({"tool_name": "Grep", "tool_input": {"pattern": "x"}}) == 0


# --- Uçtan uca: betik Claude Code'un çağırdığı gibi çalışır ---------------------


def test_betik_engellerken_2_ile_cikar_ve_sebebi_yazar(proje):
    sonuc = hook_calistir(BETIK, bash("rm data/gold/etiket.json", proje), proje)
    assert sonuc.returncode == 2
    assert "data/gold" in sonuc.stderr


def test_betik_izin_verirken_0_ile_cikar(proje):
    sonuc = hook_calistir(BETIK, bash("cat data/gold/etiket.json", proje), proje)
    assert sonuc.returncode == 0
    assert sonuc.stderr == ""


def test_betik_bozuk_girdide_engeller(proje):
    import subprocess
    import sys

    from conftest import KOK

    sonuc = subprocess.run(
        [sys.executable, str(KOK / BETIK)], input="bozuk", capture_output=True, text=True
    )
    assert sonuc.returncode == 2


# --- PowerShell (Windows) -------------------------------------------------------


def ps(komut, proje):
    return {"tool_name": "PowerShell", "tool_input": {"command": komut}, "cwd": str(proje)}


@pytest.mark.parametrize(
    "komut",
    [
        "Set-Content -Path data\\gold\\x.json -Value '{}'",
        "Remove-Item -Recurse data\\gold",
        "'{}' | Out-File data/gold/x.json",
        "New-Item -ItemType File data\\gold\\yeni.json",
        "Copy-Item data\\raw\\a.json -Destination data\\gold\\",
        "Move-Item data\\gold\\etiket.json data\\raw\\",
        "del data\\gold\\etiket.json",
        "echo x > data\\gold\\x.json",
    ],
)
def test_powershell_gold_a_yazamaz(proje, komut):
    assert gold_koruma.karar_ver(ps(komut, proje)) == 2, komut


@pytest.mark.parametrize(
    "komut",
    [
        "Get-Content data\\gold\\etiket.json",
        "Get-ChildItem data\\gold",
        "Copy-Item data\\gold\\etiket.json -Destination sonuclar\\",
        "python scripts\\degerlendir.py --gold data\\gold",
    ],
)
def test_powershell_gold_u_okuyabilir(proje, komut):
    assert gold_koruma.karar_ver(ps(komut, proje)) == 0, komut
