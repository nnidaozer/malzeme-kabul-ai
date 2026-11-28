"""Basit kullanıcı girişi ve iki rol: M&P mühendisi ve giriş kalite.

Kullanıcılar katalogla aynı SQLite dosyasında (`kullanicilar` tablosu) durur.
Parola düz metin saklanmaz: PBKDF2-HMAC-SHA256 (200 000 tur, kullanıcı başına
16 bayt tuz) özeti saklanır; karşılaştırma sabit zamanlıdır.

Ekran yetkileri:

- `mp` (M&P mühendisi): standart yükle, taslağı düzelt ve onayla, revizyon
  farkı ve M&P incelemesi, depo.
- `giris_kalite`: CoC yükle ve karar al, depo.

İlk kurulum (Docker): `ortamdan_kullanicilar` veritabanında hiç kullanıcı yoksa
parolaları ortam değişkenlerinden (ya da `*_DOSYASI` ile dosyadan) okuyarak M&P
ve giriş kalite hesaplarını açar; varsayılan parola yoktur.

Ayrılmış ad: `katalog.veritabani.ORNEK_ONAYLAYAN` ("ornek-veri") örnek verinin
demo onaylayanıdır; bu adla (harf farkı ve baştaki/sondaki boşluk gözetilmeden)
hesap açılmaz, yoksa gerçek bir hesabın onayları örnek veriyle karışırdı.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

from malzeme_kabul.katalog.veritabani import ORNEK_ONAYLAYAN, ROLLER

Rol = Literal["mp", "giris_kalite"]
# ROLLER katalog.veritabani'nda tanımlıdır (hat/katalog_karari.karari_duzelt de onu kullanır).
TUR = 200_000

EKRANLAR: dict[str, str] = {
    "standart": "Standart yükle",
    "taslak": "Taslağı düzelt ve onayla",
    "revizyon": "Revizyon farkı ve M&P incelemesi",
    "giris": "Giriş kalite: CoC kontrolü",
    "depo": "Depo: partiler ve raf ömrü",
}
YETKILER: dict[str, tuple[str, ...]] = {
    "mp": ("standart", "taslak", "revizyon", "depo"),
    "giris_kalite": ("giris", "depo"),
}

_SEMA = """
CREATE TABLE IF NOT EXISTS kullanicilar (
    ad     TEXT PRIMARY KEY,
    rol    TEXT NOT NULL CHECK (rol IN ('mp', 'giris_kalite')),
    tuz    TEXT NOT NULL,
    ozet   TEXT NOT NULL
);
"""


class KimlikHatasi(ValueError):
    pass


@dataclass(frozen=True)
class Kullanici:
    ad: str
    rol: str

    @property
    def rol_adi(self) -> str:
        return ROLLER[self.rol]

    @property
    def ekranlar(self) -> tuple[str, ...]:
        return YETKILER[self.rol]


def _ozet(parola: str, tuz: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", parola.encode("utf-8"), tuz, TUR).hex()


def tablo_kur(baglanti: sqlite3.Connection) -> None:
    baglanti.executescript(_SEMA)


def kullanici_ekle(baglanti: sqlite3.Connection, ad: str, parola: str, rol: str) -> Kullanici:
    tablo_kur(baglanti)
    if rol not in ROLLER:
        raise KimlikHatasi(f"bilinmeyen rol: {rol!r} ({', '.join(ROLLER)})")
    if not ad.strip():
        raise KimlikHatasi("kullanıcı adı boş olamaz")
    if ad.strip().casefold() == ORNEK_ONAYLAYAN.casefold():
        raise KimlikHatasi(f"{ad.strip()!r} ayrılmış addır (örnek verinin demo onaylayanı); başka ad seçin")
    if len(parola) < 8:
        raise KimlikHatasi("parola en az 8 karakter olmalı")
    tuz = os.urandom(16)
    try:
        baglanti.execute("INSERT INTO kullanicilar (ad, rol, tuz, ozet) VALUES (?, ?, ?, ?)", (ad, rol, tuz.hex(), _ozet(parola, tuz)))
        baglanti.commit()
    except sqlite3.IntegrityError as hata:
        raise KimlikHatasi(f"kullanıcı zaten var: {ad}") from hata
    return Kullanici(ad, rol)


def giris(baglanti: sqlite3.Connection, ad: str, parola: str) -> Kullanici | None:
    """Ad ve parola doğruysa kullanıcıyı, değilse None döner."""
    tablo_kur(baglanti)
    s = baglanti.execute("SELECT ad, rol, tuz, ozet FROM kullanicilar WHERE ad = ?", (ad,)).fetchone()
    if s is None:
        _ozet(parola, b"\0" * 16)  # var olmayan kullanıcıda da aynı süre
        return None
    ad_, rol, tuz, ozet = (s[0], s[1], s[2], s[3])
    if hmac.compare_digest(_ozet(parola, bytes.fromhex(tuz)), ozet):
        return Kullanici(ad_, rol)
    return None


def yetkili_mi(kullanici: Kullanici | None, ekran: str) -> bool:
    return kullanici is not None and ekran in YETKILER.get(kullanici.rol, ())


def kullanicilar(baglanti: sqlite3.Connection) -> list[Kullanici]:
    tablo_kur(baglanti)
    return [Kullanici(s[0], s[1]) for s in baglanti.execute("SELECT ad, rol FROM kullanicilar ORDER BY ad")]


# --- ilk kurulum: ortam değişkenlerinden kullanıcılar ---------------------------------

EN_AZ_PAROLA = 12
DENEME_PAROLALARI = frozenset({"mp-ornek-parola", "gk-ornek-parola"})
# (önek, rol, varsayılan kullanıcı adı)
_ILK_HESAPLAR: tuple[tuple[str, str, str], ...] = (
    ("MALZEME_KABUL_MP", "mp", "mp"),
    ("MALZEME_KABUL_GK", "giris_kalite", "gk"),
)


def _ortam_parolasi(ortam: Mapping[str, str], onek: str) -> tuple[str, str]:
    """(parola, kaynak değişken adı). Hata mesajları parolayı asla içermez."""
    degisken, dosya_degiskeni = f"{onek}_PAROLASI", f"{onek}_PAROLASI_DOSYASI"
    dogrudan, dosya = ortam.get(degisken, ""), ortam.get(dosya_degiskeni, "")
    if dogrudan and dosya:
        raise KimlikHatasi(f"{degisken} ve {dosya_degiskeni} birlikte ayarlanmış; yalnız birini kullanın")
    if dosya:
        try:
            parola = Path(dosya).read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as hata:
            raise KimlikHatasi(f"{dosya_degiskeni} ile verilen parola dosyası okunamadı") from hata
        kaynak = dosya_degiskeni
    else:
        parola, kaynak = dogrudan, degisken
    if not parola.strip():  # yalnız boşluktan oluşan parola da belirlenmemiş sayılır
        raise KimlikHatasi(f"{kaynak} boş ya da yalnız boşluk; ilk kurulumda parola zorunludur"
                           if parola else f"{degisken} (ya da {dosya_degiskeni}) ayarlanmamış; ilk kurulumda parola zorunludur")
    return parola, kaynak


def _parola_denetle(parola: str, ad: str, kaynak: str) -> None:
    if len(parola) < EN_AZ_PAROLA:
        raise KimlikHatasi(f"{kaynak}: parola en az {EN_AZ_PAROLA} karakter olmalı")
    if parola.casefold() == ad.casefold():
        raise KimlikHatasi(f"{kaynak}: parola kullanıcı adıyla aynı olamaz")
    if parola.casefold() in DENEME_PAROLALARI:
        raise KimlikHatasi(f"{kaynak}: bilinen deneme parolası kullanılamaz")


def _deneme_parolali_hesaplar(baglanti: sqlite3.Connection) -> list[str]:
    """Parolası bilinen bir deneme parolası (DENEME_PAROLALARI) olan hesapların adları."""
    tablo_kur(baglanti)
    sorunlu = []
    for ad, tuz, ozet in baglanti.execute("SELECT ad, tuz, ozet FROM kullanicilar ORDER BY ad"):
        if any(hmac.compare_digest(_ozet(d, bytes.fromhex(tuz)), ozet) for d in sorted(DENEME_PAROLALARI)):
            sorunlu.append(ad)
    return sorunlu


def ortamdan_kullanicilar(ortam: Mapping[str, str], baglanti: sqlite3.Connection) -> list[Kullanici]:
    """Veritabanında kullanıcı yoksa M&P ve giriş kalite hesaplarını ortamdan açar.

    Her çağrıda önce mevcut hesaplar deneme parolalarına karşı denetlenir; biri
    eşleşirse (ör. eski bir `--ornek-kullanicilar` kurulumu) hesabın adını söyleyen
    `KimlikHatasi` verilir, hiçbir hesap değiştirilmez ya da açılmaz. Kullanıcı
    zaten varsa ve hiçbiri deneme parolalı değilse [] döner. Parola eksik ya da
    zayıfsa `KimlikHatasi` verir ve hiçbir kullanıcı oluşturmaz (ya ikisi ya hiçbiri).
    """
    tablo_kur(baglanti)
    sorunlu = _deneme_parolali_hesaplar(baglanti)
    if sorunlu:
        raise KimlikHatasi(f"bilinen deneme parolasıyla kurulmuş hesap var: {', '.join(sorunlu)}; "
                           "hesabın parolası değiştirilmeli ya da hesap silinmeli")
    if kullanicilar(baglanti):
        return []
    hesaplar: list[tuple[str, str, str]] = []
    for onek, rol, varsayilan_ad in _ILK_HESAPLAR:
        ad = ortam.get(f"{onek}_KULLANICI", "").strip() or varsayilan_ad
        if ad.casefold() == ORNEK_ONAYLAYAN.casefold():
            raise KimlikHatasi(f"{onek}_KULLANICI: {ad!r} ayrılmış addır (örnek verinin demo onaylayanı)")
        parola, kaynak = _ortam_parolasi(ortam, onek)
        _parola_denetle(parola, ad, kaynak)
        hesaplar.append((ad, rol, parola))
    if len({ad for ad, _, _ in hesaplar}) != len(hesaplar):
        raise KimlikHatasi("MALZEME_KABUL_MP_KULLANICI ve MALZEME_KABUL_GK_KULLANICI aynı olamaz")
    try:
        with baglanti:  # tek işlem: hata olursa geri alınır
            for ad, rol, parola in hesaplar:
                tuz = os.urandom(16)
                baglanti.execute("INSERT INTO kullanicilar (ad, rol, tuz, ozet) VALUES (?, ?, ?, ?)",
                                 (ad, rol, tuz.hex(), _ozet(parola, tuz)))
    except sqlite3.IntegrityError as hata:
        raise KimlikHatasi("ilk kullanıcılar oluşturulamadı") from hata
    return [Kullanici(ad, rol) for ad, rol, _ in hesaplar]


__all__ = ["EKRANLAR", "KimlikHatasi", "Kullanici", "ROLLER", "Rol", "YETKILER", "giris", "kullanici_ekle", "kullanicilar", "ortamdan_kullanicilar", "tablo_kur", "yetkili_mi"]
