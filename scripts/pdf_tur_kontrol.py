#!/usr/bin/env python3
"""data/raw/ altındaki PDF'lerin metin tabanlı mı taranmış mı olduğunu listeler.

Taranmış PDF'ler atılmaz; listede "ocr_gerekli=evet" diye işaretlenir.
data/bolunme.yaml'daki kilitli klasörlerin (test kümesi) PDF'leri açılmaz;
listeye yalnız adlarıyla "tur=kilitli" diye yazılır.

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

# Test kümesi kilidi deney/bolunme.py'de; betik doğrudan çalışınca depo kökü yolda olsun.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deney.bolunme import VARSAYILAN_YOL, bolunme_oku  # noqa: E402

KOK = Path(__file__).resolve().parents[1]
ALANLAR = ["dosya", "tur", "sayfa_sayisi", "taranmis_sayfalar", "ocr_katmanli_sayfalar", "ocr_gerekli"]


def _sayfalar(liste: list[int]) -> str:
    return " ".join(str(s) for s in liste)


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("klasor", nargs="?", default=str(KOK / "data" / "raw"))
    ayr.add_argument("--cikti", default=None, help="CSV çıktı yolu (varsayılan: KLASOR/pdf_turleri.csv)")
    ayr.add_argument("--bolunme", default=str(VARSAYILAN_YOL), help="Geliştirme/test bölünmesi (data/bolunme.yaml)")
    args = ayr.parse_args(argv)
    bolunme = bolunme_oku(args.bolunme)

    klasor = Path(args.klasor)
    pdfler = sorted(p for p in klasor.rglob("*") if p.suffix.lower() == ".pdf")
    if not pdfler:
        print(f"PDF bulunamadı: {klasor}", file=sys.stderr)
        return 1

    satirlar = []
    for pdf in pdfler:
        ad = pdf.relative_to(klasor).as_posix()
        if bolunme.yol_kilitli_mi(pdf.relative_to(klasor)):
            satirlar.append(dict.fromkeys(ALANLAR, "") | {"dosya": ad, "tur": "kilitli"})
            continue
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
        if s["tur"] == "kilitli":
            print(f"{s['dosya']}: kilitli (test kümesi, açılmadı)")
            continue
        print(f"{s['dosya']}: {s['tur']} ({s['sayfa_sayisi']} sayfa){isaret}")
    print(f"Liste yazıldı: {cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
