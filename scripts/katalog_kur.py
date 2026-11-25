#!/usr/bin/env python3
"""SQLite kataloğu kurar; istenirse örnek veriyi yükler ve özetini yazar.

Kullanım:
  python scripts/katalog_kur.py                       # data/calisma/katalog.sqlite
  python scripts/katalog_kur.py --ornek               # + data/ornek/katalog.json
  python scripts/katalog_kur.py --db yol.sqlite --ornek
"""

from __future__ import annotations

import argparse
from pathlib import Path

from malzeme_kabul.arayuz.kimlik import KimlikHatasi, kullanici_ekle
from malzeme_kabul.katalog.ornek_veri import ornek_yukle
from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_DB = KOK / "data" / "calisma" / "katalog.sqlite"
ORNEK = KOK / "data" / "ornek" / "katalog.json"
# Yalnız deneme için; gerçek kullanımda scripts/kullanici_ekle.py ile kişisel hesap açın.
ORNEK_KULLANICILAR = [("mp", "mp-ornek-parola", "mp"), ("gk", "gk-ornek-parola", "giris_kalite")]


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("--db", default=str(VARSAYILAN_DB))
    ayr.add_argument("--ornek", action="store_true", help="data/ornek/katalog.json örnek verisini yükle")
    ayr.add_argument("--ornek-dosyasi", default=str(ORNEK))
    ayr.add_argument("--ornek-kullanicilar", action="store_true",
                     help="deneme kullanıcıları: mp / mp-ornek-parola (M&P), gk / gk-ornek-parola (giriş kalite)")
    args = ayr.parse_args(argv)

    with Katalog(args.db) as katalog:
        if args.ornek:
            ozet = ornek_yukle(katalog, args.ornek_dosyasi, KOK)
            defter = DenetimKaydi(katalog.baglanti)
            for etiket in ozet.dokuman_surumleri:
                defter.ekle("onay", "ornek-veri", {"dokuman_surumu": etiket, "not": "örnek veri, M&P onayı değil"},
                            dokuman_surumu=etiket)
            print(f"yeni doküman sürümleri: {', '.join(ozet.dokuman_surumleri) or '-'}")
            print(f"yeni malzemeler: {', '.join(ozet.malzemeler) or '-'}")
            print(f"yeni partiler: {', '.join(ozet.partiler) or '-'}")
        if args.ornek_kullanicilar:
            for ad, parola, rol in ORNEK_KULLANICILAR:
                try:
                    kullanici_ekle(katalog.baglanti, ad, parola, rol)
                    print(f"deneme kullanıcısı: {ad} / {parola} ({rol})")
                except KimlikHatasi:
                    pass
        for m in katalog.malzemeler():
            surumler = katalog.dokuman_surumleri(m.belge_no, m.revizyon)
            son = f"v{surumler[-1].surum}" if surumler else "onaylı sürüm yok"
            print(f"{m.kod}: {m.standart_etiketi} Type {m.tip} Class {m.sinif} ({son}), "
                  f"tedarikçiler: {', '.join(katalog.onayli_tedarikciler(m.kod)) or '-'}, "
                  f"parti: {len(katalog.partiler(m.kod))}")
    print(f"katalog: {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
