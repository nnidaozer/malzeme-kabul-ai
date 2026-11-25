#!/usr/bin/env python3
"""Denetim kaydının hash zincirini doğrular. Zincir sağlamsa 0, bozuksa 1 döner.

Kullanım:
  python scripts/denetim_dogrula.py [--db data/calisma/katalog.sqlite] [--son-ozet HEX]

`--son-ozet` dışarıda saklanmış son özetse zincirin onunla bittiği de denetlenir.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_DB = KOK / "data" / "calisma" / "katalog.sqlite"


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("--db", default=str(VARSAYILAN_DB))
    ayr.add_argument("--son-ozet")
    args = ayr.parse_args(argv)
    if not Path(args.db).is_file():
        print(f"veritabanı yok: {args.db}")
        return 1
    with DenetimKaydi(args.db) as defter:
        s = defter.zinciri_dogrula(args.son_ozet)
    if s.gecerli:
        print(f"zincir sağlam: {s.kayit_sayisi} kayıt, son özet {s.son_ozet}")
        return 0
    yer = f"kayıt {s.bozuk_sira}" if s.bozuk_sira is not None else "zincir sonu"
    print(f"ZİNCİR BOZUK ({yer}): {s.neden}; ilk {s.kayit_sayisi} kayıt sağlam")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
