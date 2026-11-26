#!/usr/bin/env python3
"""Sertifikaya (JSON) katalogdaki malzeme koduna göre karar verir.

Kabul dokümanı dosyadan değil, katalogdan (en son onaylı sürüm) gelir. Karar
aynı veritabanındaki denetim kaydına yazılır.

Kullanım:
  python scripts/karar_ver.py --malzeme AST-001 --sertifika S-001.json [--lot A-2512-01] [--db yol.sqlite]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from malzeme_kabul.hat.katalog_karari import malzeme_koduyla_kontrol
from malzeme_kabul.katalog.veritabani import DEMO_ETIKETI, Katalog
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.sozlesme.sertifika import Sertifika

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_DB = KOK / "data" / "calisma" / "katalog.sqlite"


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("--malzeme", required=True)
    ayr.add_argument("--sertifika", required=True)
    ayr.add_argument("--lot")
    ayr.add_argument("--db", default=str(VARSAYILAN_DB))
    ayr.add_argument("--kullanici", default="komut-satiri", help="Denetim kaydına yazılacak kullanıcı")
    args = ayr.parse_args(argv)

    sertifika = Sertifika.model_validate_json(Path(args.sertifika).read_text(encoding="utf-8"))
    with Katalog(args.db) as katalog:
        defter = DenetimKaydi(katalog.baglanti)
        k = malzeme_koduyla_kontrol(katalog, args.malzeme, sertifika, lot_no=args.lot, defter=defter, kullanici=args.kullanici)
    print(f"{k.malzeme_kodu} / {k.lot_no or '-'}: {k.dokuman_surumu} ile karar: {k.parti_karari} (parti {k.parti_durumu})"
          + (f", {DEMO_ETIKETI}" if k.demo_onayi else ""))
    satirlar = [k.kontrol.revizyon] + ([k.kontrol.tip_sinif] if k.kontrol.tip_sinif else []) + k.ek_denetimler + k.kontrol.satirlar
    for s in satirlar:
        print(f"  {s.karar:<17} {s.test_adi} [{s.madde or '-'}]: {s.gerekce}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
