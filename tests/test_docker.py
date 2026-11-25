"""Ağsız Docker yapılandırmasının ve ağ denetim betiklerinin testleri.

Asıl uçtan uca test `scripts/ag_testi.sh`'tir (CI'da `ag-testi` işi): imajı
kurar, uygulamayı docker compose ile kaldırır, konteynerden dışarı
çıkılamadığını ve uygulamanın 127.0.0.1:8501'den çalıştığını gösterir. Buradaki
testler Docker'sız çalışır.
"""

from __future__ import annotations

import re
import socket
import threading

import pytest

from tests.conftest import KOK, betik_yukle

COMPOSE = (KOK / "docker-compose.yml").read_text(encoding="utf-8")
DOCKERFILE = (KOK / "Dockerfile").read_text(encoding="utf-8")
DOCKERIGNORE = (KOK / ".dockerignore").read_text(encoding="utf-8").splitlines()


def servis(ad: str) -> str:
    m = re.search(rf"^  {ad}:\n((?:    .*\n|\s*\n)*)", COMPOSE, re.MULTILINE)
    assert m, f"servis yok: {ad}"
    return m.group(1)


def test_ic_ag_disa_kapali():
    assert re.search(r"^  ic:\n    internal: true", COMPOSE, re.MULTILINE)


def test_uygulama_yalniz_ic_agda_ve_port_acmaz():
    u = servis("uygulama")
    assert "networks: [ic]" in u and "ports" not in u and "network_mode" not in u


def test_kapi_yalniz_localhosta_acilir():
    k = servis("kapi")
    assert '"127.0.0.1:8501:8501"' in k and "yerel_kapi.py" in k
    assert not re.search(r'^\s*- "?8501', k, re.MULTILINE)  # 0.0.0.0'a açılmaz


def test_model_uygulamanin_ag_ad_alanini_paylasir():
    m = servis("model")
    assert 'network_mode: "service:uygulama"' in m and "profiles: [model]" in m and "ports" not in m


def test_dockerfile_kilitten_kurar_ve_root_olarak_calismaz():
    assert "pip install -r requirements-arayuz.lock" in DOCKERFILE
    assert "pip install --no-deps ." in DOCKERFILE
    assert re.search(r"^USER uygulama$", DOCKERFILE, re.MULTILINE)
    assert "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false" in DOCKERFILE  # Streamlit dışarı istatistik yollamaz


@pytest.mark.parametrize("klasor", ["data/gold", "data/gold_codex", "data/gold_taslak", "data/raw", "data/calisma", "deney", "tests"])
def test_imaja_girmeyenler(klasor):
    assert klasor in DOCKERIGNORE


def test_ag_testi_betigi_uc_denetimi_yapar():
    betik = (KOK / "scripts/ag_testi.sh").read_text(encoding="utf-8")
    assert "ag_kapali_mi.py" in betik and "/proc/net/route" in betik and "_stcore/health" in betik


# --- ag_kapali_mi.py ---------------------------------------------------------------------


def test_ag_kapaliysa_sifir_doner(monkeypatch, capsys):
    betik = betik_yukle("scripts/ag_kapali_mi.py")

    def kapali(*a, **k):
        raise OSError("ağ yok")

    monkeypatch.setattr(betik.socket, "gethostbyname", kapali)
    monkeypatch.setattr(betik.socket, "create_connection", kapali)
    monkeypatch.setattr(betik.urllib.request.OpenerDirector, "open", kapali)
    assert betik.main() == 0
    assert "ağ kapalı" in capsys.readouterr().out


def test_tek_cikis_bile_yakalanir(monkeypatch, capsys):
    betik = betik_yukle("scripts/ag_kapali_mi.py")

    def kapali(*a, **k):
        raise OSError("ağ yok")

    class Baglanti:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(betik.socket, "gethostbyname", kapali)
    monkeypatch.setattr(betik.socket, "create_connection",
                        lambda adres, timeout: Baglanti() if adres == ("8.8.8.8", 53) else kapali())
    monkeypatch.setattr(betik.urllib.request.OpenerDirector, "open", kapali)
    assert betik.main() == 1
    assert "AÇIK   TCP 8.8.8.8:53" in capsys.readouterr().out


# --- yerel_kapi.py -----------------------------------------------------------------------


def test_yerel_kapi_baglantiyi_yalniz_hedefe_aktarir(monkeypatch):
    kapi = betik_yukle("docker/yerel_kapi.py")
    hedef = socket.create_server(("127.0.0.1", 0))
    monkeypatch.setattr(kapi, "HEDEF", ("127.0.0.1", hedef.getsockname()[1]))

    def yankici():
        b, _ = hedef.accept()
        b.sendall(b"yanit:" + b.recv(100))
        b.close()

    threading.Thread(target=yankici, daemon=True).start()
    a, b = socket.socketpair()
    kapi._baglanti(b)
    a.sendall(b"merhaba")
    a.settimeout(5)
    assert a.recv(100) == b"yanit:merhaba"
    a.close()
    hedef.close()


# --- varsayılan parola yok (Nida: "Docker'da varsayılan parola olmasın") -------------------

BASLAT = (KOK / "docker/baslat.sh").read_text(encoding="utf-8")


@pytest.mark.parametrize("dosya", ["docker-compose.yml", "Dockerfile", "docker/baslat.sh"])
def test_docker_dosyalarinda_deneme_parolasi_gecmez(dosya):
    metin = (KOK / dosya).read_text(encoding="utf-8")
    assert "ornek-parola" not in metin
    assert "--ornek-kullanicilar" not in metin


@pytest.mark.parametrize("dosya", ["docker-compose.yml", "Dockerfile", "docker/baslat.sh"])
def test_docker_yolunda_deneme_kullanicisi_degiskeni_yok(dosya):
    assert "MALZEME_KABUL_ORNEK_KULLANICILAR" not in (KOK / dosya).read_text(encoding="utf-8")


def test_dockerfile_parola_ortam_degiskeni_tanimlamaz():
    assert "PAROLA" not in DOCKERFILE.upper().replace("PAROLASI_DOSYASI", "")  # ne ENV ne ARG ile parola


@pytest.mark.parametrize("rol", ["MP", "GK"])
def test_compose_parolayi_zorunlu_ister_ya_da_secrets_kullanir(rol):
    u = servis("uygulama")
    zorunlu = re.search(rf"MALZEME_KABUL_{rol}_PAROLASI:\s*\$\{{MALZEME_KABUL_{rol}_PAROLASI:\?[^}}]+\}}", u)
    gizli = re.search(rf"MALZEME_KABUL_{rol}_PAROLASI_DOSYASI:\s*/run/secrets/\S+", u) and re.search(r"^secrets:", COMPOSE, re.MULTILINE)
    assert zorunlu or gizli, f"{rol} parolası compose'da zorunlu değil"


def duz_metin_varsayilan_var_mi(metin: str, rol: str) -> bool:
    """Compose metninde {rol} parolasına varsayılan ya da düz metin değer verilmiş mi?

    Anahtar satır başına bağlanır (yorumlar ve `${...}` içindeki ad sayılmaz).
    İzinli tek değer biçimi zorunlu değişkendir: `${MALZEME_KABUL_{rol}_PAROLASI:?mesaj}`
    (ya da `?mesaj`). `:-varsayilan`, `-varsayilan` ve düz değer reddedilir.
    """
    ad = f"MALZEME_KABUL_{rol}_PAROLASI"
    zorunlu = rf"[\"']?\$\{{{ad}:?\?[^}}]*\}}[\"']?"
    for satir in metin.splitlines():
        if re.match(r"^\s*#", satir):
            continue
        # anahtar: değer (eşleme biçimi) ya da - AD=değer (liste biçimi)
        m = re.match(rf"^\s+{ad}:\s*(.*?)\s*(?:#.*)?$", satir) or re.match(rf"^\s+-\s*[\"']?{ad}=(.*?)[\"']?\s*$", satir)
        if m and not re.fullmatch(zorunlu, m.group(1)):
            return True
        # her yerde: ${AD:-...} ya da ${AD-...} varsayılanı
        if re.search(rf"\$\{{{ad}:?-", satir):
            return True
    return False


@pytest.mark.parametrize("ornek, beklenen", [
    ("    environment:\n      MALZEME_KABUL_MP_PAROLASI: ${MALZEME_KABUL_MP_PAROLASI:?parola zorunlu}\n", False),
    ('    environment:\n      MALZEME_KABUL_MP_PAROLASI: "${MALZEME_KABUL_MP_PAROLASI:?parola zorunlu}"\n', False),
    ("    environment:\n      MALZEME_KABUL_MP_PAROLASI: ${MALZEME_KABUL_MP_PAROLASI?zorunlu}\n", False),
    ("    environment:\n      MALZEME_KABUL_MP_PAROLASI_DOSYASI: /run/secrets/mp_parolasi\n", False),
    ("      # MALZEME_KABUL_MP_PAROLASI: gizli-parola-123 (yorum)\n", False),
    ("    environment:\n      MALZEME_KABUL_MP_PAROLASI: ${MALZEME_KABUL_MP_PAROLASI:-mp-ornek-parola}\n", True),
    ("    environment:\n      MALZEME_KABUL_MP_PAROLASI: ${MALZEME_KABUL_MP_PAROLASI-mp-ornek-parola}\n", True),
    ("    environment:\n      MALZEME_KABUL_MP_PAROLASI: mp-ornek-parola\n", True),
    ('    environment:\n      MALZEME_KABUL_MP_PAROLASI: "Gercek-Parola-2026"\n', True),
    ("    environment:\n      - MALZEME_KABUL_MP_PAROLASI=mp-ornek-parola\n", True),
    ("    environment:\n      DIGER: ${MALZEME_KABUL_MP_PAROLASI:-x}\n", True),
])
def test_duz_metin_varsayilan_denetimi_zorunlu_bicimi_kabul_eder_varsayilani_reddeder(ornek, beklenen):
    assert duz_metin_varsayilan_var_mi(ornek, "MP") is beklenen


@pytest.mark.parametrize("rol", ["MP", "GK"])
def test_compose_parolaya_duz_metin_varsayilan_vermez(rol):
    assert not duz_metin_varsayilan_var_mi(COMPOSE, rol)


# --- compose secrets: kaynak yalnız host ortam değişkeni ----------------------------------

SECRETLER = {"mp_parolasi": "MALZEME_KABUL_MP_PAROLASI", "gk_parolasi": "MALZEME_KABUL_GK_PAROLASI"}


def ust_duzey_blok(metin: str, ad: str) -> list[str]:
    """Üst düzey `ad:` bloğunun satırları (sonraki üst düzey anahtara kadar; yorumsuz, boşsuz)."""
    satirlar, icinde = [], False
    for satir in metin.splitlines():
        if re.match(r"^\S", satir):
            icinde = re.match(rf"^{ad}:\s*(?:#.*)?$", satir) is not None
            continue
        if icinde and satir.strip() and not satir.lstrip().startswith("#"):
            satirlar.append(satir)
    return satirlar


def secret_kaynaklari(metin: str) -> dict[str, list[tuple[str, str]]]:
    """Üst düzey secrets: {secret adı: [(anahtar, değer), ...]}."""
    kaynaklar: dict[str, list[tuple[str, str]]] = {}
    gecerli = None
    for satir in ust_duzey_blok(metin, "secrets"):
        if m := re.match(r"^  ([A-Za-z0-9_.-]+):\s*(.*?)\s*$", satir):
            gecerli = m.group(1)
            kaynaklar[gecerli] = [("<satir-ici>", m.group(2))] if m.group(2) else []
        elif (m := re.match(r"^    ([A-Za-z_]+):\s*[\"']?(.*?)[\"']?\s*$", satir)) and gecerli:
            kaynaklar[gecerli].append((m.group(1), m.group(2)))
        else:
            kaynaklar.setdefault("<tanınmayan>", []).append(("satir", satir))
    return kaynaklar


def secret_sorunlari(metin: str) -> list[str]:
    sorunlar = []
    kaynaklar = secret_kaynaklari(metin)
    if not kaynaklar:
        return ["üst düzey secrets: yok"]
    for secret, degisken in SECRETLER.items():
        if kaynaklar.get(secret) != [("environment", degisken)]:
            sorunlar.append(f"{secret}: kaynak yalnız environment: {degisken} olmalı, bulunan {kaynaklar.get(secret)}")
    if any(anahtar == "file" for liste in kaynaklar.values() for anahtar, _ in liste):
        sorunlar.append("secrets altında file: kaynağı var")
    if re.search(r"^\s+file:", "\n".join(ust_duzey_blok(metin, "secrets")), re.MULTILINE):
        sorunlar.append("secrets altında file: satırı var")
    return sorunlar


def uygulama_secretleri(metin: str) -> set[str]:
    m = re.search(r"^  uygulama:\n((?:    .*\n|\s*\n)*)", metin, re.MULTILINE)
    if not m:
        return set()
    govde = m.group(1)
    if s := re.search(r"^    secrets:\s*\[([^\]]*)\]", govde, re.MULTILINE):
        return {x.strip().strip("\"'") for x in s.group(1).split(",") if x.strip()}
    if s := re.search(r"^    secrets:\s*\n((?:      .*\n)*)", govde, re.MULTILINE):
        return set(re.findall(r"^      -\s*[\"']?([A-Za-z0-9_.-]+)", s.group(1), re.MULTILINE))
    return set()


_IYI_SECRETS = """services:
  uygulama:
    image: x
    secrets: [mp_parolasi, gk_parolasi]

secrets:
  mp_parolasi:
    environment: MALZEME_KABUL_MP_PAROLASI
  gk_parolasi:
    environment: "MALZEME_KABUL_GK_PAROLASI"
"""


@pytest.mark.parametrize("ornek, sorunlu", [
    (_IYI_SECRETS, False),
    (_IYI_SECRETS.replace("environment: MALZEME_KABUL_MP_PAROLASI", "file: ./mp_parola.txt"), True),
    (_IYI_SECRETS.replace("environment: MALZEME_KABUL_MP_PAROLASI",
                          "environment: MALZEME_KABUL_MP_PAROLASI\n    file: ./mp_parola.txt"), True),
    (_IYI_SECRETS.replace("environment: \"MALZEME_KABUL_GK_PAROLASI\"", "environment: MALZEME_KABUL_MP_PAROLASI"), True),
    (_IYI_SECRETS.replace("  gk_parolasi:\n    environment: \"MALZEME_KABUL_GK_PAROLASI\"\n", ""), True),
    (_IYI_SECRETS.split("secrets:\n  mp")[0], True),
])
def test_secret_denetimi_yalniz_environment_kaynagini_kabul_eder(ornek, sorunlu):
    assert bool(secret_sorunlari(ornek)) is sorunlu


@pytest.mark.parametrize("ornek, beklenen", [
    (_IYI_SECRETS, {"mp_parolasi", "gk_parolasi"}),
    (_IYI_SECRETS.replace("secrets: [mp_parolasi, gk_parolasi]", "secrets:\n      - mp_parolasi\n      - gk_parolasi"),
     {"mp_parolasi", "gk_parolasi"}),
    (_IYI_SECRETS.replace("secrets: [mp_parolasi, gk_parolasi]", "secrets: [mp_parolasi]"), {"mp_parolasi"}),
])
def test_uygulama_secret_listesi_okunur(ornek, beklenen):
    assert uygulama_secretleri(ornek) == beklenen


def test_compose_secretleri_yalniz_host_ortam_degiskeninden_gelir():
    assert secret_sorunlari(COMPOSE) == []


def test_compose_secretlerinde_file_kaynagi_yok():
    assert not any(re.match(r"^\s+file:", s) for s in ust_duzey_blok(COMPOSE, "secrets"))


def test_compose_uygulama_iki_secreti_de_listeler():
    assert uygulama_secretleri(COMPOSE) >= set(SECRETLER)


@pytest.mark.parametrize("secret, rol", [("mp_parolasi", "MP"), ("gk_parolasi", "GK")])
def test_compose_uygulama_parola_dosyasini_secretten_okur(secret, rol):
    assert re.search(rf"^      MALZEME_KABUL_{rol}_PAROLASI_DOSYASI:\s*/run/secrets/{secret}\s*$", servis("uygulama"), re.MULTILINE)


# --- Docker işareti: katalog_kur.py --ornek-kullanicilar Docker'da reddedilir -----------------
# Seçim: Dockerfile ENV'de MALZEME_KABUL_DOCKER=1 (davranış testi: tests/test_ilk_kurulum.py).


def test_dockerfile_docker_isaretini_ayarlar():
    assert re.search(r"^\s*(?:ENV\s+)?MALZEME_KABUL_DOCKER=1\b", DOCKERFILE, re.MULTILINE)


def test_baslat_ilk_kurulumu_streamlitten_once_calistirir():
    assert "ilk_kurulum.py" in BASLAT
    assert BASLAT.index("ilk_kurulum.py") < BASLAT.index("streamlit run")
    assert re.search(r"^set -[a-z]*e", BASLAT, re.MULTILINE)  # hata olursa betik durur


def test_baslat_betik_yollarini_veri_kokunden_cozer():
    assert "${MALZEME_KABUL_KOK:-/uygulama}" in BASLAT


# --- imajda veri kökü (data/bolunme.yaml, data/cikti) -----------------------------------------


def test_dockerfile_veri_kokunu_ayarlar():
    assert re.search(r"MALZEME_KABUL_KOK=/uygulama\b", DOCKERFILE)


@pytest.fixture
def ekran_verisi_kokle(monkeypatch):
    """ekran_verisi'ni verilen MALZEME_KABUL_KOK ile yeniden yükler; sonra eski haline döndürür."""
    import importlib

    from malzeme_kabul.arayuz import ekran_verisi

    def yukle(kok):
        if kok is None:
            monkeypatch.delenv("MALZEME_KABUL_KOK", raising=False)
        else:
            monkeypatch.setenv("MALZEME_KABUL_KOK", str(kok))
        return importlib.reload(ekran_verisi)

    yield yukle
    monkeypatch.delenv("MALZEME_KABUL_KOK", raising=False)
    importlib.reload(ekran_verisi)


def test_kok_ortam_degiskeni_yoksa_depo_kokune_gore_cozulur(ekran_verisi_kokle):
    ev = ekran_verisi_kokle(None)
    assert ev.KOK == KOK
    assert ev.BOLUNME == KOK / "data" / "bolunme.yaml"


def test_kok_ortam_degiskeni_bolunme_yolunu_belirler(ekran_verisi_kokle, tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/bolunme.yaml").write_text("gelistirme:\n  - MIL-PRF-99999A\ntest:\n", encoding="utf-8")
    ev = ekran_verisi_kokle(tmp_path)
    assert ev.KOK == tmp_path
    assert ev.BOLUNME == tmp_path / "data" / "bolunme.yaml"
    assert ev.standart_izinli_mi("MIL-PRF-99999A") == (True, "geliştirme kümesinde")


def test_kok_ortam_degiskeni_hazir_rapor_klasorunu_belirler(ekran_verisi_kokle, tmp_path):
    (tmp_path / "data/cikti").mkdir(parents=True)
    (tmp_path / "data/cikti/ORNEK_A-B_revizyon_farklari.md").write_text("# fark\n", encoding="utf-8")
    ev = ekran_verisi_kokle(tmp_path)
    assert ev.hazir_revizyon_raporlari() == {"ORNEK_A-B": tmp_path / "data/cikti/ORNEK_A-B_revizyon_farklari.md"}


def test_kok_ortam_degiskeni_bos_klasoru_gosterirse_bolunme_yok_denir(ekran_verisi_kokle, tmp_path):
    ev = ekran_verisi_kokle(tmp_path)
    izinli, neden = ev.standart_izinli_mi("MIL-PRF-23377K")
    assert not izinli and str(tmp_path) in neden
