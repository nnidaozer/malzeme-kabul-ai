"""PDF'ten sayfa sayfa metin ve tablo çıkarır (pdfplumber).

Çıkarıcılar madde numarasını ve kaynak sayfayı gösterebilsin diye her satır
ve tablo, geldiği sayfanın numarasıyla (1'den başlar) tutulur. Taranmış
sayfalarda metin boş gelir; OCR ayrı bir adımdır.

Güvenlik (docs/guvenlik.md, tehdit 2): tedarikçi belgesi güvenilmeyen
girdidir. Okumadan önce dosya boyutu, açınca sayfa sayısı, okurken de her
sayfadan sonra geçen süre denetlenir; sınır aşılırsa `PdfSiniriAsildi`
verilir ve belge okunmaz. Süre sınırı sayfa aralarında denetlenir; tek bir
sayfanın içinde takılan ayrıştırıcıyı kesmek için okumanın ayrı süreçte
yapılması gerekir (sonraki adım).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

Tablo = list[list[str]]


class PdfSiniriAsildi(ValueError):
    """PDF boyut, sayfa ya da süre sınırını aştı; belge okunmadı."""


@dataclass(frozen=True)
class PdfSiniri:
    """Bir PDF'i okurken uygulanan üst sınırlar."""

    en_cok_bayt: int = 25 * 1024 * 1024
    en_cok_sayfa: int = 300
    en_cok_sure_s: float = 300.0

    def __post_init__(self):
        for ad in ("en_cok_bayt", "en_cok_sayfa", "en_cok_sure_s"):
            if getattr(self, ad) <= 0:
                raise ValueError(f"{ad} pozitif olmalı: {getattr(self, ad)!r}")


# data/raw altındaki en büyük standart 2,4 MB ve 34 sayfa; sınırlar bunun çok üstünde.
VARSAYILAN_SINIRLAR = PdfSiniri()


@dataclass
class Sayfa:
    no: int
    metin: str
    tablolar: list[Tablo] = field(default_factory=list)


@dataclass
class Belge:
    dosya: Path
    sayfalar: list[Sayfa]

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
) -> Belge:
    """PDF'i okur.

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
            sayfalar = []
            for i, sayfa in enumerate(pdf.pages, 1):
                sayfalar.append(
                    Sayfa(
                        no=i,
                        metin=sayfa.extract_text() or "",
                        tablolar=[_tabloyu_temizle(t) for t in sayfa.extract_tables()],
                    )
                )
                gecen = saat() - baslangic
                if gecen > sinirlar.en_cok_sure_s:
                    raise PdfSiniriAsildi(
                        f"PDF okuma süre sınırını aştı: {yol}: {i}/{sayfa_sayisi} sayfada "
                        f"{gecen:.0f} s > {sinirlar.en_cok_sure_s:g} s"
                    )
    except (PdfminerException, PDFSyntaxError) as hata:
        raise ValueError(f"PDF okunamadı: {yol}: {hata}") from hata
    return Belge(yol, sayfalar)
