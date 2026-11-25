"""Raf ömrü: son kullanma tarihi, uyarı ve ömür uzatma testleri (kesin kurallar).

- Son kullanma tarihi = üretim tarihi + kabul dokümanındaki raf ömrü. Yıl ve
  ay takvimle eklenir (31 Ocak + 1 ay = 28/29 Şubat, ayın son günü); gün ve
  hafta gün olarak; diğer zaman birimleri pint ile güne çevrilip aşağı
  yuvarlanır (ömür kısalır, uzamaz).
- Kap türüne göre birden çok raf ömrü varsa partinin kap türüyle eşleşen
  kayıt seçilir. Kap türü bilinmiyor ya da eşleşmiyorsa **en kısa** raf ömrü
  alınır ve bu not edilir (güvenli taraf).
- Raf ömrü kaydının uygulanabilirliği tip/sınıfa uymuyorsa kayıt atlanır.
- Durum: kalan gün < 0 → `doldu`; kalan gün ≤ uyarı eşiği (varsayılan 30) →
  `yaklasiyor`; değilse `gecerli`. Raf ömrü bulunamazsa `bilinmiyor`.
- Ömür uzatma testleri, kabul dokümanında `omur_uzatma` türü taşıyan ve
  tip/sınıfa uygulanan testlerdir.
"""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from malzeme_kabul.kural.birimler import birimi_coz, kayit
from malzeme_kabul.kural.karar_motoru import uygulanir_mi
from malzeme_kabul.sozlesme.sema import KabulDokumani, RafOmru, TestSarti

RafDurumu = Literal["gecerli", "yaklasiyor", "doldu", "bilinmiyor"]
UYARI_ESIGI_GUN = 30


def ay_ekle(tarih: date, ay: int) -> date:
    """Takvimle ay ekler; gün yeni ayda yoksa ayın son günü alınır."""
    toplam = tarih.year * 12 + (tarih.month - 1) + ay
    yil, ay0 = divmod(toplam, 12)
    gun = min(tarih.day, calendar.monthrange(yil, ay0 + 1)[1])
    return date(yil, ay0 + 1, gun)


def sure_ekle(tarih: date, sure: float, birim: str) -> date:
    """Tarihe raf ömrü süresini ekler."""
    b = birimi_coz(birim)
    r = kayit()
    if b in (r.year, r.month) and float(sure).is_integer():
        return ay_ekle(tarih, int(sure) * (12 if b == r.year else 1))
    gun = r.Quantity(sure, b).to(r.day).magnitude
    return tarih + timedelta(days=math.floor(gun + 1e-9))


@dataclass(frozen=True)
class RafDurumBilgisi:
    durum: RafDurumu
    son_kullanma: date | None
    kalan_gun: int | None
    raf_omru: RafOmru | None
    notlar: list[str] = field(default_factory=list)

    @property
    def uyari(self) -> bool:
        return self.durum in ("yaklasiyor", "doldu")


def _uygulanan(kayitlar: list[RafOmru], tip: str | None, sinif: str | None) -> list[RafOmru]:
    return [r for r in kayitlar if uygulanir_mi(r.uygulanabilirlik, tip, sinif) is not False]


def raf_omru_sec(
    dokuman: KabulDokumani, kap_turu: str | None = None, tip: str | None = None, sinif: str | None = None
) -> tuple[RafOmru | None, list[str]]:
    """Partiye uygulanacak raf ömrü kaydını ve seçim notlarını döner."""
    adaylar = _uygulanan(dokuman.raf_omurleri, tip, sinif)
    if not adaylar:
        return None, ["kabul dokümanında raf ömrü yok"]
    if kap_turu:
        eslesen = [r for r in adaylar if (r.kap_turu or "").casefold() == kap_turu.casefold()]
        if eslesen:
            return eslesen[0], []
    genel = [r for r in adaylar if r.kap_turu is None]
    if len(adaylar) == 1 or (len(genel) == 1 and not kap_turu):
        return (genel or adaylar)[0], []
    ref = date(2000, 1, 1)
    en_kisa = min(adaylar, key=lambda r: sure_ekle(ref, r.sure, r.birim))
    neden = f"kap türü {kap_turu!r} eşleşmedi" if kap_turu else "kap türü bilinmiyor"
    return en_kisa, [f"{neden}; en kısa raf ömrü alındı ({en_kisa.kap_turu or 'genel'}: {en_kisa.sure:g} {en_kisa.birim})"]


def raf_durumu(
    dokuman: KabulDokumani,
    uretim_tarihi: date,
    bugun: date,
    kap_turu: str | None = None,
    tip: str | None = None,
    sinif: str | None = None,
    uyari_esigi_gun: int = UYARI_ESIGI_GUN,
) -> RafDurumBilgisi:
    """Partinin son kullanma tarihini ve raf durumunu hesaplar."""
    kayit_, notlar = raf_omru_sec(dokuman, kap_turu, tip, sinif)
    if kayit_ is None:
        return RafDurumBilgisi("bilinmiyor", None, None, None, notlar)
    son = sure_ekle(uretim_tarihi, kayit_.sure, kayit_.birim)
    if kayit_.baslangic:
        notlar = notlar + [f"başlangıç: {kayit_.baslangic} (üretim tarihi kullanıldı)"]
    kalan = (son - bugun).days
    durum: RafDurumu = "doldu" if kalan < 0 else "yaklasiyor" if kalan <= uyari_esigi_gun else "gecerli"
    return RafDurumBilgisi(durum, son, kalan, kayit_, notlar)


def omur_uzatma_testleri(dokuman: KabulDokumani, tip: str | None = None, sinif: str | None = None) -> list[TestSarti]:
    """Tip/sınıfa uygulanan ömür uzatma testleri."""
    return [t for t in dokuman.omur_uzatma_testleri if uygulanir_mi(t.uygulanabilirlik, tip, sinif) is not False]


__all__ = [
    "RafDurumBilgisi",
    "RafDurumu",
    "UYARI_ESIGI_GUN",
    "ay_ekle",
    "omur_uzatma_testleri",
    "raf_durumu",
    "raf_omru_sec",
    "sure_ekle",
]
