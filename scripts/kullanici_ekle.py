#!/usr/bin/env python3
"""Arayüz kullanıcısı ekler (rol: mp ya da giris_kalite). Parola sorulur ya da MALZEME_KABUL_PAROLA'dan okunur.

Kullanım:
  python scripts/kullanici_ekle.py --ad nida --rol mp [--db yol.sqlite]
"""

from __future__ import annotations

import argparse
import getpass
import os
import sqlite3
from pathlib import Path

from malzeme_kabul.arayuz.kimlik import ROLLER, kullanici_ekle

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_DB = KOK / "data" / "calisma" / "katalog.sqlite"


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("--ad", required=True)
    ayr.add_argument("--rol", required=True, choices=sorted(ROLLER))
    ayr.add_argument("--db", default=str(VARSAYILAN_DB))
    args = ayr.parse_args(argv)
    parola = os.environ.get("MALZEME_KABUL_PAROLA") or getpass.getpass("Parola: ")
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.db) as b:
        k = kullanici_ekle(b, args.ad, parola, args.rol)
    print(f"kullanıcı eklendi: {k.ad} ({k.rol_adi})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
