"""PDF'ten sayfa sayfa metin ve tablo çıkarır (pdfplumber).

Çıkarıcılar madde numarasını ve kaynak sayfayı gösterebilsin diye her satır
ve tablo, geldiği sayfanın numarasıyla (1'den başlar) tutulur. Taranmış
sayfalarda metin boş gelir; OCR ayrı bir adımdır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

Tablo = list[list[str]]


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


def pdf_oku(yol: str | Path) -> Belge:
    """PDF'i okur. Dosya yoksa FileNotFoundError, okunamazsa ValueError verir."""
    yol = Path(yol)
    if not yol.is_file():
        raise FileNotFoundError(yol)
    try:
        with pdfplumber.open(yol) as pdf:
            sayfalar = [
                Sayfa(
                    no=i,
                    metin=sayfa.extract_text() or "",
                    tablolar=[_tabloyu_temizle(t) for t in sayfa.extract_tables()],
                )
                for i, sayfa in enumerate(pdf.pages, 1)
            ]
    except (PdfminerException, PDFSyntaxError) as hata:
        raise ValueError(f"PDF okunamadı: {yol}: {hata}") from hata
    return Belge(yol, sayfalar)
