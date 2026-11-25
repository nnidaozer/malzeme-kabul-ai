#!/usr/bin/env python3
"""Çıkarıcı çıktısını gold ile karşılaştırıp alan bazında precision, recall ve F1 yazar.

Kullanım:
  python deney/degerlendir.py TAHMIN.json GOLD.json [--csv sonuc.csv] [--bolumler] [--bolum-csv bolum.csv]

Son iki satır genel F1'dir: mikro (bütün alanlar) ve bölüm ortalaması (her
şart maddesinin F1'inin ortalaması; büyük bir tablo ölçümü domine etmesin).
`--bolumler` bölüm başına tabloyu da yazar.

İki dosya da KabulDokumani JSON'udur. Çıkış kodu: 0 başarılı, 2 geçersiz girdi.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from pydantic import ValidationError

# `python deney/<betik>.py` ile doğrudan çalışınca depo kökü yolda olsun (deney paketi için).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deney.bolunme import VARSAYILAN_YOL, betik_korumasi
from deney.degerlendirme import degerlendir
from malzeme_kabul.sozlesme.sema import KabulDokumani

SUTUNLAR = ["alan", "dp", "yp", "yn", "precision", "recall", "f1"]


def _oku(yol: str) -> KabulDokumani:
    return KabulDokumani.model_validate_json(Path(yol).read_text(encoding="utf-8"))


def _yaz(satirlar: list[dict], ad: str) -> None:
    genislik = max(len(ad), *(len(s[ad]) for s in satirlar))
    print(f"{ad:<{genislik}}  {'dp':>4} {'yp':>4} {'yn':>4}  {'P':>6} {'R':>6} {'F1':>6}")
    for s in satirlar:
        print(
            f"{s[ad]:<{genislik}}  {s['dp']:>4} {s['yp']:>4} {s['yn']:>4}  "
            f"{s['precision']:>6.3f} {s['recall']:>6.3f} {s['f1']:>6.3f}"
        )


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("tahmin")
    ayr.add_argument("gold")
    ayr.add_argument("--csv", help="Sonuç tablosunun yazılacağı CSV yolu")
    ayr.add_argument("--bolumler", action="store_true", help="Bölüm (şart maddesi) başına tabloyu da yaz")
    ayr.add_argument("--bolum-csv", help="Bölüm tablosunun yazılacağı CSV yolu")
    ayr.add_argument("--bolunme", default=str(VARSAYILAN_YOL), help="Geliştirme/test bölünmesi (data/bolunme.yaml)")
    args = ayr.parse_args(argv)

    try:
        tahmin, gold = _oku(args.tahmin), _oku(args.gold)
    except (ValidationError, ValueError, OSError) as hata:
        print(f"geçersiz girdi: {hata}", file=sys.stderr)
        return 2
    std = f"{gold.standart.belge_no}{gold.standart.revizyon}"
    if (kod := betik_korumasi(std, args.bolunme, "degerlendir")) is not None:
        return kod

    sonuc = degerlendir(tahmin, gold)
    satirlar = sonuc.tablo()
    _yaz(satirlar, "alan")
    if args.bolumler:
        print()
        _yaz(sonuc.bolum_tablosu(), "bolum")
    if args.bolum_csv:
        with open(args.bolum_csv, "w", encoding="utf-8", newline="") as f:
            yazici = csv.DictWriter(f, fieldnames=["bolum"] + SUTUNLAR[1:])
            yazici.writeheader()
            yazici.writerows(sonuc.bolum_tablosu())

    if args.csv:
        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            yazici = csv.DictWriter(f, fieldnames=SUTUNLAR)
            yazici.writeheader()
            yazici.writerows(satirlar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
