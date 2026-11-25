#!/usr/bin/env python3
"""Depodaki partilerin son kullanma tarihlerini ve raf ömrü uyarılarını yazar.

Kullanım:
  python scripts/raf_omru.py [--db yol.sqlite] [--bugun 2026-11-25] [--esik 30] [--yalniz-uyari]
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from malzeme_kabul.hat.raf_omru_raporu import raf_raporu
from malzeme_kabul.katalog.veritabani import Katalog

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_DB = KOK / "data" / "calisma" / "katalog.sqlite"
ETIKET = {"gecerli": "geçerli", "yaklasiyor": "UYARI: yaklaşıyor", "doldu": "UYARI: doldu", "bilinmiyor": "bilinmiyor"}


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("--db", default=str(VARSAYILAN_DB))
    ayr.add_argument("--bugun", type=date.fromisoformat, default=date.today())
    ayr.add_argument("--esik", type=int, default=30, help="Kaç gün kala uyarı verilsin")
    ayr.add_argument("--yalniz-uyari", action="store_true")
    args = ayr.parse_args(argv)
    with Katalog(args.db) as katalog:
        rapor = raf_raporu(katalog, args.bugun, args.esik, args.yalniz_uyari)
    for s in rapor:
        p, r = s.parti, s.raf
        son = r.son_kullanma.isoformat() if r.son_kullanma else "-"
        kalan = f"{r.kalan_gun} gün" if r.kalan_gun is not None else "-"
        print(f"{p.malzeme_kodu} / {p.lot_no}: son kullanma {son} ({kalan}) {ETIKET[r.durum]}")
        for n in r.notlar:
            print(f"    not: {n}")
        if r.uyari:
            testler = ", ".join(f"{t.test_adi} [{t.kaynak.etiket}]" for t in s.omur_uzatma_testleri)
            print(f"    ömür uzatma testleri: {testler or 'kabul dokümanında ömür uzatma testi tanımlı değil'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
