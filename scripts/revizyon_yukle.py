#!/usr/bin/env python3
"""Standardın yeni revizyonunu kataloğa ekler; etkilenen malzeme ve partileri "M&P incelemesi bekliyor" işaretler.

İsteğe bağlı `--fark` scripts/revizyon_karsilastir.py'nin JSON çıktısıdır; özeti olaya eklenir.

Kullanım:
  python scripts/revizyon_yukle.py --belge-no MIL-PRF-23377 --revizyon L [--fark fark.json] [--db yol.sqlite]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from malzeme_kabul.hat.revizyon_etkisi import yeni_revizyon_yukle
from malzeme_kabul.katalog.veritabani import Katalog

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_DB = KOK / "data" / "calisma" / "katalog.sqlite"


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("--belge-no", required=True)
    ayr.add_argument("--revizyon", required=True)
    ayr.add_argument("--baslik")
    ayr.add_argument("--fark", help="revizyon_karsilastir.py JSON çıktısı")
    ayr.add_argument("--kullanici", default="komut-satiri")
    ayr.add_argument("--db", default=str(VARSAYILAN_DB))
    args = ayr.parse_args(argv)
    ozet = json.loads(Path(args.fark).read_text(encoding="utf-8")).get("ozet") if args.fark else None
    with Katalog(args.db) as katalog:
        etki = yeni_revizyon_yukle(katalog, args.belge_no, args.revizyon, args.kullanici, args.baslik, fark_ozeti=ozet)
    print(f"{etki.yeni_etiket} eklendi.")
    print(f"M&P incelemesi bekleyen malzemeler: {', '.join(etki.etkilenen_malzemeler) or '-'}")
    print(f"İşaretlenen partiler: {', '.join(etki.etkilenen_partiler) or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
