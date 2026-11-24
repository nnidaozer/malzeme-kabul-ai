#!/usr/bin/env python3
"""Standart PDF'inden yerel dil modeliyle ("yalnız dil modeli") kabul dokümanı taslağı çıkarır.

Model yerel bir Ollama ya da llama.cpp sunucusunda çalışır; betik yalnız
localhost'a bağlanır. Çıktılar (KLASOR altında):
  <BELGE>_dil_modeli_<model>.json        KabulDokumani (yalnız testler)
  <BELGE>_dil_modeli_<model>_rapor.json  sayfa başına süre, hata, tekrar

Kullanım:
  python deney/dil_modeli_cikar.py data/raw/MIL-PRF-23377K.pdf --model qwen2.5:7b
  python deney/dil_modeli_cikar.py BELGE.pdf --model yerel --arka-uc llamacpp --sayfalar 5-14
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# `python deney/<betik>.py` ile doğrudan çalışınca depo kökü yolda olsun (deney paketi için).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from malzeme_kabul.belge.adlandirma import belge_no_ve_revizyon

from malzeme_kabul.belge.pdf_okuyucu import pdf_oku
from malzeme_kabul.cikarim.yerel_model import ARKA_UCLAR, YerelModelIstemcisi

from deney.yalniz_dil_modeli import belgeden_cikar

KOK = Path(__file__).resolve().parents[1]


def sayfa_araligi(metin: str) -> set[int]:
    """'3-5,8' -> {3, 4, 5, 8}."""
    sayfalar: set[int] = set()
    for parca in metin.split(","):
        bas, _, son = parca.strip().partition("-")
        a, b = int(bas), int(son or bas)
        if a < 1 or b < a:
            raise ValueError(f"geçersiz sayfa aralığı: {parca!r}")
        sayfalar.update(range(a, b + 1))
    return sayfalar


def dosya_eki(model: str) -> str:
    """Model adını dosya adında kullanılabilir hale getirir: 'qwen2.5:7b' -> 'qwen2.5_7b'."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("_")


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("pdf")
    ayr.add_argument("--model", required=True, help="Ollama etiketi (ör. qwen2.5:7b) ya da llama.cpp model adı")
    ayr.add_argument("--arka-uc", choices=sorted(ARKA_UCLAR), default="ollama")
    ayr.add_argument("--adres", help="Yerel sunucu adresi; boşsa arka ucun varsayılanı")
    ayr.add_argument("--belge-no")
    ayr.add_argument("--revizyon")
    ayr.add_argument("--sayfalar", type=sayfa_araligi, help="Yalnız bu sayfalar, ör. 5-14,20")
    ayr.add_argument("--baglam", type=int, default=8192, help="Bağlam penceresi (token)")
    ayr.add_argument("--dusunme-kapali", action="store_true", help="Qwen3 gibi modellerde düşünme kipini kapatır")
    ayr.add_argument("--cikti", default=str(KOK / "data" / "cikti" / "dil_modeli"))
    args = ayr.parse_args(argv)

    if args.belge_no and args.revizyon:
        belge_no, revizyon = args.belge_no, args.revizyon
    else:
        belge_no, revizyon = belge_no_ve_revizyon(args.pdf)

    istemci = YerelModelIstemcisi(
        model=args.model, arka_uc=args.arka_uc, adres=args.adres, baglam=args.baglam,
        dusunme=False if args.dusunme_kapali else None,
    )
    dokuman, rapor = belgeden_cikar(pdf_oku(args.pdf), belge_no, revizyon, istemci, sayfalar=args.sayfalar)

    klasor = Path(args.cikti)
    klasor.mkdir(parents=True, exist_ok=True)
    temel = klasor / f"{belge_no}{revizyon}_dil_modeli_{dosya_eki(args.model)}"
    temel.with_suffix(".json").write_text(dokuman.model_dump_json(indent=2) + "\n", encoding="utf-8")
    ozet = {"model": args.model, "arka_uc": args.arka_uc, "belge": f"{belge_no}{revizyon}", **rapor.sozluk()}
    Path(f"{temel}_rapor.json").write_text(json.dumps(ozet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    hatali = sum(1 for s in rapor.sayfalar if s.hatalar)
    print(f"{rapor.test_sayisi} test, {len(rapor.sayfalar)} sayfa ({hatali} sayfada hata), "
          f"{rapor.toplam_sure_s:.1f} s -> {temel}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
