#!/usr/bin/env python3
"""Bir standardın iki revizyonunu karşılaştırır, fark raporu ve güncelleme önerileri yazar.

Çıktılar (KLASOR altında): <BELGE>_<ESKI>-<YENI>_revizyon_farklari.json ve .md

Güncelleme önerileri için eski revizyonun kabul dokümanı gerekir. --dokuman
verilmezse eski revizyondan kural tabanlı çıkarıcıyla taslak üretilir ve
öneriler o taslağa göre yazılır.

Kullanım:
  python scripts/revizyon_karsilastir.py data/raw/MIL-PRF-23377J.pdf data/raw/MIL-PRF-23377K.pdf
  python scripts/revizyon_karsilastir.py ESKI.pdf YENI.pdf --dokuman ESKI_kabul_dokumani.json --cikti data/cikti
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from malzeme_kabul.belge.adlandirma import belge_no_ve_revizyon
from malzeme_kabul.cikarim.kural_cikarici import cikar
from malzeme_kabul.revizyon.revizyon_karsilastirici import (
    guncelleme_onerileri,
    markdown_raporu,
    revizyonlari_karsilastir,
)
from malzeme_kabul.sozlesme.sema import KabulDokumani

# Test kümesi kilidi deney/bolunme.py'de; betik doğrudan çalışınca depo kökü yolda olsun.
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deney.bolunme import VARSAYILAN_YOL, betik_korumasi  # noqa: E402

KOK = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("eski_pdf")
    ayr.add_argument("yeni_pdf")
    ayr.add_argument("--dokuman", help="Eski revizyonun kabul dokümanı (JSON).")
    ayr.add_argument("--cikti", default=str(KOK / "data" / "cikti"))
    ayr.add_argument("--bolunme", default=str(VARSAYILAN_YOL), help="Geliştirme/test bölünmesi (data/bolunme.yaml)")
    args = ayr.parse_args(argv)

    belge_no, eski_rev = belge_no_ve_revizyon(args.eski_pdf)
    yeni_belge_no, yeni_rev = belge_no_ve_revizyon(args.yeni_pdf)
    if belge_no != yeni_belge_no:
        ayr.error(f"iki PDF aynı standardın revizyonları olmalı: {belge_no} ≠ {yeni_belge_no}")
    for rev in (eski_rev, yeni_rev):
        if (kod := betik_korumasi(f"{belge_no}{rev}", args.bolunme, "revizyon_karsilastir")) is not None:
            return kod

    fark = revizyonlari_karsilastir(args.eski_pdf, args.yeni_pdf, belge_no, eski_rev, yeni_rev)
    if args.dokuman:
        dokuman = KabulDokumani.model_validate_json(Path(args.dokuman).read_text(encoding="utf-8"))
    else:
        dokuman = cikar(args.eski_pdf, belge_no=belge_no, revizyon=eski_rev)
    oneriler = guncelleme_onerileri(fark, dokuman)

    klasor = Path(args.cikti)
    klasor.mkdir(parents=True, exist_ok=True)
    temel = klasor / f"{belge_no}_{eski_rev}-{yeni_rev}_revizyon_farklari"
    temel.with_suffix(".json").write_text(fark.json(oneriler), encoding="utf-8")
    temel.with_suffix(".md").write_text(markdown_raporu(fark, oneriler), encoding="utf-8")

    oz = fark.ozet()
    print(
        f"{fark.eski_etiket} → {fark.yeni_etiket}: {oz['eklenen_sart']} eklenen, {oz['kaldirilan_sart']} kaldırılan, "
        f"{oz['degisen_sart']} değişen ({oz['sayisal_degisen_sart']} sayısal), "
        f"{oz['yeniden_numaralanan_sart']} numarası değişen madde; {len(oneriler)} öneri. -> {temel}.md"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
