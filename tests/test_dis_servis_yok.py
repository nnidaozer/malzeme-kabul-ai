"""src/ altında dış servis kütüphanesi kullanılmadığını denetler.

Kural (CLAUDE.md, 4): sistemin içindeki dil modeli yerel çalışır, dış API
kullanılmaz.

- Bulut LLM SDK'ları (openai, anthropic ...) src/ altında hiçbir yerde içe
  aktarılamaz.
- Genel HTTP/ağ kütüphaneleri (requests, httpx, urllib.request ...) yalnızca
  YEREL_MODEL_ISTISNALARI içindeki dosyalarda kullanılabilir. Bu dosyalardaki
  her http(s) adresi localhost'a gitmelidir. Tek istisna yerel model
  istemcisidir (malzeme_kabul/cikarim/yerel_model.py).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

KOK = Path(__file__).resolve().parents[1]
SRC = KOK / "src"

# Hiçbir koşulda izin verilmeyen bulut LLM / dış servis SDK'ları.
YASAK_SDKLAR = {
    "openai", "anthropic", "cohere", "mistralai", "groq", "together",
    "replicate", "google.generativeai", "google.genai", "vertexai",
    "boto3", "botocore", "azure", "huggingface_hub", "litellm",
    "langchain_openai", "langchain_anthropic", "langchain_google_genai",
    "langchain_community", "llama_index.llms.openai",
}
# Yalnızca yerel model istisnasında (localhost) izin verilen ağ kütüphaneleri.
AG_KUTUPHANELERI = {
    "requests", "httpx", "aiohttp", "urllib3", "urllib.request", "http.client",
    "socket", "websocket", "websockets", "grpc", "pycurl", "ftplib", "smtplib",
}
# src/ altına göre yollar: yalnız localhost'a bağlanan yerel model istemcisi.
YEREL_MODEL_ISTISNALARI: set[str] = {"malzeme_kabul/cikarim/yerel_model.py"}
YEREL_ADRESLER = {"localhost", "127.0.0.1", "::1"}


def ice_aktarilan_moduller(kaynak: str) -> set[str]:
    """Kaynak koddaki import, from-import, __import__ ve importlib çağrılarını toplar."""
    moduller: set[str] = set()
    for dugum in ast.walk(ast.parse(kaynak)):
        if isinstance(dugum, ast.Import):
            moduller.update(a.name for a in dugum.names)
        elif isinstance(dugum, ast.ImportFrom) and dugum.module and dugum.level == 0:
            moduller.add(dugum.module)
            # from urllib import request -> urllib.request
            moduller.update(f"{dugum.module}.{a.name}" for a in dugum.names)
        elif isinstance(dugum, ast.Call) and dugum.args:
            ad = ast.unparse(dugum.func)
            ilk = dugum.args[0]
            if ad in {"__import__", "importlib.import_module", "import_module"} and isinstance(
                ilk, ast.Constant
            ) and isinstance(ilk.value, str):
                moduller.add(ilk.value)
    return moduller


def eslesir_mi(modul: str, yasaklar: set[str]) -> bool:
    """`modul` yasak listesindeki bir paketin kendisi ya da alt modülü mü?"""
    return any(modul == y or modul.startswith(y + ".") for y in yasaklar)


def yerel_olmayan_adresler(kaynak: str) -> list[str]:
    """Kaynaktaki metin sabitlerinde localhost dışına giden http(s)/ws adreslerini döner."""
    adresler = []
    for dugum in ast.walk(ast.parse(kaynak)):
        if isinstance(dugum, ast.Constant) and isinstance(dugum.value, str):
            for url in re.findall(r"(?:https?|wss?)://[^\s'\"<>]+", dugum.value):
                if urlparse(url).hostname not in YEREL_ADRESLER:
                    adresler.append(url)
    return adresler


def ihlaller(kaynak: str, istisna: bool) -> list[str]:
    """Bir kaynak dosyadaki kural ihlallerini açıklamalarıyla döner."""
    sonuc = []
    for modul in sorted(ice_aktarilan_moduller(kaynak)):
        if eslesir_mi(modul, YASAK_SDKLAR):
            sonuc.append(f"dış servis SDK'sı içe aktarılıyor: {modul}")
        elif eslesir_mi(modul, AG_KUTUPHANELERI) and not istisna:
            sonuc.append(f"ağ kütüphanesi yerel model istisnası dışında kullanılıyor: {modul}")
    if istisna:
        sonuc.extend(f"localhost dışı adres: {u}" for u in yerel_olmayan_adresler(kaynak))
    return sonuc


def src_dosyalari() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


# --- Denetleyicinin kendi testleri -------------------------------------------


@pytest.mark.parametrize(
    "kaynak",
    [
        "import openai",
        "from anthropic import Anthropic",
        "import google.generativeai as genai",
        "from google import genai",
        "__import__('openai')",
        "import importlib\nimportlib.import_module('anthropic')",
        "def f():\n    import cohere",
    ],
)
def test_bulut_sdk_her_yerde_yakalanir(kaynak):
    assert ihlaller(kaynak, istisna=False)
    assert ihlaller(kaynak, istisna=True)


@pytest.mark.parametrize(
    "kaynak",
    [
        "import requests",
        "import httpx",
        "from urllib import request",
        "import urllib.request",
        "from http.client import HTTPConnection",
        "import aiohttp",
    ],
)
def test_ag_kutuphanesi_istisna_disinda_yakalanir(kaynak):
    assert ihlaller(kaynak, istisna=False)


@pytest.mark.parametrize(
    "kaynak",
    [
        "import json, re, math",
        "from pathlib import Path",
        "from urllib.parse import urlparse",
        "from . import birimler",
        "import malzeme_kabul",
    ],
)
def test_yerel_kutuphaneler_serbest(kaynak):
    assert ihlaller(kaynak, istisna=False) == []


@pytest.mark.parametrize(
    "url",
    ["http://localhost:11434/api/generate", "http://127.0.0.1:8080/v1", "http://[::1]:11434"],
)
def test_istisnada_localhost_adresi_serbest(url):
    kaynak = f"import httpx\nURL = '{url}'"
    assert ihlaller(kaynak, istisna=True) == []


@pytest.mark.parametrize(
    "url",
    ["https://api.openai.com/v1", "http://192.168.1.10:11434", "https://localhost.evil.com"],
)
def test_istisnada_localhost_disi_adres_yakalanir(url):
    kaynak = f"import httpx\nURL = '{url}'"
    assert ihlaller(kaynak, istisna=True)


# --- Asıl kural -----------------------------------------------------------------


def test_istisna_listesindeki_dosyalar_var():
    eksik = [y for y in YEREL_MODEL_ISTISNALARI if not (SRC / y).is_file()]
    assert not eksik, f"YEREL_MODEL_ISTISNALARI içinde olmayan dosyalar: {eksik}"


def test_src_dis_servis_kullanmaz():
    bulunan = {}
    for dosya in src_dosyalari():
        goreli = dosya.relative_to(SRC).as_posix()
        hatalar = ihlaller(dosya.read_text(encoding="utf-8"), goreli in YEREL_MODEL_ISTISNALARI)
        if hatalar:
            bulunan[goreli] = hatalar
    assert not bulunan, f"Dış servis kuralı ihlali (CLAUDE.md, kural 4): {bulunan}"


# --- Alt süreç yalnız OCR katmanında (docs/ocr.md) ------------------------------------

# Dış program çalıştırma yalnız yerel Tesseract'ı çağıran OCR katmanında serbest.
ALT_SUREC_ISTISNALARI: set[str] = {"malzeme_kabul/belge/ocr.py"}
ALT_SUREC_MODULLERI = {"subprocess", "asyncio.subprocess", "pty"}
ALT_SUREC_CAGRILARI = {"os.system", "os.popen", "os.spawnl", "os.spawnv", "os.execv", "os.execl",
                       "os.posix_spawn", "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell"}


def alt_surec_ihlalleri(kaynak: str) -> list[str]:
    """subprocess içe aktarımı ve os.system / os.popen gibi dış program çağrıları."""
    sonuc = [f"alt süreç modülü: {m}" for m in sorted(ice_aktarilan_moduller(kaynak))
             if eslesir_mi(m, ALT_SUREC_MODULLERI) or m in ALT_SUREC_CAGRILARI]
    for dugum in ast.walk(ast.parse(kaynak)):
        if isinstance(dugum, ast.Attribute) and ast.unparse(dugum) in ALT_SUREC_CAGRILARI:
            sonuc.append(f"dış program çağrısı: {ast.unparse(dugum)}")
    return sonuc


@pytest.mark.parametrize(
    "kaynak",
    [
        "import subprocess",
        "from subprocess import run",
        "import os\nos.system('ls')",
        "import os\nos.popen('ls')",
        "from os import system",
        "from os import popen",
        "__import__('subprocess')",
        "def f():\n    import subprocess as sp",
    ],
)
def test_alt_surec_kullanimi_yakalanir(kaynak):
    assert alt_surec_ihlalleri(kaynak)


@pytest.mark.parametrize("kaynak", ["import os\nos.path.join('a', 'b')", "import shutil\nshutil.which('x')",
                                    "from os import environ"])
def test_alt_surec_olmayan_os_kullanimi_serbest(kaynak):
    assert alt_surec_ihlalleri(kaynak) == []


def test_alt_surec_istisnasi_var():
    assert all((SRC / y).is_file() for y in ALT_SUREC_ISTISNALARI)


def test_src_alt_sureci_yalniz_ocr_katmaninda_kullanir():
    bulunan = {}
    for dosya in src_dosyalari():
        goreli = dosya.relative_to(SRC).as_posix()
        if goreli in ALT_SUREC_ISTISNALARI:
            continue
        hatalar = alt_surec_ihlalleri(dosya.read_text(encoding="utf-8"))
        if hatalar:
            bulunan[goreli] = hatalar
    assert not bulunan, f"src/ altında alt süreç yalnız malzeme_kabul/belge/ocr.py içinde kullanılabilir: {bulunan}"
