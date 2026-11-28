#!/usr/bin/env python3
"""Güven skoru için risk–kapsam eğrisi, AURC, CSV ve SVG (docs/guven_skoru.md).

Eşik t için güveni t'nin üstünde (>= t) olan ve zorunlu incelemede olmayan
testler otomatik geçer. kapsam = otomatik / bütün test, risk = otomatik
geçenler içinde hatalı oranı. AURC eğrinin (yamuk kuralı) altındaki alandır;
küçük daha iyi.

Kullanım:
  python deney/risk_kapsam.py deney/sonuclar/guven_skoru/tahminler.csv --cikti deney/sonuclar/guven_skoru

Girdi deney/guven_egitimi.py'nin tahminler.csv'sidir. Çıktılar: risk_kapsam.csv,
risk_kapsam.svg; AURC stdout'a yazılır. data/gold altına çıktı ya da
data/bolunme.yaml'daki test kümesinden ya da taranmış (OCR gerekli) bir belge 2
koduyla reddedilir.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deney.bolunme import VARSAYILAN_YOL, TestKumesiKilitli, bolunme_oku
from malzeme_kabul.kural.guven_skoru import _gold_altinda_mi

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_CIKTI = KOK / "deney" / "sonuclar" / "guven_skoru"
SUTUNLAR = ["esik", "kapsam", "risk", "otomatik", "hatali_otomatik"]


@dataclass(frozen=True)
class EgriNoktasi:
    esik: float
    kapsam: float
    risk: float
    otomatik: int
    hatali_otomatik: int


def egri(guvenler: list[float], hatalilar: list[bool], zorunlular: list[bool]) -> list[EgriNoktasi]:
    """İlk nokta (eşik sonsuz) boş kapsamdır; sonra zorunlu olmayan her ayrı güven büyükten küçüğe."""
    if not len(guvenler) == len(hatalilar) == len(zorunlular):
        raise ValueError("guvenler, hatalilar ve zorunlular aynı uzunlukta olmalı")
    toplam = len(guvenler)
    adaylar = [(g, h) for g, h, z in zip(guvenler, hatalilar, zorunlular) if not z and not math.isnan(g)]
    noktalar = [EgriNoktasi(math.inf, 0.0, 0.0, 0, 0)]
    for esik in sorted({g for g, _ in adaylar}, reverse=True):
        gecen = [h for g, h in adaylar if g >= esik]
        hatali = sum(1 for h in gecen if h)
        noktalar.append(EgriNoktasi(esik, len(gecen) / toplam, hatali / len(gecen), len(gecen), hatali))
    return noktalar


def aurc(noktalar: list[EgriNoktasi]) -> float:
    """Risk–kapsam eğrisinin altındaki alan (yamuk kuralı, kapsam ekseninde)."""
    return sum((b.kapsam - a.kapsam) * (a.risk + b.risk) / 2 for a, b in zip(noktalar, noktalar[1:]))


def svg_ciz(noktalar: list[EgriNoktasi], baslik: str) -> str:
    """Elle yazılmış küçük bir SVG (x: kapsam, y: risk); başlık XML kaçışlıdır."""
    gen, yuk, kenar = 480, 360, 50
    ust_risk = max([n.risk for n in noktalar] + [0.0]) or 1.0

    def x(k: float) -> float:
        return kenar + k * (gen - 2 * kenar)

    def y(r: float) -> float:
        return yuk - kenar - (r / ust_risk) * (yuk - 2 * kenar)

    noktalar_metni = " ".join(f"{x(n.kapsam):.2f},{y(n.risk):.2f}" for n in noktalar)
    b = escape(baslik)
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{gen}" height="{yuk}" viewBox="0 0 {gen} {yuk}">',
        f"<title>{b}</title>",
        f'<text x="{gen / 2}" y="25" text-anchor="middle" font-size="14">{b}</text>',
        f'<line x1="{x(0)}" y1="{y(0)}" x2="{x(1)}" y2="{y(0)}" stroke="black"/>',
        f'<line x1="{x(0)}" y1="{y(0)}" x2="{x(0)}" y2="{y(ust_risk)}" stroke="black"/>',
        f'<text x="{gen / 2}" y="{yuk - 10}" text-anchor="middle" font-size="12">kapsam</text>',
        f'<text x="15" y="{yuk / 2}" text-anchor="middle" font-size="12" '
        f'transform="rotate(-90 15 {yuk / 2})">risk (en çok {ust_risk:.3f})</text>',
        f'<polyline points="{noktalar_metni}" fill="none" stroke="steelblue" stroke-width="2"/>',
        "</svg>",
        "",
    ])


def _ikili(metin: str) -> bool:
    m = metin.strip().casefold()
    if m not in ("1", "0", "true", "false"):
        raise ValueError(f"beklenmeyen ikili değer: {metin!r}")
    return m in ("1", "true")


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("tahminler", help="deney/guven_egitimi.py çıktısı tahminler.csv")
    ayr.add_argument("--cikti", default=str(VARSAYILAN_CIKTI))
    ayr.add_argument("--bolunme", default=str(VARSAYILAN_YOL), help="Geliştirme/test bölünmesi (data/bolunme.yaml)")
    ayr.add_argument("--baslik", default="Güven skoru: risk–kapsam")
    args = ayr.parse_args(argv)

    cikti = Path(args.cikti)
    if _gold_altinda_mi(cikti):
        print(f"risk_kapsam: çıktı data/gold altına yazılamaz: {cikti}", file=sys.stderr)
        return 2
    try:
        with open(args.tahminler, encoding="utf-8", newline="") as f:
            satirlar = list(csv.DictReader(f))
        b = bolunme_oku(args.bolunme)
        for etiket in sorted({s["belge"] for s in satirlar}):
            b.kullanima_izin_ver(etiket)  # test kümesi ve taranmış (OcrGerekli) belge reddedilir
        guvenler = [float(s["guven"]) for s in satirlar]
        hatalilar = [_ikili(s["hatali"]) for s in satirlar]
        zorunlular = [_ikili(s["zorunlu_inceleme"]) for s in satirlar]
    except (OSError, KeyError, TestKumesiKilitli, ValueError) as hata:
        print(f"risk_kapsam: {hata}", file=sys.stderr)
        return 2

    noktalar = egri(guvenler, hatalilar, zorunlular)
    cikti.mkdir(parents=True, exist_ok=True)
    with open(cikti / "risk_kapsam.csv", "w", encoding="utf-8", newline="") as f:
        yazici = csv.writer(f)
        yazici.writerow(SUTUNLAR)
        for n in noktalar:
            yazici.writerow([repr(n.esik), repr(n.kapsam), repr(n.risk), n.otomatik, n.hatali_otomatik])
    (cikti / "risk_kapsam.svg").write_text(svg_ciz(noktalar, args.baslik), encoding="utf-8")
    print(f"AURC {aurc(noktalar):.6f} ({len(satirlar)} test) -> {cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
