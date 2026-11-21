#!/usr/bin/env python3
"""Standart PDF'inden kural tabanlı çıkarıcıyla kabul dokümanı taslağı üretir.

Çıktılar (KLASOR altında): <BELGE>_kabul_dokumani.json, .md ve .docx

Kullanım:
  python scripts/kabul_dokumani_uret.py data/raw/MIL-PRF-23377K.pdf --cikti data/cikti
  python scripts/kabul_dokumani_uret.py BELGE.pdf --belge-no MIL-PRF-23377 --revizyon K
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from malzeme_kabul.dokuman_uretici import markdown_uret, word_uret
from malzeme_kabul.kural_cikarici import cikar

KOK = Path(__file__).resolve().parents[1]


def belge_no_ve_revizyon(dosya_adi: str) -> tuple[str, str]:
    """'MIL-PRF-23377K.pdf' -> ('MIL-PRF-23377', 'K')."""
    m = re.fullmatch(r"(.+\d)([A-Z])", Path(dosya_adi).stem)
    if not m:
        raise ValueError(f"dosya adından belge no ve revizyon çıkarılamadı: {dosya_adi}")
    return m.group(1), m.group(2)


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("pdf")
    ayr.add_argument("--belge-no")
    ayr.add_argument("--revizyon")
    ayr.add_argument("--cikti", default=str(KOK / "data" / "cikti"))
    args = ayr.parse_args(argv)

    if args.belge_no and args.revizyon:
        belge_no, revizyon = args.belge_no, args.revizyon
    else:
        belge_no, revizyon = belge_no_ve_revizyon(args.pdf)

    dokuman = cikar(args.pdf, belge_no=belge_no, revizyon=revizyon)
    klasor = Path(args.cikti)
    klasor.mkdir(parents=True, exist_ok=True)
    temel = klasor / f"{belge_no}{revizyon}_kabul_dokumani"
    temel.with_suffix(".json").write_text(
        dokuman.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    temel.with_suffix(".md").write_text(markdown_uret(dokuman), encoding="utf-8")
    word_uret(dokuman, temel.with_suffix(".docx"))
    print(f"{len(dokuman.testler)} test, {len(dokuman.kosullar)} koşul, "
          f"{len(dokuman.numune_hazirlama)} numune hazırlığı çıkarıldı -> {temel}.{{json,md,docx}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
