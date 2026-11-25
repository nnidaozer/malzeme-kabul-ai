#!/usr/bin/env python3
"""Sertifika PDF'ini seçilen modda (kural / hibrit) okuyup katalogdaki malzeme koduna göre karar verir.

Hibrit modda dil modeli yalnız localhost'taki sunucuya gider (MALZEME_KABUL_MODELI,
MALZEME_KABUL_ARKA_UCU, MALZEME_KABUL_MODEL_ADRESI). Karar denetim kaydına yazılır.

Kullanım:
  python scripts/sertifika_kontrol.py --malzeme AST-001 --pdf S-001.pdf [--mod kural|hibrit] [--lot L] [--db yol]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from malzeme_kabul.hat.hibrit_hat import sertifika_hatti
from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_DB = KOK / "data" / "calisma" / "katalog.sqlite"


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("--malzeme", required=True)
    ayr.add_argument("--pdf", required=True)
    ayr.add_argument("--mod", choices=["kural", "hibrit"])
    ayr.add_argument("--lot")
    ayr.add_argument("--kullanici", default="komut-satiri")
    ayr.add_argument("--db", default=str(VARSAYILAN_DB))
    args = ayr.parse_args(argv)
    with Katalog(args.db) as katalog:
        karar, okuma = sertifika_hatti(katalog, args.malzeme, args.pdf, mod=args.mod, lot_no=args.lot,
                                       defter=DenetimKaydi(katalog.baglanti), kullanici=args.kullanici)
    print(f"mod: {okuma.mod}" + (f" (model {okuma.model}, istem {okuma.istem_surumu})" if okuma.model else "")
          + (f"; YEDEK: {okuma.yedek}" if okuma.yedek else ""))
    print(f"{karar.malzeme_kodu} / {karar.lot_no or '-'}: {karar.dokuman_surumu} ile karar: {karar.parti_karari} (parti {karar.parti_durumu})")
    for s in [karar.kontrol.revizyon] + ([karar.kontrol.tip_sinif] if karar.kontrol.tip_sinif else []) + karar.ek_denetimler + karar.kontrol.satirlar:
        print(f"  {s.karar:<17} {s.test_adi} [{s.madde or '-'}]: {s.gerekce}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
