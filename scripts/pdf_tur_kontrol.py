#!/usr/bin/env python3
"""data/raw/ altındaki PDF'lerin metin tabanlı mı taranmış mı olduğunu listeler.

Taranmış PDF'ler atılmaz; listede "ocr_gerekli=evet" diye işaretlenir.

Kullanım:
  python scripts/pdf_tur_kontrol.py                 # data/raw -> data/raw/pdf_turleri.csv
  python scripts/pdf_tur_kontrol.py KLASOR --cikti liste.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from malzeme_kabul.belge.pdf_turu import pdf_turunu_belirle

KOK = Path(__file__).resolve().parents[1]
ALANLAR = ["dosya", "tur", "sayfa_sayisi", "taranmis_sayfalar", "ocr_katmanli_sayfalar", "ocr_gerekli"]


def _sayfalar(liste: list[int]) -> str:
    return " ".join(str(s) for s in liste)


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("klasor", nargs="?", default=str(KOK / "data" / "raw"))
    ayr.add_argument("--cikti", default=None, help="CSV çıktı yolu (varsayılan: KLASOR/pdf_turleri.csv)")
    args = ayr.parse_args(argv)

    klasor = Path(args.klasor)
    pdfler = sorted(p for p in klasor.rglob("*") if p.suffix.lower() == ".pdf")
    if not pdfler:
        print(f"PDF bulunamadı: {klasor}", file=sys.stderr)
        return 1

    satirlar = []
    for pdf in pdfler:
        ad = pdf.relative_to(klasor).as_posix()
        try:
            s = pdf_turunu_belirle(pdf)
        except ValueError as hata:
            satirlar.append(dict.fromkeys(ALANLAR, "") | {"dosya": ad, "tur": "hata", "ocr_gerekli": "?"})
            print(f"UYARI {ad}: {hata}", file=sys.stderr)
            continue
        satirlar.append({
            "dosya": ad,
            "tur": s.tur,
            "sayfa_sayisi": s.sayfa_sayisi,
            "taranmis_sayfalar": _sayfalar(s.taranmis_sayfalar),
            "ocr_katmanli_sayfalar": _sayfalar(s.ocr_katmanli_sayfalar),
            "ocr_gerekli": "evet" if s.ocr_gerekli else "hayır",
        })

    cikti = Path(args.cikti) if args.cikti else klasor / "pdf_turleri.csv"
    with cikti.open("w", encoding="utf-8", newline="") as f:
        yazici = csv.DictWriter(f, fieldnames=ALANLAR)
        yazici.writeheader()
        yazici.writerows(satirlar)

    for s in satirlar:
        isaret = "  <-- OCR gerekli" if s["ocr_gerekli"] == "evet" else ""
        print(f"{s['dosya']}: {s['tur']} ({s['sayfa_sayisi']} sayfa){isaret}")
    print(f"Liste yazıldı: {cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
