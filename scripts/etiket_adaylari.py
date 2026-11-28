#!/usr/bin/env python3
"""Onaylı taslakları etiket adayı olarak dışa verir ve düzeltme oranını basar.

Kullanım:
  python scripts/etiket_adaylari.py [--db data/calisma/katalog.sqlite] [--klasor data/calisma/etiket_adaylari]
                                    [--uzerine-yaz]

Her onaylı taslak için `<belge>_taslak<id>.json` ve `<belge>_taslak<id>.olaylar.jsonl`
yazılır (`kayit.duzeltme_kaydi.etiket_adayi_yaz`). data/gold/ altına yazılmaz:
klasör `gold_yolu_mu` ise (büyük/küçük harf, sondaki nokta/boşluk ve bağlantılar
dahil) hiçbir şey yazılmadan 2 ile çıkar. Gold'a adayları proje sahibi elle taşır.

Var olan aday dosyasının üzerine yazılmaz (taslak "atlandı" diye basılır; elle
yapılmış düzeltmeler korunur); `--uzerine-yaz` ile yenilenir. Bir taslakta hata
olursa hata basılır, diğer taslaklarla devam edilir ve sonunda 2 döner.
Veritabanı yoksa 1 döner.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kayit.duzeltme_kaydi import (
    DuzeltmeKaydi,
    duzeltme_panosu,
    etiket_adayi_yaz,
    gold_yolu_mu,
)

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_DB = KOK / "data" / "calisma" / "katalog.sqlite"
VARSAYILAN_KLASOR = KOK / "data" / "calisma" / "etiket_adaylari"


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("--db", default=str(VARSAYILAN_DB))
    ayr.add_argument("--klasor", default=str(VARSAYILAN_KLASOR))
    ayr.add_argument("--uzerine-yaz", action="store_true", help="var olan aday dosyalarını yenile")
    args = ayr.parse_args(argv)
    klasor = Path(args.klasor)
    if gold_yolu_mu(klasor):
        print(f"reddedildi: etiket adayı data/gold/ altına yazılmaz ({klasor})")
        return 2
    if not Path(args.db).is_file():
        print(f"veritabanı yok: {args.db}")
        return 1
    yazilan = atlanan = hatali = 0
    with Katalog(args.db) as katalog:
        DuzeltmeKaydi(katalog.baglanti)
        for taslak in katalog.taslaklar():
            if taslak.durum != "onaylandi":
                continue
            try:
                # Modül düzeyindeki ad üzerinden çağrılır (testler bu adı değiştirebilir).
                yollar = etiket_adayi_yaz(katalog, taslak.id, klasor, uzerine_yaz=args.uzerine_yaz)
            except FileExistsError as hata:
                print(f"taslak {taslak.id} atlandı: {hata} (yenilemek için --uzerine-yaz)")
                atlanan += 1
                continue
            except (OSError, ValueError, sqlite3.Error) as hata:
                print(f"taslak {taslak.id} dışa verilemedi: {hata}")
                hatali += 1
                continue
            for yol in yollar:
                print(yol)
            yazilan += 1
        p = duzeltme_panosu(katalog.baglanti)
    print(f"{yazilan} onaylı taslak dışa verildi, {atlanan} atlandı, {hatali} hatalı: {klasor}")
    print(f"Düzeltme oranı: {p.oran:.1%} ({p.duzeltilen_alan}/{p.toplam_alan} alan); "
          f"onay bekleyen düzeltme: {p.onay_bekleyen_duzeltme}; "
          f"tabanı bilinmeyen taslak: {p.tabani_bilinmeyen_taslak}")
    return 2 if hatali else 0


if __name__ == "__main__":
    raise SystemExit(main())
