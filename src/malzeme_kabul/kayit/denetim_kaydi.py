"""Zincirli (hash) denetim kaydı (docs/mimari.md madde 3).

Her karar, onay ve düzeltme bir kayıt olarak eklenir: kullanıcı, zaman,
kabul dokümanı sürümü, PDF sayfası, model ve istem sürümü ve kaydın içeriği
(JSON). Kayıtlar yalnız eklenir.

Kurcalanamazlık iki katmanlıdır:

1. SQLite tetikleyicileri kayıtların güncellenmesini ve silinmesini reddeder.
2. Her kaydın `ozet` alanı, kaydın bütün alanlarının ve **bir önceki kaydın
   özetinin** SHA-256'sıdır. İlk kaydın öncülü `BASLANGIC` (64 sıfır). Bir
   kayıt değişir, silinir ya da araya kayıt sokulursa o kayıttan sonraki
   zincir tutmaz; `zinciri_dogrula` ilk bozuk kaydı bildirir.

Özet, alanların anahtarları sıralı, boşluksuz JSON'u üzerinden hesaplanır;
böylece aynı kayıt her makinede aynı özeti verir.

Not: veritabanının tamamını baştan yazabilen biri zinciri yeniden
hesaplayabilir. Buna karşı son özet dışarıda (ör. rapora, e-postaya)
saklanmalıdır; `son_ozet` bunun içindir.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

KayitTuru = Literal["karar", "onay", "duzeltme"]
KAYIT_TURLERI: tuple[str, ...] = ("karar", "onay", "duzeltme")
BASLANGIC = "0" * 64

SEMA = """
CREATE TABLE IF NOT EXISTS denetim_kaydi (
    sira            INTEGER PRIMARY KEY,
    zaman           TEXT NOT NULL,
    tur             TEXT NOT NULL CHECK (tur IN ('karar', 'onay', 'duzeltme')),
    kullanici       TEXT NOT NULL,
    malzeme_kodu    TEXT,
    lot_no          TEXT,
    dokuman_surumu  TEXT,
    pdf_sayfasi     TEXT,
    model           TEXT,
    istem_surumu    TEXT,
    icerik          TEXT NOT NULL,
    onceki_ozet     TEXT NOT NULL,
    ozet            TEXT NOT NULL UNIQUE
);

CREATE TRIGGER IF NOT EXISTS denetim_kaydi_degistirilemez
BEFORE UPDATE ON denetim_kaydi
BEGIN
    SELECT RAISE(ABORT, 'denetim kaydı değiştirilemez');
END;

CREATE TRIGGER IF NOT EXISTS denetim_kaydi_silinemez
BEFORE DELETE ON denetim_kaydi
BEGIN
    SELECT RAISE(ABORT, 'denetim kaydı silinemez');
END;
"""

_ALANLAR = (
    "sira", "zaman", "tur", "kullanici", "malzeme_kodu", "lot_no", "dokuman_surumu",
    "pdf_sayfasi", "model", "istem_surumu", "icerik", "onceki_ozet",
)


class DenetimHatasi(ValueError):
    """Geçersiz kayıt (bilinmeyen tür, boş kullanıcı...)."""


@dataclass(frozen=True)
class Kayit:
    sira: int
    zaman: str
    tur: str
    kullanici: str
    malzeme_kodu: str | None
    lot_no: str | None
    dokuman_surumu: str | None
    pdf_sayfasi: str | None
    model: str | None
    istem_surumu: str | None
    icerik: str
    onceki_ozet: str
    ozet: str

    @property
    def veri(self) -> Any:
        return json.loads(self.icerik)


@dataclass(frozen=True)
class DogrulamaSonucu:
    gecerli: bool
    kayit_sayisi: int
    bozuk_sira: int | None = None
    neden: str | None = None
    son_ozet: str = BASLANGIC


def kayit_ozeti(alanlar: dict[str, Any]) -> str:
    """Kaydın alanlarından (özet hariç) SHA-256 özeti."""
    govde = {a: alanlar.get(a) for a in _ALANLAR}
    metin = json.dumps(govde, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


def _simdi() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class DenetimKaydi:
    """Zincirli denetim kaydı. Katalogla aynı SQLite bağlantısını paylaşabilir."""

    def __init__(self, baglanti: sqlite3.Connection | str | Path = ":memory:"):
        if isinstance(baglanti, sqlite3.Connection):
            self.baglanti = baglanti
            self._sahip = False
        else:
            if str(baglanti) != ":memory:":
                Path(baglanti).parent.mkdir(parents=True, exist_ok=True)
            self.baglanti = sqlite3.connect(str(baglanti), check_same_thread=False)
            self._sahip = True
        self.baglanti.row_factory = sqlite3.Row
        self.baglanti.executescript(SEMA)

    def kapat(self) -> None:
        if self._sahip:
            self.baglanti.close()

    def __enter__(self) -> DenetimKaydi:
        return self

    def __exit__(self, *_exc) -> None:
        self.kapat()

    def son_ozet(self) -> str:
        s = self.baglanti.execute("SELECT ozet FROM denetim_kaydi ORDER BY sira DESC LIMIT 1").fetchone()
        return s["ozet"] if s else BASLANGIC

    def ekle(
        self,
        tur: KayitTuru,
        kullanici: str,
        icerik: Any,
        *,
        malzeme_kodu: str | None = None,
        lot_no: str | None = None,
        dokuman_surumu: str | None = None,
        pdf_sayfasi: str | int | None = None,
        model: str | None = None,
        istem_surumu: str | None = None,
        zaman: str | None = None,
    ) -> Kayit:
        """Zincirin sonuna bir kayıt ekler ve onu döner."""
        if tur not in KAYIT_TURLERI:
            raise DenetimHatasi(f"bilinmeyen kayıt türü: {tur!r} ({', '.join(KAYIT_TURLERI)})")
        if not kullanici or not kullanici.strip():
            raise DenetimHatasi("kullanıcı boş olamaz")
        b = self.baglanti
        b.execute("BEGIN IMMEDIATE")
        try:
            son = b.execute("SELECT sira, ozet FROM denetim_kaydi ORDER BY sira DESC LIMIT 1").fetchone()
            alanlar: dict[str, Any] = {
                "sira": (son["sira"] + 1) if son else 1,
                "zaman": zaman or _simdi(),
                "tur": tur,
                "kullanici": kullanici,
                "malzeme_kodu": malzeme_kodu,
                "lot_no": lot_no,
                "dokuman_surumu": dokuman_surumu,
                "pdf_sayfasi": None if pdf_sayfasi is None else str(pdf_sayfasi),
                "model": model,
                "istem_surumu": istem_surumu,
                "icerik": json.dumps(icerik, ensure_ascii=False, sort_keys=True, default=str),
                "onceki_ozet": son["ozet"] if son else BASLANGIC,
            }
            alanlar["ozet"] = kayit_ozeti(alanlar)
            b.execute(
                f"INSERT INTO denetim_kaydi ({', '.join(alanlar)}) VALUES ({', '.join('?' * len(alanlar))})",
                tuple(alanlar.values()),
            )
            b.execute("COMMIT")
        except Exception:
            b.execute("ROLLBACK")
            raise
        return Kayit(**alanlar)

    def kayitlar(self, tur: str | None = None, malzeme_kodu: str | None = None) -> list[Kayit]:
        kosul, deger = [], []
        if tur is not None:
            kosul.append("tur = ?")
            deger.append(tur)
        if malzeme_kodu is not None:
            kosul.append("malzeme_kodu = ?")
            deger.append(malzeme_kodu)
        nerede = f" WHERE {' AND '.join(kosul)}" if kosul else ""
        satirlar = self.baglanti.execute(f"SELECT * FROM denetim_kaydi{nerede} ORDER BY sira", deger)
        return [Kayit(**dict(s)) for s in satirlar]

    def zinciri_dogrula(self, beklenen_son_ozet: str | None = None) -> DogrulamaSonucu:
        """Zinciri baştan sona doğrular; ilk bozuk kaydı bildirir.

        `beklenen_son_ozet` dışarıda saklanmış son özetse, zincirin onunla
        bittiği de denetlenir (sondan kayıt silinmesi ya da zincirin baştan
        yazılması buna takılır).
        """
        onceki = BASLANGIC
        beklenen_sira = 1
        sayi = 0
        for s in self.baglanti.execute("SELECT * FROM denetim_kaydi ORDER BY sira"):
            alanlar = dict(s)
            sira = alanlar["sira"]
            if sira != beklenen_sira:
                return DogrulamaSonucu(False, sayi, sira, f"sıra atlıyor: {beklenen_sira} bekleniyordu, {sira} var", onceki)
            if alanlar["onceki_ozet"] != onceki:
                return DogrulamaSonucu(False, sayi, sira, "önceki özet zincirle tutmuyor (kayıt silinmiş ya da araya girilmiş)", onceki)
            if kayit_ozeti(alanlar) != alanlar["ozet"]:
                return DogrulamaSonucu(False, sayi, sira, "kaydın özeti içeriğiyle tutmuyor (kayıt değiştirilmiş)", onceki)
            onceki = alanlar["ozet"]
            beklenen_sira += 1
            sayi += 1
        if beklenen_son_ozet is not None and beklenen_son_ozet != onceki:
            return DogrulamaSonucu(False, sayi, None, "zincirin son özeti dışarıda saklanan özetle tutmuyor", onceki)
        return DogrulamaSonucu(True, sayi, son_ozet=onceki)


__all__ = [
    "BASLANGIC",
    "DenetimHatasi",
    "DenetimKaydi",
    "DogrulamaSonucu",
    "KAYIT_TURLERI",
    "Kayit",
    "KayitTuru",
    "kayit_ozeti",
]
