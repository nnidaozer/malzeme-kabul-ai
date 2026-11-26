"""Revizyon etkisi: yeni revizyon yüklenince etkilenen malzeme ve partileri işaretler (docs/mimari.md madde 4).

Standardın yeni revizyonu kataloğa eklenince aynı standardın daha eski bir
revizyonuna bağlı her malzeme kodu ve o malzemelerin partileri
"M&P incelemesi bekliyor" olarak işaretlenir. İşaret kilit değildir: parti
durumu değişmez, kullanım sürer (depodaki partiler için siparişte yazan
revizyon geçerlidir).

M&P mühendisi farkı inceleyip işareti kapatır (`mp_incelemesini_kapat`):

- `gerek_yok`: yeni revizyon bu malzemeyi etkilemiyor; malzeme eski
  revizyonda kalır.
- `yeni_revizyona_gec`: malzeme yeni revizyona bağlanır; yeni revizyonun
  onaylı kabul dokümanı önceden bulunmalıdır.

Kapatma denetim kaydına `onay` olarak yazılır.

Revizyon harfleri tek harftir ve alfabe sırasıyla ilerler (G → H → J → K);
yalnız yeni revizyondan **önceki** harflere bağlı malzemeler etkilenir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from malzeme_kabul.katalog.veritabani import Katalog, KatalogHatasi
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi, Kayit

MP_ISARETI = "M&P incelemesi bekliyor"
KapatmaKarari = Literal["gerek_yok", "yeni_revizyona_gec"]

_OLAYLAR = """
CREATE TABLE IF NOT EXISTS revizyon_olaylari (
    sira         INTEGER PRIMARY KEY,
    belge_no     TEXT NOT NULL,
    yeni_revizyon TEXT NOT NULL,
    zaman        TEXT NOT NULL,
    kullanici    TEXT NOT NULL,
    etkilenen_malzemeler TEXT NOT NULL,
    etkilenen_partiler   TEXT NOT NULL,
    fark_ozeti   TEXT
);
"""


@dataclass
class RevizyonEtkisi:
    belge_no: str
    yeni_revizyon: str
    etkilenen_malzemeler: list[str] = field(default_factory=list)
    etkilenen_partiler: list[str] = field(default_factory=list)  # "KOD/LOT"

    @property
    def yeni_etiket(self) -> str:
        return f"{self.belge_no}{self.yeni_revizyon}"


def daha_eski_mi(eski: str, yeni: str) -> bool:
    """Revizyon harfi sırası: 'J' 'K'dan eskidir. Uzunluk farklıysa önce uzunluk (Z < AA)."""
    return (len(eski), eski.upper()) < (len(yeni), yeni.upper())


def yeni_revizyon_yukle(
    katalog: Katalog,
    belge_no: str,
    yeni_revizyon: str,
    kullanici: str,
    baslik: str | None = None,
    tarih: str | None = None,
    fark_ozeti: dict | None = None,
) -> RevizyonEtkisi:
    """Yeni revizyonu kataloğa ekler; etkilenen malzeme ve partileri işaretler."""
    if not kullanici or not kullanici.strip():
        raise KatalogHatasi("kullanıcı boş olamaz")
    katalog.standart_ekle(belge_no, yeni_revizyon, baslik, tarih)
    etki = RevizyonEtkisi(belge_no, yeni_revizyon)
    neden = f"{MP_ISARETI}: {etki.yeni_etiket} yayımlandı"
    for m in katalog.malzemeler():
        if m.belge_no != belge_no or not daha_eski_mi(m.revizyon, yeni_revizyon):
            continue
        katalog.mp_inceleme_ata(m.kod, f"{neden} (malzeme {m.standart_etiketi})")
        etki.etkilenen_malzemeler.append(m.kod)
        etki.etkilenen_partiler += [f"{p.malzeme_kodu}/{p.lot_no}" for p in katalog.partiler(m.kod)]
    b = katalog.baglanti
    b.execute(_OLAYLAR)  # tek ifade; executescript açık bir dış işlemi sessizce bitirirdi
    with katalog.islem():
        b.execute(
            "INSERT INTO revizyon_olaylari (belge_no, yeni_revizyon, zaman, kullanici, etkilenen_malzemeler,"
            " etkilenen_partiler, fark_ozeti) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (belge_no, yeni_revizyon, datetime.now(timezone.utc).isoformat(timespec="seconds"), kullanici,
             json.dumps(etki.etkilenen_malzemeler), json.dumps(etki.etkilenen_partiler, ensure_ascii=False),
             json.dumps(fark_ozeti, ensure_ascii=False) if fark_ozeti is not None else None),
        )
    return etki


def mp_bekleyenler(katalog: Katalog) -> list[str]:
    """M&P incelemesi bekleyen malzeme kodları."""
    return [m.kod for m in katalog.malzemeler() if m.mp_inceleme]


def mp_incelemesini_kapat(
    katalog: Katalog,
    defter: DenetimKaydi,
    malzeme_kodu: str,
    kullanici: str,
    karar: KapatmaKarari,
    not_: str | None = None,
    yeni_revizyon: str | None = None,
) -> Kayit:
    """M&P incelemesini kapatır ve denetim kaydına yazar.

    Revizyon değişikliği, işaretin kaldırılması ve kayıt tek işlemdir: kayıt
    yazılamazsa revizyon da işaret de eski kalır.
    """
    if defter.baglanti is not katalog.baglanti:
        raise KatalogHatasi("denetim kaydı katalogla aynı bağlantıyı paylaşmalı (durum ve kayıt tek işlem)")
    m = katalog.malzeme(malzeme_kodu)
    if not m.mp_inceleme:
        raise KatalogHatasi(f"{malzeme_kodu} için bekleyen M&P incelemesi yok")
    if karar not in ("gerek_yok", "yeni_revizyona_gec"):
        raise KatalogHatasi(f"bilinmeyen karar: {karar!r} (gerek_yok, yeni_revizyona_gec)")
    if karar == "yeni_revizyona_gec" and not yeni_revizyon:
        raise KatalogHatasi("yeni revizyona geçmek için revizyon harfi gerekli")
    with katalog.islem():
        if karar == "yeni_revizyona_gec":
            m2 = katalog.malzeme_revizyonu_ata(malzeme_kodu, yeni_revizyon)
            icerik = {"karar": karar, "eski": m.standart_etiketi, "yeni": m2.standart_etiketi, "not": not_}
            surum = katalog.gecerli_dokuman(malzeme_kodu).etiket
        else:
            icerik = {"karar": karar, "malzeme": m.standart_etiketi, "isaret": m.mp_inceleme, "not": not_}
            surum = None
            try:
                surum = katalog.gecerli_dokuman(malzeme_kodu).etiket
            except KatalogHatasi:
                pass
        katalog.mp_inceleme_ata(malzeme_kodu, None)
        return defter.ekle("onay", kullanici, icerik, malzeme_kodu=malzeme_kodu, dokuman_surumu=surum)


__all__ = [
    "KapatmaKarari",
    "MP_ISARETI",
    "RevizyonEtkisi",
    "daha_eski_mi",
    "mp_bekleyenler",
    "mp_incelemesini_kapat",
    "yeni_revizyon_yukle",
]
