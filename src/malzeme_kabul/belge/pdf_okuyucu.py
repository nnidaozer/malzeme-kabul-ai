"""PDF'ten sayfa sayfa metin ve tablo çıkarır (pdfplumber).

Çıkarıcılar madde numarasını ve kaynak sayfayı gösterebilsin diye her satır
ve tablo, geldiği sayfanın numarasıyla (1'den başlar) tutulur.

Taranmış sayfalarda metin boş gelir. `pdf_oku(..., ocr=motor)` verilirse
`pdf_turu.sayfa_turu` "taranmış" ya da "ocr_katmanlı" diyen sayfalar yerel OCR
motorundan (belge/ocr.py, Tesseract) geçer: bu sayfaların metni OCR metnidir,
`Sayfa.kaynak = "ocr"` ve `Sayfa.ocr_guveni` (ortalama kelime güveni) taşır,
hazır OCR katmanlı sayfada pdfplumber'ın bulduğu tablolar korunur, taranmış
sayfada tablo yoktur. Metin ve boş sayfalar OCR'a gitmez; motor verilmezse
davranış değişmez (docs/ocr.md).

Güvenlik (docs/guvenlik.md, tehdit 2): tedarikçi belgesi güvenilmeyen
girdidir. Okumadan önce dosya boyutu, açınca sayfa sayısı, okurken de her
sayfadan sonra geçen süre denetlenir; sınır aşılırsa `PdfSiniriAsildi`
verilir ve belge okunmaz. Süre sınırı sayfa aralarında denetlenir; tek bir
sayfanın içinde takılan ayrıştırıcıyı kesmek için okumanın ayrı süreçte
yapılması gerekir (sonraki adım). OCR süresi de bu sınıra dahildir; OCR'a
giden her sayfa bütçeye `ocr_sayfa_basi_s` ekler.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

from malzeme_kabul.belge.ocr import OcrMotoru
from malzeme_kabul.belge.pdf_turu import OCR_KATMANLI, TARANMIS, sayfa_turu

Tablo = list[list[str]]

KAYNAK_METIN = "metin"
KAYNAK_OCR = "ocr"


class PdfSiniriAsildi(ValueError):
    """PDF boyut, sayfa ya da süre sınırını aştı; belge okunmadı."""


@dataclass(frozen=True)
class PdfSiniri:
    """Bir PDF'i okurken uygulanan üst sınırlar."""

    en_cok_bayt: int = 25 * 1024 * 1024
    en_cok_sayfa: int = 300
    en_cok_sure_s: float = 300.0
    # OCR'a giden her sayfa süre bütçesine bu kadar ekler: bütçe
    # en_cok_sure_s + ocr_sayfa_basi_s x (OCR sayfa sayısı). Metin sayfaları ek almaz.
    ocr_sayfa_basi_s: float = 30.0

    def __post_init__(self):
        for ad in ("en_cok_bayt", "en_cok_sayfa", "en_cok_sure_s", "ocr_sayfa_basi_s"):
            if getattr(self, ad) <= 0:
                raise ValueError(f"{ad} pozitif olmalı: {getattr(self, ad)!r}")


# data/raw altındaki en büyük standart 2,4 MB ve 34 sayfa; sınırlar bunun çok üstünde.
VARSAYILAN_SINIRLAR = PdfSiniri()


@dataclass
class Sayfa:
    no: int
    metin: str
    tablolar: list[Tablo] = field(default_factory=list)
    kaynak: str = KAYNAK_METIN
    ocr_guveni: float | None = None  # OCR sayfasında ortalama kelime güveni (0-100)


@dataclass
class Belge:
    dosya: Path
    sayfalar: list[Sayfa]

    @property
    def ocr_sayfalari(self) -> list[int]:
        """OCR'dan geçen sayfaların numaraları."""
        return [s.no for s in self.sayfalar if s.kaynak == KAYNAK_OCR]

    @property
    def tam_metin(self) -> str:
        """Bütün sayfaların metni, sayfalar arasında boş satırla."""
        return "\n\n".join(s.metin for s in self.sayfalar)

    def satirlar(self) -> list[tuple[int, str]]:
        """Boş olmayan satırlar, (sayfa_no, satır) olarak."""
        return [
            (s.no, satir)
            for s in self.sayfalar
            for satir in s.metin.splitlines()
            if satir.strip()
        ]

    def tablolar(self) -> list[tuple[int, Tablo]]:
        """Bütün tablolar, (sayfa_no, tablo) olarak."""
        return [(s.no, t) for s in self.sayfalar for t in s.tablolar]


def _tabloyu_temizle(ham: list[list[str | None]]) -> Tablo:
    return [[(h or "").strip() for h in satir] for satir in ham]


def pdf_oku(
    yol: str | Path,
    sinirlar: PdfSiniri | None = None,
    saat: Callable[[], float] = time.monotonic,
    ocr: OcrMotoru | None = None,
) -> Belge:
    """PDF'i okur.

    `ocr` verilirse taranmış ve hazır OCR katmanlı sayfalar motorla okunur.

    Dosya yoksa FileNotFoundError, okunamazsa ValueError, sınır aşılırsa
    PdfSiniriAsildi (bir ValueError) verir.
    """
    yol = Path(yol)
    sinirlar = sinirlar or VARSAYILAN_SINIRLAR
    if not yol.is_file():
        raise FileNotFoundError(yol)
    boyut = yol.stat().st_size
    if boyut > sinirlar.en_cok_bayt:
        raise PdfSiniriAsildi(f"PDF boyut sınırını aşıyor: {yol}: {boyut} bayt > {sinirlar.en_cok_bayt} bayt")
    baslangic = saat()
    try:
        with pdfplumber.open(yol) as pdf:
            sayfa_sayisi = len(pdf.pages)
            if sayfa_sayisi > sinirlar.en_cok_sayfa:
                raise PdfSiniriAsildi(
                    f"PDF sayfa sınırını aşıyor: {yol}: {sayfa_sayisi} sayfa > {sinirlar.en_cok_sayfa}"
                )
            turler = [sayfa_turu(s) if ocr is not None else None for s in pdf.pages]
            ocr_sayisi = sum(1 for t in turler if t in (TARANMIS, OCR_KATMANLI))
            butce = sinirlar.en_cok_sure_s + sinirlar.ocr_sayfa_basi_s * ocr_sayisi
            sayfalar = []
            for i, (sayfa, tur) in enumerate(zip(pdf.pages, turler), 1):
                if tur in (TARANMIS, OCR_KATMANLI):
                    sonuc = ocr.sayfa_oku(yol, i)
                    # Hazır katmandaki tablolar korunur; taranmış sayfada tablo yoktur.
                    tablolar = ([_tabloyu_temizle(t) for t in sayfa.extract_tables()]
                                if tur == OCR_KATMANLI else [])
                    sayfalar.append(Sayfa(no=i, metin=sonuc.metin, tablolar=tablolar, kaynak=KAYNAK_OCR,
                                          ocr_guveni=sonuc.ortalama_guven))
                else:
                    sayfalar.append(
                        Sayfa(
                            no=i,
                            metin=sayfa.extract_text() or "",
                            tablolar=[_tabloyu_temizle(t) for t in sayfa.extract_tables()],
                        )
                    )
                gecen = saat() - baslangic
                if gecen > butce:
                    raise PdfSiniriAsildi(
                        f"PDF okuma süre sınırını aştı: {yol}: {i}/{sayfa_sayisi} sayfada "
                        f"{gecen:.0f} s > {butce:g} s"
                    )
    except (PdfminerException, PDFSyntaxError) as hata:
        raise ValueError(f"PDF okunamadı: {yol}: {hata}") from hata
    return Belge(yol, sayfalar)
