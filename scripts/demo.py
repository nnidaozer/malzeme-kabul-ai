#!/usr/bin/env python3
"""Tek komutla yerel demo: sanal ortam, demo veritabanı, kullanıcılar ve Streamlit.

Kullanım:
  python scripts/demo.py                # Windows: py scripts\\demo.py
  python scripts/demo.py --sifirla      # demo veritabanını silip baştan kurar
  python scripts/demo.py --yalniz-kur   # kurar, uygulamayı başlatmaz
  python scripts/demo.py --kurulum-yok  # sanal ortam/pip adımını atlar (geçerli Python)
  python scripts/demo.py --port 8502

İlk çalıştırmada .venv'e kilitli sürümler (requirements-arayuz.lock) kurulur;
bunun için ağ gerekir. Sonraki çalıştırmalar ağsızdır. Demo verisi
data/calisma/demo/ altındadır; parolalar yalnız parolalar.txt'ye yazılır.
Uygulama yalnız 127.0.0.1'den açılır. Örnek dokümanlar DEMO ONAYI'dır
(M&P onayı değil). Ayrıntı: docs/demo_plani.md.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import secrets
import shutil
import subprocess
import sys
from dataclasses import make_dataclass
from pathlib import Path
from typing import List, Optional

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_KLASOR = KOK / "data" / "calisma" / "demo"
VARSAYILAN_VENV = KOK / ".venv"
KURULUM_ISARETI = ".malzeme_kabul_kurulum"
KILIT = "requirements-arayuz.lock"
VARSAYILAN_PORT = 8501
UYGULAMA = Path("src") / "malzeme_kabul" / "arayuz" / "uygulama.py"
SENTETIK = Path("data") / "sentetik" / "sertifikalar" / "MIL-PRF-23377K" / "pdf"
# hedef ad -> depo köküne göre kaynak
DEMO_DOSYALARI = {
    "MIL-PRF-23377K.pdf": Path("data") / "raw" / "MIL-PRF-23377K.pdf",
    "hatali_CoC_B86447.pdf": SENTETIK / "S-089.pdf",
    "temiz_CoC_B80677.pdf": SENTETIK / "S-032.pdf",
}
ORNEK_KATALOGLARI = [Path("data") / "ornek" / "katalog.json", Path("data") / "demo" / "katalog.json"]
DEMO_KULLANICILARI = [("mp", "mp"), ("gk", "giris_kalite")]


# make_dataclass: betik sys.modules'a kaydedilmeden yüklendiğinde (tests/conftest.betik_yukle)
# `from __future__ import annotations` ile @dataclass dize açıklamaları çözemez.
DemoKurulumu = make_dataclass(
    "DemoKurulumu",
    [("db", Path), ("parola_dosyasi", Path), ("dosyalar", Path), ("yeni_kuruldu", bool)],
    namespace={"__doc__": "demo_kur sonucu: veritabanı, parola dosyası, demo dosyaları klasörü."},
)
DemoKurulumu.__module__ = __name__


def python_uygun_mu(surum=sys.version_info) -> bool:
    """Python 3.11 ve üstü mü."""
    return tuple(surum[:2]) >= (3, 11)


def venv_python(venv: Path, platform: str = sys.platform) -> Path:
    """Sanal ortamın Python yorumlayıcısının yolu."""
    if platform == "win32":
        return Path(venv) / "Scripts" / "python.exe"
    return Path(venv) / "bin" / "python"


def kilit_ozeti(kok: Path) -> str:
    """Kilit dosyası ve pyproject.toml içeriğinin sha256'sı."""
    h = hashlib.sha256()
    for ad in (KILIT, "pyproject.toml"):
        h.update(ad.encode("utf-8") + b"\0")
        h.update((Path(kok) / ad).read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def kurulum_gerekli_mi(venv: Path, kok: Path) -> bool:
    """Sanal ortam yoksa ya da işaretteki özet kilitlerle uyuşmuyorsa True."""
    venv = Path(venv)
    isaret = venv / KURULUM_ISARETI
    if not venv_python(venv).is_file() or not isaret.is_file():
        return True
    return isaret.read_text(encoding="utf-8").strip() != kilit_ozeti(kok)


def kurulum_komutlari(venv_py: Path, kok: Path) -> List[List[str]]:
    """Önce kilitli bağımlılıklar, sonra paketin kendisi (bağımlılıksız, düzenlenebilir)."""
    kok = Path(kok)
    py = str(venv_py)
    return [
        [py, "-m", "pip", "install", "-r", str(kok / KILIT)],
        [py, "-m", "pip", "install", "--no-deps", "-e", str(kok)],
    ]


def _katalog_kur_betigi(kok: Path):
    yol = Path(kok) / "scripts" / "katalog_kur.py"
    spec = importlib.util.spec_from_file_location("katalog_kur", yol)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _sil(yol: Path) -> None:
    if yol.is_dir():
        shutil.rmtree(yol)
    elif yol.exists():
        yol.unlink()


def _parola_dosyasi_yaz(yol: Path, parolalar: dict) -> None:
    satirlar = [
        "# Demo kullanıcılarının parolaları (scripts/demo.py üretti; yalnız yerel demo içindir).",
        "# Biçim: <kullanıcı>: <parola>. --sifirla ile yenilenir.",
    ]
    satirlar += [f"{ad}: {parola}" for ad, parola in parolalar.items()]
    _sil(yol)
    fd = os.open(str(yol), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(satirlar) + "\n")
    if os.name == "posix":
        os.chmod(yol, 0o600)


SQLITE_EKLERI = ("-journal", "-wal", "-shm")


class KlasorHatasi(ValueError):
    """Demo klasörü depo içinde data/calisma/ altında değil."""


class VeritabaniSilinemedi(OSError):
    """--sifirla'da var olan demo veritabanı silinemedi (ör. Windows'ta uygulama açık)."""


def _klasor_denetle(klasor: Path, kok: Path) -> Path:
    """Depo içindeki klasör yalnız data/calisma/'nın alt klasörü olabilir; dosya sistemine dokunmaz."""
    klasor, kok = Path(klasor).resolve(), Path(kok).resolve()
    calisma = kok / "data" / "calisma"
    if (klasor == kok or kok in klasor.parents) and calisma not in klasor.parents:
        raise KlasorHatasi(
            f"demo klasörü depo içinde yalnız data/calisma/ altında olabilir (verilen: {klasor})")
    return klasor


def _venv_denetle(venv: Path, kok: Path) -> Path:
    """Depo içindeki sanal ortam yalnız kökteki .venv ya da data/calisma/ altı olabilir; dosya sistemine dokunmaz."""
    venv, kok = Path(venv).resolve(), Path(kok).resolve()
    if venv != kok / ".venv" and (venv == kok or kok in venv.parents) \
            and (kok / "data" / "calisma") not in venv.parents:
        raise KlasorHatasi(
            f"sanal ortam depo içinde yalnız .venv ya da data/calisma/ altında olabilir (verilen: {venv})")
    return venv


def _sqlite_sil(db: Path) -> None:
    for yol in [db] + [Path(f"{db}{ek}") for ek in SQLITE_EKLERI]:
        _sil(yol)


def _eksik_dosyalari_kopyala(dosyalar: Path, kok: Path) -> None:
    dosyalar.mkdir(parents=True, exist_ok=True)
    for hedef, kaynak in DEMO_DOSYALARI.items():
        if not (dosyalar / hedef).is_file():
            shutil.copyfile(kok / kaynak, dosyalar / hedef)


def demo_kur(klasor: Path = VARSAYILAN_KLASOR, kok: Path = KOK, sifirla: bool = False):
    """Demo veritabanını, kullanıcıları ve demo dosyalarını `klasor` altına kurar.

    Veritabanı varsa ve `sifirla` değilse veritabanına ve parolalara dokunulmaz;
    yalnız eksik demo dosyaları yeniden kopyalanır. Depo içindeki klasör
    data/calisma/ altında değilse hiçbir şey yazılmadan `KlasorHatasi` verilir.
    """
    kok = Path(kok)
    klasor = _klasor_denetle(klasor, kok)  # ilk yazmadan önce
    db = klasor / "katalog.sqlite"
    parola_dosyasi = klasor / "parolalar.txt"
    dosyalar = klasor / "dosyalar"
    if db.exists() and not sifirla:
        _eksik_dosyalari_kopyala(dosyalar, kok)
        if not parola_dosyasi.is_file():
            print("UYARI: parola dosyası yok; parolalar yeniden üretilmedi, demoyu --sifirla ile baştan kurun.")
        return DemoKurulumu(db, parola_dosyasi, dosyalar, yeni_kuruldu=False)

    from malzeme_kabul.arayuz.kimlik import kullanici_ekle
    from malzeme_kabul.katalog.veritabani import Katalog
    from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi

    try:
        _sqlite_sil(db)  # önce veritabanı: silinemezse başka bir şeye dokunulmaz
    except OSError as hata:
        raise VeritabaniSilinemedi(f"demo veritabanı silinemedi: {db} ({hata})") from hata
    for yol in (parola_dosyasi, dosyalar, klasor / "yuklenen"):
        _sil(yol)
    klasor.mkdir(parents=True, exist_ok=True)
    gecici = klasor / "katalog.sqlite.kuruluyor"
    _sqlite_sil(gecici)

    ornek_kur = _katalog_kur_betigi(kok).ornek_kur
    parolalar = {ad: secrets.token_urlsafe(18) for ad, _ in DEMO_KULLANICILARI}
    with Katalog(gecici) as katalog:
        defter = DenetimKaydi(katalog.baglanti)
        for veri in ORNEK_KATALOGLARI:
            ornek_kur(katalog, defter, kok / veri, kok)
        for ad, rol in DEMO_KULLANICILARI:
            kullanici_ekle(katalog.baglanti, ad, parolalar[ad], rol)

    _eksik_dosyalari_kopyala(dosyalar, kok)
    _parola_dosyasi_yaz(parola_dosyasi, parolalar)
    os.replace(gecici, db)  # veritabanı en son yerine konur: yarım kurulum "kurulu" sayılmaz
    _sqlite_sil(gecici)  # geçici dosyanın günlük artıkları
    return DemoKurulumu(db, parola_dosyasi, dosyalar, yeni_kuruldu=True)


def streamlit_komutu(python: Path, kok: Path, port: int) -> List[str]:
    """Uygulamayı yalnız 127.0.0.1'de başlatan Streamlit komutu."""
    return [
        str(python), "-m", "streamlit", "run", str(Path(kok) / UYGULAMA),
        "--server.address", "127.0.0.1",
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--client.toolbarMode", "minimal",  # Docker'daki gibi: "Deploy" düğmesi görünmez
    ]


def streamlit_ortami(kurulum, ortam: dict) -> dict:
    """Verilen ortamın kopyası; veritabanı ve yükleme klasörü demo klasörünü gösterir."""
    yeni = dict(ortam)
    yeni["MALZEME_KABUL_DB"] = str(kurulum.db)
    yeni["MALZEME_KABUL_YUKLEME"] = str(Path(kurulum.db).parent / "yuklenen")
    return yeni


def _venv_icinde_mi(venv: Path) -> bool:
    try:
        return Path(sys.prefix).resolve() == Path(venv).resolve()
    except OSError:
        return False


def _sanal_ortami_hazirla(venv: Path, kok: Path) -> None:
    py = venv_python(venv)
    if not py.is_file():
        print(f"sanal ortam kuruluyor: {venv}")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    if kurulum_gerekli_mi(venv, kok):
        print("kilitli sürümler kuruluyor (ilk çalıştırmada ağ gerekir) ...")
        for komut in kurulum_komutlari(py, kok):
            subprocess.check_call(komut)
        (Path(venv) / KURULUM_ISARETI).write_text(kilit_ozeti(kok), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("--sifirla", action="store_true", help="demo veritabanını silip baştan kurar")
    ayr.add_argument("--yalniz-kur", action="store_true", help="kurar, uygulamayı başlatmaz")
    ayr.add_argument("--kurulum-yok", action="store_true", help="sanal ortam/pip adımını atlar")
    ayr.add_argument("--port", type=int, default=VARSAYILAN_PORT)
    ayr.add_argument("--klasor", default=str(VARSAYILAN_KLASOR), help="demo verisinin klasörü")
    ayr.add_argument("--venv", default=str(VARSAYILAN_VENV), help="sanal ortam klasörü")
    args = ayr.parse_args(sys.argv[1:] if argv is None else argv)

    if not python_uygun_mu():
        surum = ".".join(str(p) for p in sys.version_info[:3])
        print(f"HATA: Python 3.11 ya da üstü gerekir (bu Python {surum}).", file=sys.stderr)
        return 2

    try:
        _klasor_denetle(Path(args.klasor), KOK)
        _venv_denetle(Path(args.venv), KOK)
    except KlasorHatasi as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 2

    venv = Path(args.venv)
    if not args.kurulum_yok and not _venv_icinde_mi(venv):
        _sanal_ortami_hazirla(venv, KOK)
        argumanlar = list(sys.argv[1:] if argv is None else argv) + ["--kurulum-yok"]
        try:
            return subprocess.call([str(venv_python(venv)), str(Path(__file__).resolve()), *argumanlar])
        except KeyboardInterrupt:
            return 0

    try:
        kurulum = demo_kur(Path(args.klasor), KOK, sifirla=args.sifirla)
    except KlasorHatasi as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 2
    except VeritabaniSilinemedi as hata:
        print(f"HATA: {hata}. Veritabanı başka bir süreçte açık olabilir (Windows'ta çalışan demo); "
              "uygulamayı kapatıp yeniden deneyin.", file=sys.stderr)
        return 2
    if kurulum.yeni_kuruldu:
        print(f"demo kuruldu: {kurulum.db}")
    else:
        print(f"var olan demo kullanılıyor (baştan kurmak için --sifirla): {kurulum.db}")
    print(f"parolalar: {kurulum.parola_dosyasi}  (kullanıcılar: mp = M&P, gk = giriş kalite)")
    print(f"demo dosyaları: {kurulum.dosyalar}")
    adres = f"http://127.0.0.1:{args.port}"
    if args.yalniz_kur:
        print(f"uygulamayı başlatmak için: python scripts/demo.py  (adres: {adres})")
        return 0

    print(f"uygulama: {adres}  (durdurmak için Ctrl+C)")
    try:
        return subprocess.call(streamlit_komutu(Path(sys.executable), KOK, args.port),
                               env=streamlit_ortami(kurulum, os.environ), cwd=str(KOK))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
