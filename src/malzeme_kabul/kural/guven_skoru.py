"""Güven skoru: hibrit çıkarıcının bir test şartını yanlış okumuş olma olasılığı.

Ayrıntı ve gerekçe: docs/guven_skoru.md. Skor kabul ya da red kararı vermez;
yalnız "uygun" kararı insan incelemesine gönderebilir (`yonlendir`).
"uygun_degil" ve "insan_incelemeli" hiçbir skorla değişmez; model yoksa
(güven None) hiçbir karar değişmez.

Model, L2 düzenlemeli lojistik regresyondur; ağırlıklar JSON'da saklanır.
Eğitim bu modülde yoktur (deney/guven_egitimi.py). Saf Python; dil modeli,
numpy ve dış servis kullanılmaz.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

SURUM = "guven-skoru-v1"
OZELLIK_ADLARI = (
    "anlasmazlik_sayisi",
    "kanit_yok",
    "yalniz_model",
    "sayfa_kanitsiz_sayisi",
    "yon_celiskisi",
    "sayfa_sema_hatasi",
)
_SAYI_ALANLARI = ("anlasmazlik_sayisi", "sayfa_kanitsiz_sayisi", "sayfa_sema_hatasi")
KARARLAR = ("uygun", "uygun_degil", "insan_incelemeli")
EN_YUKSEK_GUVEN = math.nextafter(1.0, 0.0)  # güven 1.0'a ulaşmaz; 1.0 eşiği "otomatik geçiş yok" demektir


class GuvenModeliHatasi(ValueError):
    """Model dosyası ya da parametreleri geçersiz."""


@dataclass(frozen=True)
class GuvenGirdileri:
    """Bir hibrit test şartı için güven skoru girdileri (docs/guven_skoru.md, Girdiler)."""

    anlasmazlik_sayisi: int = 0
    kanit_yok: bool = False
    yalniz_model: bool = False
    sayfa_kanitsiz_sayisi: int = 0
    yon_celiskisi: bool = False
    sayfa_sema_hatasi: int = 0

    def __post_init__(self) -> None:
        for f in fields(self):
            deger = getattr(self, f.name)
            if f.name in _SAYI_ALANLARI:
                if type(deger) is not int or deger < 0:
                    raise ValueError(f"{f.name} negatif olmayan bir tamsayı olmalı: {deger!r}")
            elif type(deger) is not bool:
                raise ValueError(f"{f.name} True ya da False olmalı: {deger!r}")

    def vektor(self) -> tuple[float, ...]:
        """Sayılar log(1 + n), ikililer 0/1; sıra OZELLIK_ADLARI."""
        return tuple(
            math.log1p(getattr(self, ad)) if ad in _SAYI_ALANLARI else float(getattr(self, ad))
            for ad in OZELLIK_ADLARI
        )


def _sigmoid(z: float) -> float:
    """Taşmasız sigmoid."""
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _sonlu_sayi(deger: Any, ad: str) -> float:
    if isinstance(deger, bool) or not isinstance(deger, (int, float)) or not math.isfinite(deger):
        raise GuvenModeliHatasi(f"{ad} sonlu bir sayı olmalı: {deger!r}")
    return float(deger)


def _gold_altinda_mi(yol: str | Path) -> bool:
    """Yol data/gold altında mı (harf büyüklüğü gözetilmez)?"""
    parcalar = [p.casefold() for p in Path(yol).resolve().parts]
    return any(a == "data" and b == "gold" for a, b in zip(parcalar, parcalar[1:]))


@dataclass(frozen=True)
class GuvenModeli:
    agirliklar: dict[str, float]
    sabit: float
    esik: float
    bilgi: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.agirliklar, dict) or set(self.agirliklar) != set(OZELLIK_ADLARI):
            raise GuvenModeliHatasi(f"ağırlık anahtarları {list(OZELLIK_ADLARI)} olmalı")
        agirliklar = {ad: _sonlu_sayi(self.agirliklar[ad], f"ağırlık {ad}") for ad in OZELLIK_ADLARI}
        object.__setattr__(self, "agirliklar", agirliklar)
        object.__setattr__(self, "sabit", _sonlu_sayi(self.sabit, "sabit"))
        esik = _sonlu_sayi(self.esik, "eşik")
        if not 0.0 <= esik <= 1.0:
            raise GuvenModeliHatasi(f"eşik 0 ile 1 arasında olmalı: {esik}")
        object.__setattr__(self, "esik", esik)
        if not isinstance(self.bilgi, dict):
            raise GuvenModeliHatasi("bilgi bir sözlük olmalı")

    def hata_olasiligi(self, girdiler: GuvenGirdileri) -> float:
        z = self.sabit + sum(self.agirliklar[ad] * x for ad, x in zip(OZELLIK_ADLARI, girdiler.vektor()))
        return _sigmoid(z)

    def guven(self, girdiler: GuvenGirdileri) -> float:
        """1 - hata olasılığı; en çok EN_YUKSEK_GUVEN (1.0 eşiğinde hiçbir test otomatik geçmez)."""
        return min(1.0 - self.hata_olasiligi(girdiler), EN_YUKSEK_GUVEN)

    def sozluk(self) -> dict[str, Any]:
        return {
            "surum": SURUM,
            "ozellikler": list(OZELLIK_ADLARI),
            "agirliklar": dict(self.agirliklar),
            "sabit": self.sabit,
            "esik": self.esik,
            "bilgi": dict(self.bilgi),
        }

    @classmethod
    def sozlukten(cls, veri: Any) -> GuvenModeli:
        if not isinstance(veri, dict):
            raise GuvenModeliHatasi("model bir JSON nesnesi olmalı")
        if veri.get("surum") != SURUM:
            raise GuvenModeliHatasi(f"model sürümü {SURUM!r} olmalı: {veri.get('surum')!r}")
        if veri.get("ozellikler") != list(OZELLIK_ADLARI):
            raise GuvenModeliHatasi(f"özellik listesi birebir {list(OZELLIK_ADLARI)} olmalı")
        try:
            return cls(agirliklar=veri["agirliklar"], sabit=veri["sabit"], esik=veri["esik"],
                       bilgi=veri.get("bilgi", {}))
        except KeyError as hata:
            raise GuvenModeliHatasi(f"model alanı eksik: {hata}") from hata

    def kaydet(self, yol: str | Path) -> None:
        """JSON'a yazar; data/gold altına yazmayı reddeder."""
        yol = Path(yol)
        if _gold_altinda_mi(yol):
            raise GuvenModeliHatasi(f"model data/gold altına yazılamaz: {yol}")
        yol.write_text(json.dumps(self.sozluk(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def yukle(cls, yol: str | Path) -> GuvenModeli:
        try:
            veri = json.loads(Path(yol).read_text(encoding="utf-8"))
        except (OSError, ValueError) as hata:
            raise GuvenModeliHatasi(f"model okunamadı ({yol}): {hata}") from hata
        return cls.sozlukten(veri)


def _esik_dogrula(esik: float) -> None:
    if isinstance(esik, bool) or not isinstance(esik, (int, float)) or not 0.0 <= esik <= 1.0:
        raise ValueError(f"eşik 0 ile 1 arasında sonlu bir sayı olmalı: {esik!r}")


def _guven_dogrula(guven: float) -> None:
    """NaN geçerlidir (temkinle incelemeye gider); NaN olmayan güven [0, 1] içinde olmalı."""
    if isinstance(guven, bool) or not isinstance(guven, (int, float)):
        raise ValueError(f"güven bir sayı olmalı: {guven!r}")
    if not math.isnan(guven) and not 0.0 <= guven <= 1.0:
        raise ValueError(f"güven 0 ile 1 arasında olmalı: {guven!r}")


def _gecer_mi(guven: float, esik: float) -> bool:
    """"uygun" yalnız güven >= eşik ve eşik < 1.0 iken geçer; 1.0 eşiği "otomatik geçiş yok" demektir."""
    return not math.isnan(guven) and esik < 1.0 and guven >= esik


def yonlendir(karar: str, guven: float | None, esik: float) -> tuple[str, str | None]:
    """Yalnız "uygun"u, geçemiyorsa (`_gecer_mi`) "insan_incelemeli"ye çevirir.

    Dönen: (karar, neden). Neden yalnız karar değiştiyse doludur. Güven None
    (model yok) ise karar değişmez. Geçersiz eşik (NaN, sonsuz, [0, 1] dışı) ya da
    NaN olmayan [0, 1] dışı güven karardan bağımsız olarak ValueError verir.
    """
    _esik_dogrula(esik)
    if guven is not None:
        _guven_dogrula(guven)
    if karar not in KARARLAR:
        raise ValueError(f"bilinmeyen karar: {karar!r}")
    if karar != "uygun" or guven is None or _gecer_mi(guven, esik):
        return karar, None
    if math.isnan(guven):
        return "insan_incelemeli", "güven skoru hesaplanamadı (NaN)"
    if esik >= 1.0:
        return "insan_incelemeli", "güven skoru eşiği 1.0: otomatik geçiş yok"
    return "insan_incelemeli", f"güven skoru düşük ({guven:.3f} < eşik {esik:.3f})"


def incelenecek_testler(guvenler: dict[str, float], esik: float) -> list[str]:
    """Geçemeyen (`_gecer_mi`) test kimlikleri, sıralı. Geçersiz eşik ya da güven ValueError verir."""
    _esik_dogrula(esik)
    for g in guvenler.values():
        _guven_dogrula(g)
    return sorted(k for k, g in guvenler.items() if not _gecer_mi(g, esik))
