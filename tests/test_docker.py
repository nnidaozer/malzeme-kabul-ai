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
