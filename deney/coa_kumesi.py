"""Gerçek CoA'ların ölçüm kümesi: "tam" ve "eksik" sertifikalar.

Kural (Nida, 24 Kasım 2026): bir sertifika "tam" sayılır, eğer

- ürününün (tedarikçi + katalog numarası) en az iki farklı lotu listede varsa ve
- ürünün sertifikadan ayrı bir şartname dosyası varsa (liste.csv'de adı yazılı,
  dosya klasörde duruyor ve sertifikanın kendisi değil).

Ölçümde yalnız "tam" sertifikalar kullanılır (`olcum_sertifikalari`); "eksik"
olanlar nedeniyle birlikte ayrı listelenir. Liste `data/coa_kumesi.csv` dosyasına
yazılır; test, dosyanın liste.csv ile güncel olduğunu denetler.

Kullanım:
  python deney/coa_kumesi.py                       # data/raw/gercek_coa -> data/coa_kumesi.csv
  python deney/coa_kumesi.py KLASOR --cikti kume.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_KLASOR = KOK / "data" / "raw" / "gercek_coa"
VARSAYILAN_CIKTI = KOK / "data" / "coa_kumesi.csv"
ALANLAR = ["sertifika", "urun", "tedarikci", "katalog", "lot", "sartname", "lot_sayisi", "durum", "neden"]


def coa_durumlari(klasor: str | Path = VARSAYILAN_KLASOR) -> list[dict]:
    """liste.csv'deki her sertifika için durum ("tam" / "eksik") ve eksiklik nedenini, liste sırasıyla döner."""
    klasor = Path(klasor)
    with (klasor / "liste.csv").open(encoding="utf-8-sig", newline="") as f:
        satirlar = list(csv.DictReader(f))
    lotlar: dict[tuple[str, str], set[str]] = defaultdict(set)
    for s in satirlar:
        lotlar[(s["tedarikci"], s["katalog_numarasi"])].add(s["lot_numarasi"])
    sonuc = []
    for s in satirlar:
        lot_sayisi = len(lotlar[(s["tedarikci"], s["katalog_numarasi"])])
        sartname = s["sartname_dosya_adi"].strip()
        nedenler = []
        if lot_sayisi < 2:
            nedenler.append("tek lot")
        if not sartname or sartname == s["sertifika_dosya_adi"]:
            nedenler.append("şartname yok")
        elif not (klasor / sartname).is_file():
            nedenler.append("şartname dosyası yok")
        sonuc.append({
            "sertifika": s["sertifika_dosya_adi"],
            "urun": s["urun"],
            "tedarikci": s["tedarikci"],
            "katalog": s["katalog_numarasi"],
            "lot": s["lot_numarasi"],
            "sartname": sartname,
            "lot_sayisi": lot_sayisi,
            "durum": "eksik" if nedenler else "tam",
            "neden": "; ".join(nedenler),
        })
    return sonuc


def olcum_sertifikalari(klasor: str | Path = VARSAYILAN_KLASOR) -> list[str]:
    """Ölçüme girecek (tam) sertifikaların dosya adları, liste sırasıyla."""
    return [d["sertifika"] for d in coa_durumlari(klasor) if d["durum"] == "tam"]


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description="Gerçek CoA'ları tam / eksik diye işaretler.")
    ayr.add_argument("klasor", nargs="?", default=str(VARSAYILAN_KLASOR))
    ayr.add_argument("--cikti", default=str(VARSAYILAN_CIKTI))
    args = ayr.parse_args(argv)
    durumlar = coa_durumlari(args.klasor)
    with Path(args.cikti).open("w", encoding="utf-8", newline="") as f:
        yazici = csv.DictWriter(f, fieldnames=ALANLAR)
        yazici.writeheader()
        yazici.writerows(durumlar)
    tam = sum(d["durum"] == "tam" for d in durumlar)
    urunler = {(d["tedarikci"], d["katalog"]) for d in durumlar if d["durum"] == "tam"}
    print(f"tam: {tam}, eksik: {len(durumlar) - tam} (tam ürün: {len(urunler)}); liste yazıldı: {args.cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
