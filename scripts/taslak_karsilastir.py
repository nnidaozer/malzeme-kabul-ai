#!/usr/bin/env python3
"""İki bağımsız doğru cevap taslağını karşılaştırıp kontrol raporu yazar.

Kullanım:
  python scripts/taslak_karsilastir.py A.json B.json [--md rapor.md] [--csv rapor.csv]
                                       [--oran 0.2] [--seed 20261209]

A ve B, KabulDokumani JSON'udur (ör. A: data/gold_taslak altındaki taslak,
B: bağımsız modelin taslağı). Rapor ayrışan satırları, yalnız bir taslakta olan
satırları, ad benzerliğiyle eşleşen kayıtları ve uyuşan satırlardan seçilen
kontrol örneğini `[ ]` kutularıyla listeler. Aynı girdi ve seed hep aynı örneği
verir. data/gold/ altına yazmaz.

Çıkış kodu: 0 başarılı, 2 geçersiz girdi ya da yasak çıktı yolu.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from malzeme_kabul.sema import KabulDokumani
from malzeme_kabul.taslak_karsilastirma import (
    VARSAYILAN_ORAN, VARSAYILAN_SEED, Karsilastirma, Satir, karsilastir,
)

SUTUNLAR = ["durum", "alan", "kayit_a", "kayit_b", "deger_a", "deger_b", "madde", "eslesme", "kontrol_ornegi"]


def _oku(yol: str) -> KabulDokumani:
    return KabulDokumani.model_validate_json(Path(yol).read_text(encoding="utf-8"))


def _gold_altinda_mi(yol: str) -> bool:
    parcalar = [p.casefold() for p in Path(yol).resolve().parts]
    return any(a == "data" and b == "gold" for a, b in zip(parcalar, parcalar[1:]))


def _goster(deger: Any) -> str:
    if deger is None:
        return "—"
    if isinstance(deger, tuple):
        return ", ".join(str(d) for d in deger)
    if isinstance(deger, float) and deger.is_integer():
        return str(int(deger))
    return str(deger)


def _hucre(deger: Any) -> str:
    return _goster(deger).replace("|", "\\|").replace("\n", " ")


def _madde(s: Satir) -> str:
    return f" (madde {s.madde})" if s.madde else ""


def rapor_md(k: Karsilastirma, ad_a: str, ad_b: str, oran: float, seed: int) -> str:
    ornek = k.kontrol_ornegi(oran=oran, seed=seed)
    y = [
        "# Bağımsız taslak karşılaştırması",
        "",
        f"- A: `{ad_a}`",
        f"- B: `{ad_b}`",
        f"- Satır: {len(k.satirlar)} (uyuşan {len(k.uyusan)}, ayrışan {len(k.ayrisan)}, "
        f"yalnız A {len(k.yalniz_a)}, yalnız B {len(k.yalniz_b)})",
        f"- **Uyuşma oranı: {k.uyusma_orani:.1%}** (uyuşan / bütün satırlar)",
        f"- Kontrol örneği: uyuşan satırların %{oran * 100:g}'i, {len(ornek)} satır, seed {seed}",
        "",
        "Kontrol edilecekler: ayrışan satırlar, yalnız bir taslakta olan satırlar,",
        "ad benzerliğiyle eşleşen kayıtlar ve kontrol örneği. Doğruysa `[ ]` kutusunu `[x]` yap,",
        "yanlışsa doğrusunu yanına yaz.",
        "",
        "## Ad benzerliğiyle eşleşen kayıtlar",
        "",
        "İki taslak bu kayıtlara farklı ad verdi; aynı şart oldukları varsayıldı. Yanlış eşleşmeyse",
        "o kaydın satırları anlamsızdır.",
        "",
    ]
    if k.benzerlik_eslesmeleri:
        for e in k.benzerlik_eslesmeleri:
            madde = f", madde {e.madde}" if e.madde else ""
            y.append(f"- [ ] {e.tur}: A `{e.a}` ≈ B `{e.b}` (benzerlik {e.benzerlik:.2f}{madde})")
    else:
        y.append("Yok.")

    def liste(baslik: str, satirlar: list[Satir], bicim) -> None:
        y.extend(["", f"## {baslik} ({len(satirlar)})", ""])
        if satirlar:
            y.extend(bicim(s) for s in satirlar)
        else:
            y.append("Yok.")

    def iki_deger(s: Satir) -> str:
        isaret = " · ad benzerliğiyle eşleşti" if s.eslesme == "benzerlik" else ""
        return f"- [ ] `{s.kayit}` · `{s.alan}`{_madde(s)}: A = {_goster(s.a)} · B = {_goster(s.b)}{isaret}"

    liste("Ayrışan satırlar", k.ayrisan, iki_deger)
    liste("Yalnız A'da olan satırlar", k.yalniz_a,
          lambda s: f"- [ ] `{s.kayit}` · `{s.alan}`{_madde(s)}: {_goster(s.a)}")
    liste("Yalnız B'de olan satırlar", k.yalniz_b,
          lambda s: f"- [ ] `{s.kayit}` · `{s.alan}`{_madde(s)}: {_goster(s.b)}")
    liste("Kontrol örneği (uyuşan satırlardan)", ornek, iki_deger)

    y.extend(["", "## Alan türüne göre uyuşma", "",
              "| Alan | Uyuşan | Ayrışan | Yalnız A | Yalnız B | Oran |", "|---|---|---|---|---|---|"])
    for d in k.alan_dokumu():
        y.append(f"| `{d['alan']}` | {d['uyusan']} | {d['ayrisan']} | {d['yalniz_a']} | {d['yalniz_b']} | {d['oran']:.0%} |")
    return "\n".join(y) + "\n"


def csv_yaz(k: Karsilastirma, yol: Path, oran: float, seed: int) -> None:
    ornek = {id(s) for s in k.kontrol_ornegi(oran=oran, seed=seed)}
    with open(yol, "w", encoding="utf-8", newline="") as f:
        yazici = csv.DictWriter(f, fieldnames=SUTUNLAR)
        yazici.writeheader()
        for s in k.satirlar:
            yazici.writerow({
                "durum": s.durum, "alan": s.alan, "kayit_a": s.kayit_a or "", "kayit_b": s.kayit_b or "",
                "deger_a": "" if s.a is None else _goster(s.a), "deger_b": "" if s.b is None else _goster(s.b),
                "madde": s.madde or "", "eslesme": s.eslesme or "",
                "kontrol_ornegi": "evet" if id(s) in ornek else "",
            })


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("a", help="Birinci taslak (KabulDokumani JSON)")
    ayr.add_argument("b", help="İkinci, bağımsız taslak (KabulDokumani JSON)")
    ayr.add_argument("--md", help="Markdown raporun yazılacağı yol")
    ayr.add_argument("--csv", help="Bütün satırların yazılacağı CSV yolu")
    ayr.add_argument("--oran", type=float, default=VARSAYILAN_ORAN, help="Kontrol örneği oranı (0-1)")
    ayr.add_argument("--seed", type=int, default=VARSAYILAN_SEED, help="Kontrol örneği için seed")
    args = ayr.parse_args(argv)

    for yol in (args.md, args.csv):
        if yol and _gold_altinda_mi(yol):
            print(f"data/gold/ altına yazılmaz: {yol}", file=sys.stderr)
            return 2
    if not 0.0 <= args.oran <= 1.0:
        print(f"--oran 0 ile 1 arasında olmalı: {args.oran}", file=sys.stderr)
        return 2
    try:
        a, b = _oku(args.a), _oku(args.b)
    except (ValidationError, ValueError, OSError) as hata:
        print(f"geçersiz girdi: {hata}", file=sys.stderr)
        return 2

    k = karsilastir(a, b)
    print(
        f"Satır: {len(k.satirlar)}  uyuşan: {len(k.uyusan)}  ayrışan: {len(k.ayrisan)}  "
        f"yalnız A: {len(k.yalniz_a)}  yalnız B: {len(k.yalniz_b)}  "
        f"benzerlikle eşleşen kayıt: {len(k.benzerlik_eslesmeleri)}"
    )
    print(f"Uyuşma oranı: {k.uyusma_orani:.1%}")
    print(f"Kontrol örneği: {len(k.kontrol_ornegi(args.oran, args.seed))} satır (seed {args.seed})")

    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(rapor_md(k, args.a, args.b, args.oran, args.seed), encoding="utf-8")
    if args.csv:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        csv_yaz(k, Path(args.csv), args.oran, args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
