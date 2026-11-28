"""Tek komutla demo kurulumu (docs/demo_plani.md, yol haritası madde 6).

`scripts/demo.py` conftest'teki `betik_yukle` ile modül olarak yüklenir.
Bu testler ağa çıkmaz: sanal ortam / pip adımı yalnız saf fonksiyonlarla ve
main'in `--kurulum-yok --yalniz-kur` yoluyla sınanır; subprocess çağrılmaz,
Streamlit başlatılmaz. Demo her zaman tmp_path altına kurulur; data/gold'a
dokunulmaz.
"""

from __future__ import annotations

import builtins
import functools
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import traceback
from pathlib import Path

import pytest

from malzeme_kabul.arayuz import ekran_verisi as ev
from malzeme_kabul.arayuz import kimlik
from malzeme_kabul.hat.hibrit_hat import sertifika_hatti
from malzeme_kabul.katalog.ornek_veri import YuklemeOzeti, ornek_yukle
from malzeme_kabul.katalog.veritabani import ORNEK_ONAYLAYAN, Katalog
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.sozlesme.sema import KabulDokumani
from tests.conftest import KOK, betik_yukle

DEMO_BETIGI = KOK / "scripts" / "demo.py"
DEMO_KATALOG = KOK / "data" / "demo" / "katalog.json"
DEMO_J_DOKUMANI = KOK / "data" / "demo" / "MIL-PRF-23377J_kabul_dokumani.json"
ORNEK_KATALOG = KOK / "data" / "ornek" / "katalog.json"
SENTETIK = KOK / "data" / "sentetik" / "sertifikalar" / "MIL-PRF-23377K" / "pdf"
TEDARIKCI = "Ornek Aerospace Finishes Ltd. (kurgusal)"
DEMO_DOSYALARI = {
    "MIL-PRF-23377K.pdf": KOK / "data" / "raw" / "MIL-PRF-23377K.pdf",
    "hatali_CoC_B86447.pdf": SENTETIK / "S-089.pdf",
    "temiz_CoC_B80677.pdf": SENTETIK / "S-032.pdf",
}


@functools.cache
def demo_betigi():
    """scripts/demo.py'yi yükler; yoksa testi açık bir mesajla başarısız kılar."""
    assert DEMO_BETIGI.is_file(), "scripts/demo.py henüz yok"
    return betik_yukle("scripts/demo.py")


def katalog_kur_betigi():
    return betik_yukle("scripts/katalog_kur.py")


def parolalari_oku(dosya: Path) -> dict[str, str]:
    """Parola dosyasını ayrıştırır.

    Varsayılan biçim: her kullanıcı ayrı satırda, satırın ilk sözcüğü kullanıcı
    adı (sonundaki `:`/`=` gibi işaretler atılır), son sözcüğü parola. `#` ile
    başlayan satırlar açıklamadır.
    """
    parolalar: dict[str, str] = {}
    for satir in dosya.read_text(encoding="utf-8").splitlines():
        if not satir.strip() or satir.lstrip().startswith("#"):
            continue
        sozcukler = satir.split()
        if len(sozcukler) < 2:
            continue
        ad = sozcukler[0].strip(":=/,()")
        if ad in ("mp", "gk"):
            parolalar[ad] = sozcukler[-1]
    return parolalar


def klasor_goruntusu(klasor: Path) -> dict[str, tuple[int, int, str]]:
    """Klasördeki her dosyanın (mtime_ns, boyut, sha256) özeti."""
    sonuc = {}
    for yol in sorted(klasor.rglob("*")):
        if yol.is_file():
            st = yol.stat()
            sonuc[str(yol.relative_to(klasor))] = (st.st_mtime_ns, st.st_size, hashlib.sha256(yol.read_bytes()).hexdigest())
    return sonuc


def bolunme_test_kumesi() -> list[str]:
    metin = (KOK / "data" / "bolunme.yaml").read_text(encoding="utf-8")
    m = re.search(r"^test:\s*\n((?:\s*-.*\n?)+)", metin, re.MULTILINE)
    assert m, "bolunme.yaml test listesi okunamadı"
    return [s.strip()[1:].split("#")[0].strip() for s in m.group(1).splitlines() if s.strip().startswith("-")]




def dosya_ozeti(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


# --- 1. Python sürümü ----------------------------------------------------------------------


@pytest.mark.parametrize("surum", [(3, 11, 0), (3, 11, 9), (3, 12, 1), (3, 13, 0), (4, 0, 0)])
def test_python_3_11_ve_ustu_uygun_sayilir(surum):
    assert demo_betigi().python_uygun_mu(surum) is True


@pytest.mark.parametrize("surum", [(3, 10, 99), (3, 10, 0), (3, 9, 18), (2, 7, 18)])
def test_python_3_11_alti_uygun_sayilmaz(surum):
    assert demo_betigi().python_uygun_mu(surum) is False


def test_python_uygun_degilse_main_2_doner_ve_gereken_surumu_yazar(monkeypatch, capsys):
    demo = demo_betigi()
    monkeypatch.setattr(demo, "python_uygun_mu", lambda *a, **k: False)
    monkeypatch.setattr(demo, "demo_kur", lambda *a, **k: pytest.fail("eski Python'da demo kurulmamalı"))
    assert demo.main(["--kurulum-yok", "--yalniz-kur"]) == 2
    cikti = capsys.readouterr()
    assert "3.11" in cikti.out + cikti.err


# --- 2. Sanal ortam ve kurulum (saf fonksiyonlar; ağ ve pip yok) ---------------------------


def test_venv_python_windowsta_scripts_python_exe(tmp_path):
    assert demo_betigi().venv_python(tmp_path / ".venv", platform="win32") == tmp_path / ".venv" / "Scripts" / "python.exe"


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_venv_python_posixte_bin_python(tmp_path, platform):
    assert demo_betigi().venv_python(tmp_path / ".venv", platform=platform) == tmp_path / ".venv" / "bin" / "python"


@pytest.fixture
def sahte_kok(tmp_path):
    kok = tmp_path / "kok"
    kok.mkdir()
    (kok / "requirements-arayuz.lock").write_text("streamlit==1.0\n", encoding="utf-8")
    (kok / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    return kok


def test_kilit_ozeti_sha256_onaltilik_ve_tekrarlanabilir(sahte_kok):
    demo = demo_betigi()
    ozet = demo.kilit_ozeti(sahte_kok)
    assert re.fullmatch(r"[0-9a-f]{64}", ozet)
    assert demo.kilit_ozeti(sahte_kok) == ozet


def test_kilit_ozeti_kilit_dosyasi_degisince_degisir(sahte_kok):
    demo = demo_betigi()
    once = demo.kilit_ozeti(sahte_kok)
    (sahte_kok / "requirements-arayuz.lock").write_text("streamlit==1.1\n", encoding="utf-8")
    assert demo.kilit_ozeti(sahte_kok) != once


def test_kilit_ozeti_pyproject_degisince_degisir(sahte_kok):
    demo = demo_betigi()
    once = demo.kilit_ozeti(sahte_kok)
    (sahte_kok / "pyproject.toml").write_text("[project]\nname = 'y'\n", encoding="utf-8")
    assert demo.kilit_ozeti(sahte_kok) != once


def _venv_hazirla(demo, venv: Path) -> None:
    py = demo.venv_python(venv)
    py.parent.mkdir(parents=True, exist_ok=True)
    py.write_text("", encoding="utf-8")


def test_kurulum_isareti_yoksa_kurulum_gerekir(tmp_path, sahte_kok):
    demo = demo_betigi()
    venv = tmp_path / ".venv"
    _venv_hazirla(demo, venv)
    assert demo.kurulum_gerekli_mi(venv, sahte_kok) is True


def test_sanal_ortam_hic_yoksa_kurulum_gerekir(tmp_path, sahte_kok):
    assert demo_betigi().kurulum_gerekli_mi(tmp_path / "yok", sahte_kok) is True


def test_kurulum_isaretindeki_ozet_ayniysa_kurulum_gerekmez(tmp_path, sahte_kok):
    demo = demo_betigi()
    venv = tmp_path / ".venv"
    _venv_hazirla(demo, venv)
    (venv / ".malzeme_kabul_kurulum").write_text(demo.kilit_ozeti(sahte_kok), encoding="utf-8")
    assert demo.kurulum_gerekli_mi(venv, sahte_kok) is False


def test_kilit_degisince_kurulum_yeniden_gerekir(tmp_path, sahte_kok):
    demo = demo_betigi()
    venv = tmp_path / ".venv"
    _venv_hazirla(demo, venv)
    (venv / ".malzeme_kabul_kurulum").write_text(demo.kilit_ozeti(sahte_kok), encoding="utf-8")
    (sahte_kok / "requirements-arayuz.lock").write_text("streamlit==2.0\n", encoding="utf-8")
    assert demo.kurulum_gerekli_mi(venv, sahte_kok) is True


def test_kurulum_komutlari_once_kilitli_bagimliliklar_sonra_paket_bagimliliksiz(tmp_path, sahte_kok):
    venv_py = tmp_path / ".venv" / "bin" / "python"
    komutlar = [[str(p) for p in k] for k in demo_betigi().kurulum_komutlari(venv_py, sahte_kok)]
    assert len(komutlar) == 2
    birinci, ikinci = komutlar
    assert birinci[:5] == [str(venv_py), "-m", "pip", "install", "-r"]
    assert len(birinci) == 6 and Path(birinci[5]).name == "requirements-arayuz.lock"
    assert birinci[5] in ("requirements-arayuz.lock", str(sahte_kok / "requirements-arayuz.lock"))
    assert ikinci == [str(venv_py), "-m", "pip", "install", "--no-deps", "-e", str(sahte_kok)]


# --- 4. Streamlit komutu ve ortamı (saf; başlatılmaz) -----------------------------------------


def _ardisik(komut: list[str], anahtar: str) -> str:
    assert anahtar in komut, f"{anahtar} komutta yok: {komut}"
    return komut[komut.index(anahtar) + 1]


def test_streamlit_komutu_uygulamayi_yalniz_127_0_0_1_de_verilen_portta_baslatir(tmp_path):
    py = tmp_path / "python"
    komut = [str(p) for p in demo_betigi().streamlit_komutu(py, KOK, 8502)]
    assert komut[0] == str(py)
    assert "streamlit" in komut and _ardisik(komut, "streamlit") == "run"
    assert Path(_ardisik(komut, "run")).as_posix().endswith("src/malzeme_kabul/arayuz/uygulama.py")
    assert _ardisik(komut, "--server.address") == "127.0.0.1"
    assert _ardisik(komut, "--server.port") == "8502"
    assert _ardisik(komut, "--server.headless") == "true"
    assert _ardisik(komut, "--browser.gatherUsageStats") == "false"
    assert _ardisik(komut, "--client.toolbarMode") == "minimal"  # "Deploy" düğmesi görünmez (Docker gibi)
    assert "0.0.0.0" not in komut


def test_streamlit_komutu_port_degistirilebilir(tmp_path):
    komut = [str(p) for p in demo_betigi().streamlit_komutu(tmp_path / "python", KOK, 8601)]
    assert _ardisik(komut, "--server.port") == "8601"


def _sahte_kurulum(demo, klasor: Path):
    return demo.DemoKurulumu(db=klasor / "katalog.sqlite", parola_dosyasi=klasor / "parolalar.txt",
                             dosyalar=klasor / "dosyalar", yeni_kuruldu=True)


def test_streamlit_ortami_demo_veritabanini_ve_yukleme_klasorunu_gosterir(tmp_path):
    demo = demo_betigi()
    klasor = tmp_path / "demo"
    ortam = demo.streamlit_ortami(_sahte_kurulum(demo, klasor), {"PATH": "/usr/bin"})
    assert Path(ortam["MALZEME_KABUL_DB"]) == klasor / "katalog.sqlite"
    assert Path(ortam["MALZEME_KABUL_YUKLEME"]) == klasor / "yuklenen"
    assert ortam["PATH"] == "/usr/bin"


def test_streamlit_ortami_onceden_tanimli_db_degiskenini_demoyla_ezer_ve_girdiyi_degistirmez(tmp_path):
    demo = demo_betigi()
    klasor = tmp_path / "demo"
    girdi = {"MALZEME_KABUL_DB": "/baska/katalog.sqlite", "MALZEME_KABUL_YUKLEME": "/baska/yuklenen"}
    ortam = demo.streamlit_ortami(_sahte_kurulum(demo, klasor), girdi)
    assert Path(ortam["MALZEME_KABUL_DB"]) == klasor / "katalog.sqlite"
    assert Path(ortam["MALZEME_KABUL_YUKLEME"]) == klasor / "yuklenen"
    assert girdi == {"MALZEME_KABUL_DB": "/baska/katalog.sqlite", "MALZEME_KABUL_YUKLEME": "/baska/yuklenen"}


# --- 5. main: --kurulum-yok --yalniz-kur (pip yok, Streamlit yok) -----------------------------


@pytest.fixture
def alt_surec_yasak(monkeypatch):
    """subprocess ve exec çağrılarını yasaklar; çağrılırsa test başarısız olur."""

    def yasak(*a, **k):
        pytest.fail(f"alt süreç çağrılmamalıydı: {a!r}")

    for ad in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, ad, yasak)
    for ad in ("execv", "execve", "execvp", "execvpe", "system"):
        if hasattr(os, ad):
            monkeypatch.setattr(os, ad, yasak)


def sahte_demo_kur_ayarla(monkeypatch, tmp_path):
    """main'in çağırdığı demo_kur'u tmp_path'e kuran sahtesiyle değiştirir; çağrıları kaydeder."""
    demo = demo_betigi()
    cagrilar: list[dict] = []
    klasor = tmp_path / "demo"

    def sahte(*a, **k):
        cagrilar.append({"a": a, "k": k})
        return _sahte_kurulum(demo, klasor)

    monkeypatch.setattr(demo, "demo_kur", sahte)
    return demo, cagrilar, klasor


def test_main_yalniz_kur_ile_streamlit_ve_pip_cagirmadan_0_doner(alt_surec_yasak, monkeypatch, tmp_path):
    demo, cagrilar, _ = sahte_demo_kur_ayarla(monkeypatch, tmp_path)
    assert demo.main(["--kurulum-yok", "--yalniz-kur"]) == 0
    assert len(cagrilar) == 1


def test_main_parola_dosyasinin_ve_demo_dosyalarinin_yolunu_yazar(alt_surec_yasak, monkeypatch, tmp_path, capsys):
    demo, _, klasor = sahte_demo_kur_ayarla(monkeypatch, tmp_path)
    demo.main(["--kurulum-yok", "--yalniz-kur"])
    cikti = capsys.readouterr().out
    assert str(klasor / "parolalar.txt") in cikti
    assert str(klasor / "dosyalar") in cikti


def _sifirla_degeri(cagri: dict) -> bool:
    if "sifirla" in cagri["k"]:
        return cagri["k"]["sifirla"]
    return cagri["a"][2] if len(cagri["a"]) > 2 else False


def test_main_varsayilan_olarak_sifirlamadan_kurar(alt_surec_yasak, monkeypatch, tmp_path):
    demo, cagrilar, _ = sahte_demo_kur_ayarla(monkeypatch, tmp_path)
    demo.main(["--kurulum-yok", "--yalniz-kur"])
    assert _sifirla_degeri(cagrilar[0]) is False


def test_main_sifirla_secenegini_demo_kura_iletir(alt_surec_yasak, monkeypatch, tmp_path):
    demo, cagrilar, _ = sahte_demo_kur_ayarla(monkeypatch, tmp_path)
    demo.main(["--kurulum-yok", "--yalniz-kur", "--sifirla"])
    assert _sifirla_degeri(cagrilar[0]) is True


# --- 3. katalog_kur.ornek_kur (yükleme döngüsü fonksiyona alınır) -----------------------------


@pytest.fixture
def bos_katalog():
    k = Katalog(":memory:")
    yield k
    k.kapat()


def test_ornek_kur_yukleme_ozeti_doner(bos_katalog):
    defter = DenetimKaydi(bos_katalog.baglanti)
    ozet = katalog_kur_betigi().ornek_kur(bos_katalog, defter, ORNEK_KATALOG, KOK)
    assert isinstance(ozet, YuklemeOzeti)
    assert "MIL-PRF-23377K v1" in ozet.dokuman_surumleri
    assert "AST-001" in ozet.malzemeler


def test_ornek_kur_her_yeni_surum_icin_demo_onay_kaydi_yazar(bos_katalog):
    defter = DenetimKaydi(bos_katalog.baglanti)
    ozet = katalog_kur_betigi().ornek_kur(bos_katalog, defter, ORNEK_KATALOG, KOK)
    onaylar = defter.kayitlar("onay")
    assert sorted(o.dokuman_surumu for o in onaylar) == sorted(ozet.dokuman_surumleri)
    for o in onaylar:
        assert o.kullanici == ORNEK_ONAYLAYAN
        assert o.veri["demo_onayi"] is True


def test_ornek_kur_ikinci_kez_yeni_onay_kaydi_yazmaz(bos_katalog):
    defter = DenetimKaydi(bos_katalog.baglanti)
    betik = katalog_kur_betigi()
    betik.ornek_kur(bos_katalog, defter, ORNEK_KATALOG, KOK)
    sayi = len(defter.kayitlar("onay"))
    ikinci = betik.ornek_kur(bos_katalog, defter, ORNEK_KATALOG, KOK)
    assert ikinci.dokuman_surumleri == []
    assert len(defter.kayitlar("onay")) == sayi


def test_katalog_kur_ornek_secenegi_ornek_kuru_cagirir(tmp_path, monkeypatch):
    betik = katalog_kur_betigi()
    gercek = betik.ornek_kur
    cagrilar = []

    def izle(*a, **k):
        cagrilar.append(a)
        return gercek(*a, **k)

    monkeypatch.setattr(betik, "ornek_kur", izle)
    assert betik.main(["--db", str(tmp_path / "k.sqlite"), "--ornek"]) == 0
    assert len(cagrilar) == 1


# --- data/demo içeriği -------------------------------------------------------------------------


def demo_verisi() -> dict:
    assert DEMO_KATALOG.is_file(), "data/demo/katalog.json henüz yok"
    return json.loads(DEMO_KATALOG.read_text(encoding="utf-8"))


def test_demo_katalogu_ornek_veri_onaylayaniyla_demo_onaylidir():
    assert demo_verisi()["onaylayan"] == ORNEK_ONAYLAYAN


def test_demo_katalogu_23377j_kabul_dokumanini_yukler():
    dokumanlar = demo_verisi()["dokumanlar"]
    assert "data/demo/MIL-PRF-23377J_kabul_dokumani.json" in dokumanlar
    assert not [d for d in dokumanlar if d.startswith("data/gold")]


def test_23377j_kabul_dokumani_gecerli_sema_ve_j_revizyonu():
    assert DEMO_J_DOKUMANI.is_file(), "data/demo/MIL-PRF-23377J_kabul_dokumani.json henüz yok"
    d = KabulDokumani.model_validate_json(DEMO_J_DOKUMANI.read_text(encoding="utf-8"))
    assert (d.standart.belge_no, d.standart.revizyon) == ("MIL-PRF-23377", "J")
    assert d.testler


def test_demo_katalogu_ast_003_u_23377j_type_i_class_n_olarak_tanimlar():
    m = [m for m in demo_verisi()["malzemeler"] if m["kod"] == "AST-003"]
    assert len(m) == 1
    assert (m[0]["belge_no"], m[0]["revizyon"], m[0]["tip"], m[0]["sinif"]) == ("MIL-PRF-23377", "J", "I", "N")


def test_demo_katalogu_sentetik_tedarikciyi_ast_001_icin_onaylar():
    assert {"malzeme_kodu": "AST-001", "tedarikci": TEDARIKCI} in demo_verisi()["onayli_tedarikciler"]


@pytest.mark.parametrize("lot", ["B86447", "B80677"])
def test_demo_katalogu_ast_001_icin_sentetik_tedarikcinin_bekleyen_lotunu_icerir(lot):
    p = [p for p in demo_verisi()["partiler"] if p["lot_no"] == lot]
    assert len(p) == 1
    assert (p[0]["malzeme_kodu"], p[0]["tedarikci"], p[0]["siparis_revizyonu"], p[0]["durum"]) == (
        "AST-001", TEDARIKCI, "K", "bekliyor")


def test_demo_katalogu_ast_003_icin_parti_icerir():
    assert [p for p in demo_verisi()["partiler"] if p["malzeme_kodu"] == "AST-003"]


def test_demo_katalogu_ornek_verinin_ustune_yuklenince_ast_003_j_demo_surumune_baglanir(bos_katalog):
    ornek_yukle(bos_katalog, ORNEK_KATALOG, KOK)
    ornek_yukle(bos_katalog, DEMO_KATALOG, KOK)
    g = bos_katalog.gecerli_dokuman("AST-003")
    assert (g.revizyon, g.demo_onayi, g.onaylayan) == ("J", True, ORNEK_ONAYLAYAN)


# --- 3. demo_kur ---------------------------------------------------------------------------------


def kur(tmp_path, capsys):
    """Demoyu tmp_path/demo altına kurar; (kurulum, yakalanan çıktı) döner."""
    k = demo_betigi().demo_kur(tmp_path / "demo", KOK)
    return k, capsys.readouterr()


def test_demo_kur_yeni_kurulumda_yeni_kuruldu_doner(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    assert k.yeni_kuruldu is True
    assert Path(k.db).is_file()
    assert Path(k.db).resolve().is_relative_to((tmp_path / "demo").resolve())


@pytest.mark.parametrize("ad", list(DEMO_DOSYALARI))
def test_demo_kur_demo_dosyasini_kaynagiyla_ayni_icerikte_kopyalar(tmp_path, capsys, ad):
    k, _ = kur(tmp_path, capsys)
    hedef = Path(k.dosyalar) / ad
    assert hedef.is_file()
    assert dosya_ozeti(hedef) == dosya_ozeti(DEMO_DOSYALARI[ad])


def test_demo_kur_test_kumesi_ve_gercek_havacilik_belgelerini_kopyalamaz(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    adlar = [p.name for p in Path(k.dosyalar).rglob("*") if p.is_file()]
    yasak = bolunme_test_kumesi()
    assert not [a for a in adlar if any(a.startswith(s) for s in yasak)]
    havacilik = {p.name for p in (KOK / "data/raw/gercek_coc_havacilik").rglob("*") if p.is_file()}
    assert not havacilik & set(adlar)
    assert not [p for p in Path(k.dosyalar).rglob("*") if "gercek_coc_havacilik" in p.parts]


def test_demo_kur_ornek_ve_demo_dokumanlarini_demo_onayiyla_yukler(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    with Katalog(k.db) as katalog:
        for kod, rev in (("AST-001", "K"), ("AST-003", "J")):
            g = katalog.gecerli_dokuman(kod)
            assert (g.revizyon, g.demo_onayi, g.onaylayan) == (rev, True, ORNEK_ONAYLAYAN)
        onaylar = DenetimKaydi(katalog.baglanti).kayitlar("onay")
        etiketler = {o.dokuman_surumu for o in onaylar}
        assert {"MIL-PRF-23377K v1", "MIL-PRF-23377J v1"} <= etiketler
        assert all(o.veri["demo_onayi"] is True for o in onaylar)


def test_demo_kur_lotlari_ve_tedarikciyi_katalogga_yazar(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    with Katalog(k.db) as katalog:
        assert TEDARIKCI in katalog.onayli_tedarikciler("AST-001")
        for lot in ("B86447", "B80677"):
            p = katalog.parti("AST-001", lot)
            assert (p.tedarikci, p.durum) == (TEDARIKCI, "bekliyor")
        assert katalog.partiler("AST-003")


def test_demo_kur_mp_ve_giris_kalite_kullanicilarini_parola_dosyasindaki_parolalarla_acar(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    parolalar = parolalari_oku(Path(k.parola_dosyasi))
    assert set(parolalar) == {"mp", "gk"}
    with Katalog(k.db) as katalog:
        mp = kimlik.giris(katalog.baglanti, "mp", parolalar["mp"])
        gk = kimlik.giris(katalog.baglanti, "gk", parolalar["gk"])
    assert mp is not None and mp.rol == "mp"
    assert gk is not None and gk.rol == "giris_kalite"


def test_demo_parolalari_en_az_16_karakter_ve_birbirinden_farkli(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    parolalar = parolalari_oku(Path(k.parola_dosyasi))
    assert all(len(p) >= 16 for p in parolalar.values())
    assert parolalar["mp"] != parolalar["gk"]


def test_demo_parolalari_deneme_parolasi_degildir(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    parolalar = parolalari_oku(Path(k.parola_dosyasi))
    assert parolalar["mp"] != "mp-ornek-parola" and parolalar["gk"] != "gk-ornek-parola"


def test_yanlis_parolayla_demo_kullanicisi_giris_yapamaz(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    with Katalog(k.db) as katalog:
        assert kimlik.giris(katalog.baglanti, "mp", "yanlis-parola-0123456789") is None


@pytest.mark.skipif(os.name != "posix", reason="dosya izni POSIX'e özgü")
def test_parola_dosyasi_yalniz_sahibince_okunur_0600(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    assert stat.S_IMODE(Path(k.parola_dosyasi).stat().st_mode) == 0o600


def test_demo_kur_parolalari_ekrana_yazmaz(tmp_path, capsys):
    k, cikti = kur(tmp_path, capsys)
    for parola in parolalari_oku(Path(k.parola_dosyasi)).values():
        assert parola not in cikti.out
        assert parola not in cikti.err


def test_main_parolalari_ekrana_yazmaz(tmp_path, monkeypatch, capsys, alt_surec_yasak):
    demo = demo_betigi()
    gercek = demo.demo_kur
    kurulan = []

    def tmp_ye_kur(*a, sifirla=False, **k):
        kurulan.append(gercek(tmp_path / "demo", KOK, sifirla=sifirla))
        return kurulan[-1]

    monkeypatch.setattr(demo, "demo_kur", tmp_ye_kur)
    assert demo.main(["--kurulum-yok", "--yalniz-kur"]) == 0
    cikti = capsys.readouterr()
    assert kurulan
    for parola in parolalari_oku(Path(kurulan[0].parola_dosyasi)).values():
        assert parola not in cikti.out and parola not in cikti.err


def test_ikinci_demo_kur_veritabanina_ve_parolalara_dokunmaz(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    db_once = dosya_ozeti(Path(k.db))
    parola_once = Path(k.parola_dosyasi).read_text(encoding="utf-8")
    ikinci = demo_betigi().demo_kur(tmp_path / "demo", KOK)
    assert ikinci.yeni_kuruldu is False
    assert dosya_ozeti(Path(k.db)) == db_once
    assert Path(k.parola_dosyasi).read_text(encoding="utf-8") == parola_once


def test_sifirla_ile_demo_yeniden_kurulur_ve_parolalar_yenilenir(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    eski = parolalari_oku(Path(k.parola_dosyasi))
    with Katalog(k.db) as katalog:  # yeni kurulumda olmayacak bir iz bırak
        katalog.parti_durumu_ata("AST-001", "B80677", "karantina", kaynak="insan")
    yeni_k = demo_betigi().demo_kur(tmp_path / "demo", KOK, sifirla=True)
    assert yeni_k.yeni_kuruldu is True
    yeni = parolalari_oku(Path(yeni_k.parola_dosyasi))
    assert yeni["mp"] != eski["mp"] and yeni["gk"] != eski["gk"]
    with Katalog(yeni_k.db) as katalog:
        assert kimlik.giris(katalog.baglanti, "mp", yeni["mp"]) is not None
        assert kimlik.giris(katalog.baglanti, "mp", eski["mp"]) is None
        assert katalog.parti("AST-001", "B80677").durum == "bekliyor"


def test_demo_kur_data_gold_a_yazmaz(tmp_path):
    once = klasor_goruntusu(KOK / "data" / "gold")
    demo_betigi().demo_kur(tmp_path / "demo", KOK)
    assert klasor_goruntusu(KOK / "data" / "gold") == once


def test_demo_kur_gold_test_kumesi_ve_gercek_havacilik_dosyalarini_acmaz(tmp_path, monkeypatch):
    demo = demo_betigi()
    acilanlar: list[str] = []
    gercek_open = builtins.open
    gercek_io_open = io.open

    def izle(asil):
        def ac(dosya, *a, **k):
            if isinstance(dosya, (str, os.PathLike)):
                acilanlar.append(str(Path(dosya).resolve()))
            return asil(dosya, *a, **k)
        return ac

    monkeypatch.setattr(builtins, "open", izle(gercek_open))
    monkeypatch.setattr(io, "open", izle(gercek_io_open))
    demo.demo_kur(tmp_path / "demo", KOK)
    monkeypatch.undo()
    raw = (KOK / "data" / "raw").resolve()
    gold = (KOK / "data" / "gold").resolve()
    yasak_onekler = [str(raw / s) for s in bolunme_test_kumesi()]
    assert not [a for a in acilanlar if Path(a).is_relative_to(gold)]
    assert not [a for a in acilanlar if Path(a).is_relative_to(raw / "gercek_coc_havacilik")]
    assert not [a for a in acilanlar if any(a.startswith(o) for o in yasak_onekler)]


# --- uçtan uca demo akışı (senaryonun altı adımı) ---------------------------------------------


@pytest.fixture(scope="module")
def akis(tmp_path_factory):
    """Demoyu kurar ve senaryoyu baştan sona oynatır; sonuçları (ya da hatayı) toplar."""
    sonuc: dict = {}
    try:
        k = demo_betigi().demo_kur(tmp_path_factory.mktemp("demo_akis") / "demo", KOK)
        sonuc["kurulum"] = k
        dosyalar = Path(k.dosyalar)
        katalog = Katalog(k.db)
        defter = DenetimKaydi(katalog.baglanti)
        sonuc["ilk_surum"] = katalog.gecerli_dokuman("AST-001")
        # 1-2: standart yükle, kabul dokümanını onayla (demo v1 yerine gerçek v2)
        taslak = ev.standart_yukle(katalog, dosyalar / "MIL-PRF-23377K.pdf", "mp")
        sonuc["onaylanan"] = ev.taslak_onayla(katalog, defter, taslak.id, "mp", "demo senaryosu")
        sonuc["gecerli"] = katalog.gecerli_dokuman("AST-001")
        # 3-4: hatalı CoC -> RED, madde referansı
        karar, _ = sertifika_hatti(
            katalog, "AST-001", dosyalar / "hatali_CoC_B86447.pdf", mod="kural", lot_no="B86447",
            defter=defter, kullanici="gk")
        sonuc["hatali_baslik"] = ev.karar_basligi(karar)
        sonuc["hatali_tablo"] = ev.karar_tablosu(karar)
        sonuc["hatali_parti"] = katalog.parti("AST-001", "B86447").durum
        karar2, _ = sertifika_hatti(
            katalog, "AST-001", dosyalar / "temiz_CoC_B80677.pdf", mod="kural", lot_no="B80677",
            defter=defter, kullanici="gk")
        sonuc["temiz_baslik"] = ev.karar_basligi(karar2)
        # 5: revizyon etkisi
        from malzeme_kabul.hat.revizyon_etkisi import mp_incelemesini_kapat, yeni_revizyon_yukle

        sonuc["etki"] = yeni_revizyon_yukle(katalog, "MIL-PRF-23377", "K", "mp")
        # 5b: M&P incelemesini kapat; AST-003 K'ye geçer
        mp_incelemesini_kapat(katalog, defter, "AST-003", "mp", "yeni_revizyona_gec", "demo: K'ye geçildi", "K")
        sonuc["ast003_sonra"] = katalog.malzeme("AST-003")
        sonuc["ast003_dokuman"] = katalog.gecerli_dokuman("AST-003")
        sonuc["kayit_turleri"] = [r.tur for r in defter.kayitlar()]
        # 6: denetim kaydı
        sonuc["zincir"] = defter.zinciri_dogrula()
        katalog.kapat()
        sonuc["dogrula_kodu"] = betik_yukle("scripts/denetim_dogrula.py").main(["--db", str(k.db)])
    except Exception:  # testler hatayı başarısızlık olarak gösterir
        sonuc["hata"] = traceback.format_exc()
    return sonuc


def adim(akis: dict, anahtar: str):
    if anahtar not in akis:
        pytest.fail(f"demo akışı '{anahtar}' adımına ulaşamadı:\n{akis.get('hata', '')}")
    return akis[anahtar]


def test_akis_baslangicta_ast_001_demo_onayli_v1_e_bagli(akis):
    s = adim(akis, "ilk_surum")
    assert (s.etiket, s.demo_onayi) == ("MIL-PRF-23377K v1", True)


def test_akis_onaylanan_taslak_demo_olmayan_v2_olur_ve_gecerli_surum_olur(akis):
    s = adim(akis, "onaylanan")
    assert (s.etiket, s.demo_onayi) == ("MIL-PRF-23377K v2", False)
    assert adim(akis, "gecerli").etiket == "MIL-PRF-23377K v2"


def test_akis_hatali_coc_kural_modunda_red_karantina_verir(akis):
    assert adim(akis, "hatali_baslik") == "Parti kararı: ❌ RED (karantina)"
    assert adim(akis, "hatali_parti") == "karantina"


def test_akis_hatali_coc_ta_yalniz_kuruma_suresi_3_7_2_ile_uygun_degil(akis):
    tablo = adim(akis, "hatali_tablo")
    uygun_degil = [s for s in tablo if s["karar"] == ev.ETIKETLER["uygun_degil"]]
    assert [(s["test"], s["madde"]) for s in uygun_degil] == [("Drying time", "MIL-PRF-23377K, 3.7.2")]
    assert all(s["karar"] == ev.ETIKETLER["uygun"] for s in tablo if s not in uygun_degil)


@pytest.mark.parametrize("satir", ["Onaylı tedarikçi", "Parti numarası", "Partinin tedarikçisi"])
def test_akis_hatali_coc_ta_tedarikci_ve_lot_satirlari_uygun(akis, satir):
    tablo = {s["test"]: s["karar"] for s in adim(akis, "hatali_tablo")}
    assert tablo.get(satir) == ev.ETIKETLER["uygun"]


def test_akis_temiz_coc_kabul_serbest_verir(akis):
    assert adim(akis, "temiz_baslik") == "Parti kararı: ✅ KABUL (serbest)"


def test_akis_k_revizyonu_yuklenince_yalniz_j_deki_ast_003_isaretlenir(akis):
    etki = adim(akis, "etki")
    assert "AST-003" in etki.etkilenen_malzemeler
    assert "AST-001" not in etki.etkilenen_malzemeler
    assert [p for p in etki.etkilenen_partiler if p.startswith("AST-003/")]


def test_akis_sonunda_denetim_zinciri_saglam(akis):
    assert adim(akis, "zincir").gecerli is True


def test_akis_sonunda_denetim_dogrula_betigi_0_doner(akis):
    assert adim(akis, "dogrula_kodu") == 0


def test_akis_inceleme_kapatilinca_ast_003_23377k_ye_baglanir_ve_v2_yi_kullanir(akis):
    m = adim(akis, "ast003_sonra")
    assert m.standart_etiketi == "MIL-PRF-23377K"
    assert m.mp_inceleme is None
    assert adim(akis, "ast003_dokuman").etiket == "MIL-PRF-23377K v2"


def test_akis_sonunda_zincirde_sekiz_kayit_var(akis):
    # 4 demo onayı (23377K, 81733D, 85285E, 23377J) + v2 onayı + hatalı CoC kararı
    # + temiz CoC kararı + M&P incelemesinin kapatılması (revizyon yüklemesi deftere yazmaz)
    assert adim(akis, "zincir").kayit_sayisi == 8
    assert adim(akis, "kayit_turleri") == ["onay"] * 5 + ["karar", "karar", "onay"]


# --- gözden geçirme düzeltmeleri: sanal ortam ve main'in kurulum yolu (sahte subprocess) -------


class SahteAltSurec:
    """subprocess.check_call / call yerine geçer; komutları kaydeder, ağa ve pip'e çıkmaz."""

    def __init__(self, demo, venv: Path, hata_verecek: int | None = None, cikis_kodu: int = 0):
        self.demo, self.venv = demo, venv
        self.komutlar: list[list[str]] = []
        self.call_cagrilari: list[tuple[list[str], dict]] = []
        self.hata_verecek = hata_verecek  # bu sıradaki check_call CalledProcessError verir
        self.cikis_kodu = cikis_kodu
        self.isaret_anlari: list[bool] = []  # her check_call anında kurulum işareti var mıydı

    def check_call(self, komut, *a, **k):
        komut = [str(x) for x in komut]
        self.komutlar.append(komut)
        self.isaret_anlari.append((self.venv / ".malzeme_kabul_kurulum").exists())
        if self.hata_verecek is not None and len(self.komutlar) - 1 == self.hata_verecek:
            raise subprocess.CalledProcessError(1, komut)
        if komut[1:3] == ["-m", "venv"]:
            _venv_hazirla(self.demo, Path(komut[3]))
        return 0

    def call(self, komut, *a, **k):
        self.call_cagrilari.append(([str(x) for x in komut], k))
        return self.cikis_kodu


@pytest.fixture
def sahte_alt_surec(monkeypatch, tmp_path, alt_surec_yasak):
    demo = demo_betigi()
    venv = tmp_path / ".venv"

    def kur(**ayar):
        s = SahteAltSurec(demo, venv, **ayar)
        monkeypatch.setattr(subprocess, "check_call", s.check_call)
        monkeypatch.setattr(subprocess, "call", s.call)
        return s

    return demo, venv, kur


def test_sanal_ortam_yoksa_once_venv_olusturulur(sahte_alt_surec, sahte_kok):
    demo, venv, kur = sahte_alt_surec
    s = kur()
    demo._sanal_ortami_hazirla(venv, sahte_kok)
    assert s.komutlar[0][1:] == ["-m", "venv", str(venv)]


def test_sanal_ortam_hazirlaninca_kurulum_komutlari_sirayla_calisir(sahte_alt_surec, sahte_kok):
    demo, venv, kur = sahte_alt_surec
    s = kur()
    demo._sanal_ortami_hazirla(venv, sahte_kok)
    beklenen = [[str(x) for x in k] for k in demo.kurulum_komutlari(demo.venv_python(venv), sahte_kok)]
    assert s.komutlar[1:] == beklenen


def test_kurulum_isareti_komutlar_basarili_olduktan_sonra_yazilir(sahte_alt_surec, sahte_kok):
    demo, venv, kur = sahte_alt_surec
    s = kur()
    demo._sanal_ortami_hazirla(venv, sahte_kok)
    assert not any(s.isaret_anlari)
    assert (venv / ".malzeme_kabul_kurulum").read_text(encoding="utf-8").strip() == demo.kilit_ozeti(sahte_kok)


@pytest.mark.parametrize("hatali_sira", [1, 2])  # 1: kilitli bağımlılıklar, 2: paketin kendisi
def test_pip_komutu_basarisiz_olursa_kurulum_isareti_yazilmaz(sahte_alt_surec, sahte_kok, hatali_sira):
    demo, venv, kur = sahte_alt_surec
    kur(hata_verecek=hatali_sira)
    try:
        demo._sanal_ortami_hazirla(venv, sahte_kok)
    except (subprocess.CalledProcessError, SystemExit):
        pass
    assert not (venv / ".malzeme_kabul_kurulum").exists()


def test_pip_basarisiz_olursa_eski_kurulum_isareti_guncellenmez(sahte_alt_surec, sahte_kok):
    demo, venv, kur = sahte_alt_surec
    _venv_hazirla(demo, venv)
    (venv / ".malzeme_kabul_kurulum").write_text("eski-ozet", encoding="utf-8")
    kur(hata_verecek=0)
    try:
        demo._sanal_ortami_hazirla(venv, sahte_kok)
    except (subprocess.CalledProcessError, SystemExit):
        pass
    assert (venv / ".malzeme_kabul_kurulum").read_text(encoding="utf-8") == "eski-ozet"


def test_kurulum_isareti_guncelse_pip_cagrilmaz(sahte_alt_surec, sahte_kok):
    demo, venv, kur = sahte_alt_surec
    _venv_hazirla(demo, venv)
    (venv / ".malzeme_kabul_kurulum").write_text(demo.kilit_ozeti(sahte_kok), encoding="utf-8")
    s = kur()
    demo._sanal_ortami_hazirla(venv, sahte_kok)
    assert s.komutlar == []


def test_main_kurulumdan_sonra_kendini_venv_pythonuyla_kurulum_yok_ekleyerek_calistirir(
        sahte_alt_surec, monkeypatch, tmp_path):
    demo, venv, kur = sahte_alt_surec
    s = kur(cikis_kodu=7)
    hazirlanan = []
    monkeypatch.setattr(demo, "_venv_icinde_mi", lambda v: False)
    monkeypatch.setattr(demo, "_sanal_ortami_hazirla", lambda v, k: hazirlanan.append(Path(v)))
    monkeypatch.setattr(demo, "demo_kur", lambda *a, **k: pytest.fail("üst süreç demo kurmamalı"))
    argumanlar = ["--yalniz-kur", "--port", "8502", "--venv", str(venv)]
    assert demo.main(argumanlar) == 7
    assert hazirlanan == [venv]
    assert len(s.call_cagrilari) == 1
    komut, _ = s.call_cagrilari[0]
    assert komut[0] == str(demo.venv_python(venv))
    assert Path(komut[1]).resolve() == DEMO_BETIGI.resolve()
    assert komut[2:] == argumanlar + ["--kurulum-yok"]


def test_main_yeniden_calistirilan_surec_ctrl_c_ile_kesilince_0_doner(sahte_alt_surec, monkeypatch):
    demo, venv, kur = sahte_alt_surec
    kur()
    monkeypatch.setattr(demo, "_venv_icinde_mi", lambda v: False)
    monkeypatch.setattr(demo, "_sanal_ortami_hazirla", lambda v, k: None)

    def kesildi(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "call", kesildi)
    assert demo.main(["--venv", str(venv)]) == 0


def test_main_kurulum_yok_ile_streamlit_i_demo_veritabani_ortamiyla_baslatir(sahte_alt_surec, monkeypatch, tmp_path):
    demo, _, kur = sahte_alt_surec
    s = kur(cikis_kodu=0)
    _, _, klasor = sahte_demo_kur_ayarla(monkeypatch, tmp_path)
    assert demo.main(["--kurulum-yok", "--port", "8503"]) == 0
    assert len(s.call_cagrilari) == 1
    komut, k = s.call_cagrilari[0]
    assert komut == [str(x) for x in demo.streamlit_komutu(Path(sys.executable), KOK, 8503)]
    assert Path(k["env"]["MALZEME_KABUL_DB"]) == klasor / "katalog.sqlite"


def test_main_streamlit_ctrl_c_ile_durdurulunca_0_doner(alt_surec_yasak, monkeypatch, tmp_path):
    demo, _, _ = sahte_demo_kur_ayarla(monkeypatch, tmp_path)

    def kesildi(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "call", kesildi)
    assert demo.main(["--kurulum-yok"]) == 0


# --- gözden geçirme düzeltmeleri: SQLite günlük dosyaları --------------------------------------


@pytest.mark.parametrize("ek", ["-journal", "-wal", "-shm"])
def test_sifirla_oncesindeki_sqlite_gunluk_dosyasi_silinir(tmp_path, capsys, ek):
    k, _ = kur(tmp_path, capsys)
    gunluk = Path(f"{k.db}{ek}")
    gunluk.write_bytes(b"eski kurulumdan kalan bozuk gunluk")
    demo_betigi().demo_kur(tmp_path / "demo", KOK, sifirla=True)
    assert not gunluk.exists() or gunluk.read_bytes() != b"eski kurulumdan kalan bozuk gunluk"


def test_yarim_kalmis_kurulumun_gecici_dosyalari_yeni_kurulumda_temizlenir(tmp_path):
    klasor = tmp_path / "demo"
    klasor.mkdir()
    for ad in ("katalog.sqlite.kuruluyor", "katalog.sqlite.kuruluyor-journal", "katalog.sqlite.kuruluyor-wal"):
        (klasor / ad).write_bytes(b"yarim kurulum")
    demo_betigi().demo_kur(klasor, KOK)
    artiklar = [p.name for p in klasor.rglob("*") if ".kuruluyor" in p.name or p.name.endswith("-journal")]
    assert artiklar == []


def test_yeni_kurulumdan_sonra_gecici_ya_da_gunluk_dosyasi_kalmaz(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    artiklar = [p.name for p in (tmp_path / "demo").rglob("*") if ".kuruluyor" in p.name or p.name.endswith("-journal")]
    assert artiklar == []


# --- gözden geçirme düzeltmeleri: klasör koruması ----------------------------------------------


class YazmaGirisimi(Exception):
    """Reddedilmesi gereken klasöre yazma girişimi (test güvenlik ağı)."""


@pytest.fixture
def yazma_yasak(monkeypatch):
    """Dosya sistemine ve SQLite'a yazmayı yasaklar: koruma çalışmasa bile depoya bir şey yazılmaz."""
    import shutil
    import sqlite3

    def yasak(*a, **k):
        raise YazmaGirisimi(f"yazma girişimi: {a!r}")

    gercek_open, gercek_io_open = builtins.open, io.open

    def salt_okunur(asil):
        def ac(dosya, mode="r", *a, **k):
            if any(c in mode for c in "wax+"):
                raise YazmaGirisimi(f"yazma kipinde açma: {dosya!r}")
            return asil(dosya, mode, *a, **k)
        return ac

    monkeypatch.setattr(builtins, "open", salt_okunur(gercek_open))
    monkeypatch.setattr(io, "open", salt_okunur(gercek_io_open))
    for ad in ("mkdir", "unlink", "rmdir", "write_text", "write_bytes", "touch", "rename", "replace"):
        monkeypatch.setattr(Path, ad, yasak)
    for ad in ("open", "remove", "unlink", "replace", "rename", "makedirs", "mkdir", "rmdir", "chmod"):
        monkeypatch.setattr(os, ad, yasak)
    for ad in ("rmtree", "copyfile", "copy", "copy2", "copytree", "move"):
        monkeypatch.setattr(shutil, ad, yasak)
    monkeypatch.setattr(sqlite3, "connect", yasak)


REDDEDILEN_KLASORLER = ["data/gold", "data/gold/alt", "data/raw", ".", "src", "data", "data/calisma/../gold",
                        "data/calismax/demo"]


@pytest.mark.parametrize("goreli", REDDEDILEN_KLASORLER)
def test_demo_kur_depo_icinde_data_calisma_disindaki_klasoru_reddeder(goreli, yazma_yasak):
    gold_once = klasor_goruntusu(KOK / "data" / "gold")
    with pytest.raises(ValueError):
        demo_betigi().demo_kur(KOK / goreli, KOK)
    assert klasor_goruntusu(KOK / "data" / "gold") == gold_once
    assert not (KOK / goreli / "katalog.sqlite").exists()


@pytest.mark.parametrize("goreli", REDDEDILEN_KLASORLER)
def test_main_depo_icinde_data_calisma_disindaki_klasoru_2_ile_reddeder(goreli, yazma_yasak, alt_surec_yasak, capsys):
    kod = demo_betigi().main(["--kurulum-yok", "--yalniz-kur", "--klasor", str(KOK / goreli)])
    cikti = capsys.readouterr()
    assert kod == 2
    assert "data/calisma" in cikti.out + cikti.err


def test_demo_kur_data_calisma_altindaki_klasoru_kabul_eder(capsys):
    import shutil
    import uuid

    klasor = KOK / "data" / "calisma" / f"demo_test_{uuid.uuid4().hex[:8]}"
    try:
        k = demo_betigi().demo_kur(klasor, KOK)
        assert k.yeni_kuruldu is True and Path(k.db).is_file()
    finally:
        shutil.rmtree(klasor, ignore_errors=True)


def test_demo_kur_depo_disindaki_klasoru_kabul_eder(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    assert k.yeni_kuruldu is True


# --- gözden geçirme düzeltmeleri: var olan demoda eksik dosyalar ------------------------------


@pytest.mark.parametrize("ad", list(DEMO_DOSYALARI))
def test_var_olan_demoda_eksik_demo_dosyasi_yeniden_kopyalanir(tmp_path, capsys, ad):
    k, _ = kur(tmp_path, capsys)
    db_once = dosya_ozeti(Path(k.db))
    (Path(k.dosyalar) / ad).unlink()
    ikinci = demo_betigi().demo_kur(tmp_path / "demo", KOK)
    assert ikinci.yeni_kuruldu is False
    assert (Path(k.dosyalar) / ad).is_file(), f"{ad} yeniden kopyalanmadı"
    assert dosya_ozeti(Path(k.dosyalar) / ad) == dosya_ozeti(DEMO_DOSYALARI[ad])
    assert dosya_ozeti(Path(k.db)) == db_once


def _parola_ve_sifirla_satiri(metin: str, tmp_path: Path) -> bool:
    """Parolaya değinen ve --sifirla öneren bir satır var mı (yollar çıkarılır: tmp adı 'parola' içerebilir)."""
    metin = metin.replace(str(tmp_path), "<tmp>")
    return any("parola" in s.lower() and "--sifirla" in s for s in metin.splitlines())


def test_parola_dosyasi_eksikse_demo_kur_sifirla_onerir_ve_parola_uretmez(tmp_path, capsys):
    k, _ = kur(tmp_path, capsys)
    db_once = dosya_ozeti(Path(k.db))
    Path(k.parola_dosyasi).unlink()
    ikinci = demo_betigi().demo_kur(tmp_path / "demo", KOK)
    cikti = capsys.readouterr()
    assert ikinci.yeni_kuruldu is False
    assert _parola_ve_sifirla_satiri(cikti.out + "\n" + cikti.err, tmp_path)
    assert not Path(k.parola_dosyasi).exists()
    assert dosya_ozeti(Path(k.db)) == db_once


def test_parola_dosyasi_eksikse_main_sifirla_onerir_ve_parola_uretmez(tmp_path, capsys, alt_surec_yasak):
    k, _ = kur(tmp_path, capsys)
    Path(k.parola_dosyasi).unlink()
    demo_betigi().main(["--kurulum-yok", "--yalniz-kur", "--klasor", str(tmp_path / "demo")])
    cikti = capsys.readouterr()
    assert _parola_ve_sifirla_satiri(cikti.out + "\n" + cikti.err, tmp_path)
    assert not Path(k.parola_dosyasi).exists()


# --- gözden geçirme düzeltmeleri: --sifirla sırasında veritabanı silinemezse -------------------


def test_sifirla_veritabani_silinemezse_main_2_doner_ve_uygulamayi_kapat_der(tmp_path, capsys, monkeypatch,
                                                                             alt_surec_yasak):
    k, _ = kur(tmp_path, capsys)
    db_once = dosya_ozeti(Path(k.db))
    gercek_unlink, gercek_remove, gercek_os_unlink = Path.unlink, os.remove, os.unlink

    def kilitli(yol) -> bool:
        return Path(yol).name.startswith("katalog.sqlite")

    def path_unlink(self, *a, **kw):
        if kilitli(self):
            raise PermissionError(13, "dosya başka bir süreçte açık", str(self))
        return gercek_unlink(self, *a, **kw)

    def os_sil(asil):
        def sil(yol, *a, **kw):
            if kilitli(yol):
                raise PermissionError(13, "dosya başka bir süreçte açık", str(yol))
            return asil(yol, *a, **kw)
        return sil

    monkeypatch.setattr(Path, "unlink", path_unlink)
    monkeypatch.setattr(os, "remove", os_sil(gercek_remove))
    monkeypatch.setattr(os, "unlink", os_sil(gercek_os_unlink))
    kod = demo_betigi().main(["--kurulum-yok", "--yalniz-kur", "--sifirla", "--klasor", str(tmp_path / "demo")])
    cikti = capsys.readouterr()
    assert kod == 2
    assert "uygulamayı kapat" in cikti.out + cikti.err
    assert dosya_ozeti(Path(k.db)) == db_once


# --- belgeler ------------------------------------------------------------------------------------

SENARYO = KOK / "docs" / "demo_senaryosu.md"


def test_readme_tek_komutla_demo_bolumu_ve_komutu_icerir():
    metin = (KOK / "README.md").read_text(encoding="utf-8")
    assert "python scripts/demo.py" in metin
    baslik = re.search(r"^#{2,4}\s*Tek komutla demo", metin, re.MULTILINE)
    assert baslik, "README'de 'Tek komutla demo' başlığı yok"
    kurulum = re.search(r"^##\s*Kurulum ve kullanım", metin, re.MULTILINE)
    docker = re.search(r"^###\s*Ağsız Docker", metin, re.MULTILINE)
    assert kurulum and docker
    assert baslik.start() < docker.start()


def senaryo() -> str:
    assert SENARYO.is_file(), "docs/demo_senaryosu.md henüz yok"
    return SENARYO.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "adim_adi, anahtarlar",
    [
        ("standart yükle", ["standart", "yükle"]),
        ("kabul dokümanı onayla", ["kabul dokümanı", "onayla"]),
        ("hatalı CoC yükle", ["hatalı coc"]),
        ("karar ve madde referansı", ["karar", "3.7.2"]),
        ("revizyon etkisi", ["revizyon etkisi"]),
        ("denetim kaydı doğrulama", ["denetim kaydı", "denetim_dogrula.py"]),
    ],
)
def test_senaryo_alti_adimin_her_birini_anlatir(adim_adi, anahtarlar):
    metin = senaryo().lower()
    eksik = [a for a in anahtarlar if a not in metin]
    assert not eksik, f"'{adim_adi}' adımı için eksik: {eksik}"


def test_senaryo_demo_onayi_isaretinden_soz_eder():
    assert "DEMO ONAYI" in senaryo()


ARALIK = re.compile(r"\((\d+):(\d{2})\s*[–-]\s*(\d+):(\d{2})\)")


def senaryo_araliklari() -> list[tuple[int, int]]:
    return [(int(a) * 60 + int(b), int(c) * 60 + int(d)) for a, b, c, d in ARALIK.findall(senaryo())]


def test_senaryo_her_adim_icin_sure_araligi_verir():
    assert len(senaryo_araliklari()) >= 6


def test_senaryo_sure_araliklari_sirali_ve_gecerli():
    araliklar = senaryo_araliklari()
    assert araliklar
    for bas, son in araliklar:
        assert bas < son
    for (_, onceki_son), (sonraki_bas, _) in zip(araliklar, araliklar[1:]):
        assert sonraki_bas >= onceki_son


def test_senaryo_toplam_suresi_iki_dakikayi_gecmez():
    araliklar = senaryo_araliklari()
    assert araliklar
    assert max(son for _, son in araliklar) <= 120


@pytest.mark.parametrize("goreli", ["data/gold", "data/gold/venv", "data/raw", "src", ".venvx"])
def test_main_depo_icinde_venv_yalniz_kok_venv_ya_da_data_calisma_altinda_olabilir(
        goreli, yazma_yasak, alt_surec_yasak, capsys):
    kod = demo_betigi().main(["--yalniz-kur", "--venv", str(KOK / goreli)])
    cikti = capsys.readouterr()
    assert kod == 2
    assert ".venv" in cikti.out + cikti.err
