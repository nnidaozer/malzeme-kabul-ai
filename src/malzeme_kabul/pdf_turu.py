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

# Bu sayıdan az görünür karakteri olan sayfa "metinsiz" sayılır (sayfa
# numarası, tarayıcı damgası gibi kırıntılar karar değiştirmesin).
EN_AZ_KARAKTER = 25
# Resim sayfa alanının bu oranından fazlasını kaplıyorsa sayfa "taranmış"tır.
KAPLAMA_ESIGI = 0.5


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
        return bool(self.taranmis_sayfalar)


def _resim_kaplama_orani(sayfa) -> float:
    alan = float(sayfa.width * sayfa.height) or 1.0
    en_buyuk = 0.0
    for resim in sayfa.images:
        gen = max(0.0, float(resim["x1"]) - float(resim["x0"]))
        yuk = max(0.0, float(resim["bottom"]) - float(resim["top"]))
        en_buyuk = max(en_buyuk, gen * yuk / alan)
    return min(en_buyuk, 1.0)


def sayfa_turu(sayfa) -> str:
    """Tek bir pdfplumber sayfasının türünü döner."""
    karakter = sum(1 for c in sayfa.chars if not c["text"].isspace())
    metinli = karakter >= EN_AZ_KARAKTER
    resimli = _resim_kaplama_orani(sayfa) >= KAPLAMA_ESIGI
    if resimli:
        return OCR_KATMANLI if metinli else TARANMIS
    if metinli:
        return METIN
    return BOS


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
