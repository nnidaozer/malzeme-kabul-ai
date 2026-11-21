#!/usr/bin/env python3
"""Çıkarıcı çıktısını gold ile karşılaştırıp alan bazında precision, recall ve F1 yazar.

Kullanım:
  python scripts/degerlendir.py TAHMIN.json GOLD.json [--csv sonuc.csv]

İki dosya da KabulDokumani JSON'udur. Çıkış kodu: 0 başarılı, 2 geçersiz girdi.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from pydantic import ValidationError

from malzeme_kabul.degerlendirme import degerlendir
from malzeme_kabul.sema import KabulDokumani

SUTUNLAR = ["alan", "dp", "yp", "yn", "precision", "recall", "f1"]


def _oku(yol: str) -> KabulDokumani:
    return KabulDokumani.model_validate_json(Path(yol).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("tahmin")
    ayr.add_argument("gold")
    ayr.add_argument("--csv", help="Sonuç tablosunun yazılacağı CSV yolu")
    args = ayr.parse_args(argv)

    try:
        tahmin, gold = _oku(args.tahmin), _oku(args.gold)
    except (ValidationError, ValueError, OSError) as hata:
        print(f"geçersiz girdi: {hata}", file=sys.stderr)
        return 2

    satirlar = degerlendir(tahmin, gold).tablo()
    genislik = max(len(s["alan"]) for s in satirlar)
    print(f"{'alan':<{genislik}}  {'dp':>4} {'yp':>4} {'yn':>4}  {'P':>6} {'R':>6} {'F1':>6}")
    for s in satirlar:
        print(
            f"{s['alan']:<{genislik}}  {s['dp']:>4} {s['yp']:>4} {s['yn']:>4}  "
            f"{s['precision']:>6.3f} {s['recall']:>6.3f} {s['f1']:>6.3f}"
        )

    if args.csv:
        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            yazici = csv.DictWriter(f, fieldnames=SUTUNLAR)
            yazici.writeheader()
            yazici.writerows(satirlar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
