#!/usr/bin/env python3
"""Denetim kaydının hash zincirini doğrular. Zincir sağlamsa 0, bozuksa 1 döner.

Kullanım:
  python scripts/denetim_dogrula.py [--db data/calisma/katalog.sqlite] [--son-ozet HEX]

`--son-ozet` dışarıda saklanmış son özetse zincirin onunla bittiği de denetlenir.

Veritabanı salt okunur açılır (`mode=ro`); şema kurulmaz ya da onarılmaz.
Denetim tablosu ya da tetikleyicilerinden biri yoksa zincir bozuk sayılır
(tablo silinip ya da tetikleyici kaldırılıp boşaltılmışsa "0 kayıt" sağlam
değildir).
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi, sema_eksikleri

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
    try:
        baglanti = sqlite3.connect(f"{Path(args.db).resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as hata:
        print(f"ZİNCİR BOZUK (veritabanı açılamadı): {hata}")
        return 1
    try:
        try:
            eksik = sema_eksikleri(baglanti)
        except sqlite3.DatabaseError as hata:
            print(f"ZİNCİR BOZUK (veritabanı okunamadı): {hata}")
            return 1
        if eksik:
            print(f"ZİNCİR BOZUK (şema): eksik {', '.join(eksik)}")
            return 1
        try:
            # Şema tam olduğu için CREATE ... IF NOT EXISTS hiçbir şey yazmaz; bağlantı zaten salt okunur.
            s = DenetimKaydi(baglanti).zinciri_dogrula(args.son_ozet)
        except sqlite3.DatabaseError as hata:
            print(f"ZİNCİR BOZUK (veritabanı okunamadı): {hata}")
            return 1
    finally:
        baglanti.close()
    if s.gecerli:
        print(f"zincir sağlam: {s.kayit_sayisi} kayıt, son özet {s.son_ozet}")
        return 0
    yer = f"kayıt {s.bozuk_sira}" if s.bozuk_sira is not None else "zincir sonu"
    print(f"ZİNCİR BOZUK ({yer}): {s.neden}; öncesindeki {s.kayit_sayisi} kayıt zincirle tutarlı")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
