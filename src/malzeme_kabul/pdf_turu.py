"""Bir PDF'in metin tabanlı mı taranmış mı olduğunu belirler.

Her sayfa için çıkarılabilen metin miktarına ve sayfayı kaplayan resim olup
olmadığına bakılır:

- metin: sayfada yeterli metin var, sayfayı kaplayan resim yok.
- taranmış: sayfayı kaplayan resim var, metin yok ya da birkaç karakter.
  OCR gerekir.
- ocr_katmanlı: sayfa resim ama üstünde görünmez bir metin katmanı var
  (daha önce OCR'dan geçmiş tarama). Metin okunabilir ama kalitesi
  doğrulanmalı.
- boş: ne metin ne resim; karara katılmaz.

Belgenin türü sayfalardan çıkar: hepsi aynıysa o tür, karışıksa "karma".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

METIN = "metin"
TARANMIS = "taranmış"
OCR_KATMANLI = "ocr_katmanlı"
KARMA = "karma"
BOS = "boş"

# Bu sayıdan az görünür karakteri olan sayfa "metinsiz" sayılır. Sayfa
# numarası ya da indirme sitesinin filigran satırı ("Downloaded from
# https://www.everyspec.com", ~36 karakter) karar değiştirmesin.
EN_AZ_KARAKTER = 50
# Resimler (toplam) sayfa alanının bu oranından fazlasını kaplıyorsa sayfa
# taranmış olabilir. Bazı taramalar sayfayı yatay şeritlere böler; alanlar toplanır.
KAPLAMA_ESIGI = 0.5
# Karakterlerin bu oranından fazlası resimlerin üstündeyse metin bir OCR
# katmanıdır. Şekil sayfalarında metin (başlık, açıklama) resmin dışında kalır.
OCR_ORANI = 0.7


@dataclass
class PdfTuru:
    """Bir PDF için tür kararı ve sayfa ayrıntıları (sayfa numaraları 1'den başlar)."""

    dosya: Path
    tur: str
    sayfa_sayisi: int
    taranmis_sayfalar: list[int] = field(default_factory=list)
    ocr_katmanli_sayfalar: list[int] = field(default_factory=list)

    @property
    def ocr_gerekli(self) -> bool:
        """Taranmış ya da hazır OCR katmanlı sayfa varsa OCR gerekir.

        Hazır OCR katmanının kalitesi bilinmez (EverySpec taramalarında harf
        boşluklu, bozuk metin görülür), bu yüzden bu sayfalar da yeniden OCR'a girer.
        """
        return bool(self.taranmis_sayfalar or self.ocr_katmanli_sayfalar)


def _resim_kaplama_orani(sayfa) -> float:
    alan = float(sayfa.width * sayfa.height) or 1.0
    toplam = 0.0
    for resim in sayfa.images:
        gen = max(0.0, float(resim["x1"]) - float(resim["x0"]))
        yuk = max(0.0, float(resim["bottom"]) - float(resim["top"]))
        toplam += gen * yuk
    return min(toplam / alan, 1.0)


def _resim_ustunde_mi(karakter, resimler) -> bool:
    x = (float(karakter["x0"]) + float(karakter["x1"])) / 2
    y = (float(karakter["top"]) + float(karakter["bottom"])) / 2
    return any(
        float(r["x0"]) <= x <= float(r["x1"]) and float(r["top"]) <= y <= float(r["bottom"])
        for r in resimler
    )


def sayfa_turu(sayfa) -> str:
    """Tek bir pdfplumber sayfasının türünü döner."""
    karakterler = [c for c in sayfa.chars if not c["text"].isspace()]
    metinli = len(karakterler) >= EN_AZ_KARAKTER
    resimli = _resim_kaplama_orani(sayfa) >= KAPLAMA_ESIGI
    if resimli and not metinli:
        return TARANMIS
    if resimli:
        ustte = sum(1 for c in karakterler if _resim_ustunde_mi(c, sayfa.images))
        return OCR_KATMANLI if ustte / len(karakterler) >= OCR_ORANI else METIN
    return METIN if metinli else BOS


def pdf_turunu_belirle(yol: str | Path) -> PdfTuru:
    """PDF dosyasının türünü belirler. Okunamayan dosyada ValueError verir."""
    yol = Path(yol)
    try:
        with pdfplumber.open(yol) as pdf:
            turler = [sayfa_turu(s) for s in pdf.pages]
    except (PdfminerException, PDFSyntaxError) as hata:
        raise ValueError(f"PDF okunamadı: {yol}: {hata}") from hata

    taranmis = [i for i, t in enumerate(turler, 1) if t == TARANMIS]
    ocr = [i for i, t in enumerate(turler, 1) if t == OCR_KATMANLI]
    dolu = {t for t in turler if t != BOS}
    if not dolu:
        tur = BOS
    elif len(dolu) == 1:
        tur = dolu.pop()
    else:
        tur = KARMA
    return PdfTuru(yol, tur, len(turler), taranmis, ocr)
