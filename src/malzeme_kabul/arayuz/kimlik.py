"""Basit kullanıcı girişi ve iki rol: M&P mühendisi ve giriş kalite.

Kullanıcılar katalogla aynı SQLite dosyasında (`kullanicilar` tablosu) durur.
Parola düz metin saklanmaz: PBKDF2-HMAC-SHA256 (200 000 tur, kullanıcı başına
16 bayt tuz) özeti saklanır; karşılaştırma sabit zamanlıdır.

Ekran yetkileri:

- `mp` (M&P mühendisi): standart yükle, taslağı düzelt ve onayla, revizyon
  farkı ve M&P incelemesi, depo.
- `giris_kalite`: CoC yükle ve karar al, depo.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from dataclasses import dataclass
from typing import Literal

Rol = Literal["mp", "giris_kalite"]
ROLLER: dict[str, str] = {"mp": "M&P mühendisi", "giris_kalite": "Giriş kalite"}
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


__all__ = ["EKRANLAR", "KimlikHatasi", "Kullanici", "ROLLER", "Rol", "YETKILER", "giris", "kullanici_ekle", "kullanicilar", "tablo_kur", "yetkili_mi"]
