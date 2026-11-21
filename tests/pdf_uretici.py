"""Testler için küçük örnek PDF'ler üreten yardımcılar (reportlab ile).

Gerçek standart PDF'leri depoda yok; testler bu sahte belgelerle çalışır.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def _gorsel(tmp_dizin: Path) -> Path:
    yol = tmp_dizin / "tarama.png"
    if not yol.exists():
        Image.new("RGB", (200, 280), "white").save(yol)
    return yol


def pdf_yaz(yol: Path, sayfalar: list[dict]) -> Path:
    """Her sayfa için {"metin": [satırlar], "gorsel": bool, "tablo": [[hücreler]]} alır.

    "gorsel": True ise sayfanın tamamını kaplayan bir resim konur (taranmış sayfa
    benzetimi). "tablo" verilirse çizgili basit bir tablo çizilir.
    """
    c = canvas.Canvas(str(yol), pagesize=A4)
    genislik, yukseklik = A4
    for sayfa in sayfalar:
        if sayfa.get("gorsel"):
            c.drawImage(str(_gorsel(yol.parent)), 0, 0, width=genislik, height=yukseklik)
        y = yukseklik - 72
        for satir in sayfa.get("metin", []):
            c.drawString(72, y, satir)
            y -= 16
        tablo = sayfa.get("tablo")
        if tablo:
            sutun_gen, satir_yuk = 150, 20
            ust = y - 20
            sol = 72
            n_sat, n_sut = len(tablo), len(tablo[0])
            for i in range(n_sat + 1):
                c.line(sol, ust - i * satir_yuk, sol + n_sut * sutun_gen, ust - i * satir_yuk)
            for j in range(n_sut + 1):
                c.line(sol + j * sutun_gen, ust, sol + j * sutun_gen, ust - n_sat * satir_yuk)
            for i, satir in enumerate(tablo):
                for j, hucre in enumerate(satir):
                    c.drawString(sol + j * sutun_gen + 4, ust - (i + 1) * satir_yuk + 6, hucre)
        c.showPage()
    c.save()
    return yol
