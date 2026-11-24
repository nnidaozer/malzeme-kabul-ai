#!/usr/bin/env python3
"""Doğru cevap dosyasındaki her sayısal değerin PDF'in ilgili sayfasında geçtiğini kontrol eder.

Kullanım:
  python deney/kanit_kontrol.py CEVAP.json STANDART.pdf [--md rapor.md] [--csv rapor.csv]

CEVAP.json bir KabulDokumani'dır (ör. data/gold_taslak/MIL-PRF-23377K.json ya da
data/gold_codex/MIL-PRF-23377K.json). Her değer, kaydın kaynak sayfasında (yoksa
madde numarasının geçtiği sayfada) aranır. Bulunamayanlar, ± toleransından
hesaplananlar, yalnız sonraki sayfada geçenler ve sayfası olmayanlar listelenir.
data/gold/ altına yazmaz.

Çıkış kodu: 0 her değer bulundu ya da hesaplandı, 1 bulunamayan ya da
sayfası olmayan değer var, 2 geçersiz girdi ya da yasak çıktı yolu.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

# `python deney/<betik>.py` ile doğrudan çalışınca depo kökü yolda olsun (deney paketi için).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deney.bolunme import VARSAYILAN_YOL, betik_korumasi
from deney.kanit_kontrolu import KanitSonucu, kanit_kontrol
from malzeme_kabul.belge.pdf_okuyucu import pdf_oku
from malzeme_kabul.sozlesme.sema import KabulDokumani

SUTUNLAR = ["durum", "kayit", "alan", "deger", "madde", "sayfa", "madde_sayfada"]
BOLUMLER = [
    ("bulunamadi", "Bulunamayan değerler", "Değer, kaydın sayfasında ve sonraki sayfada geçmiyor."),
    ("sayfa_yok", "Sayfası olmayan değerler", "Sayfa PDF'te yok ya da madde numarası hiçbir sayfada bulunamadı."),
    ("sonraki_sayfada", "Yalnız sonraki sayfada geçen değerler",
     "Madde sayfa sonunda devam ediyor olabilir ya da sayfa numarası yanlış."),
    ("turetildi", "± toleransından hesaplanan değerler", "Sayfada X ± Y olarak geçiyor; hesabı kontrol et."),
]
ETIKET = {"bulundu": "bulundu", "turetildi": "± ile hesaplandı", "sonraki_sayfada": "sonraki sayfada",
          "bulunamadi": "bulunamadı", "sayfa_yok": "sayfa yok"}


def _gold_altinda_mi(yol: str) -> bool:
    parcalar = [p.casefold() for p in Path(yol).resolve().parts]
    return any(a == "data" and b == "gold" for a, b in zip(parcalar, parcalar[1:]))


def _sayi(deger: float) -> str:
    return str(int(deger)) if float(deger).is_integer() else f"{deger:g}"


def rapor_md(sonuclar: list[KanitSonucu], cevap: str, pdf: str) -> str:
    say = Counter(s.durum for s in sonuclar)
    y = [
        "# Kanıt kontrolü",
        "",
        f"- Cevap dosyası: `{cevap}`",
        f"- PDF: `{pdf}`",
        f"- Sayısal değer: {len(sonuclar)} · " + " · ".join(f"{ETIKET[d]}: {say.get(d, 0)}" for d in ETIKET),
        "",
        "Kontrol yalnızca sayının sayfada geçip geçmediğine bakar; birimi ve cümleyi denetlemez.",
    ]
    for durum, baslik, aciklama in BOLUMLER:
        secili = [s for s in sonuclar if s.durum == durum]
        y.extend(["", f"## {baslik} ({len(secili)})", "", aciklama, ""])
        if not secili:
            y.append("Yok.")
        for s in secili:
            sayfa = f"sayfa {s.sayfa}" if s.sayfa else "sayfa yok"
            uyari = " · madde numarası bu sayfada yok" if s.madde_sayfada is False else ""
            y.append(f"- [ ] `{s.kayit}` · `{s.alan}` = {_sayi(s.deger)} (madde {s.madde}, {sayfa}){uyari}")
    return "\n".join(y) + "\n"


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("cevap", help="Doğru cevap dosyası (KabulDokumani JSON)")
    ayr.add_argument("pdf", help="Standardın PDF'i")
    ayr.add_argument("--md", help="Markdown raporun yazılacağı yol")
    ayr.add_argument("--csv", help="Bütün değerlerin yazılacağı CSV yolu")
    ayr.add_argument("--bolunme", default=str(VARSAYILAN_YOL), help="Geliştirme/test bölünmesi (data/bolunme.yaml)")
    args = ayr.parse_args(argv)

    for yol in (args.md, args.csv):
        if yol and _gold_altinda_mi(yol):
            print(f"data/gold/ altına yazılmaz: {yol}", file=sys.stderr)
            return 2
    try:
        dokuman = KabulDokumani.model_validate_json(Path(args.cevap).read_text(encoding="utf-8"))
    except (ValidationError, ValueError, OSError) as hata:
        print(f"geçersiz girdi: {hata}", file=sys.stderr)
        return 2
    std = dokuman.standart
    if (kod := betik_korumasi(f"{std.belge_no}{std.revizyon}", args.bolunme, "kanit_kontrol")) is not None:
        return kod
    try:
        belge = pdf_oku(args.pdf)
    except (ValueError, OSError) as hata:
        print(f"geçersiz girdi: {hata}", file=sys.stderr)
        return 2

    sonuclar = kanit_kontrol(dokuman, belge)
    say = Counter(s.durum for s in sonuclar)
    print(f"Sayısal değer: {len(sonuclar)}  " + "  ".join(f"{ETIKET[d]}: {say.get(d, 0)}" for d in ETIKET))
    for s in sonuclar:
        if s.durum in ("bulunamadi", "sayfa_yok"):
            print(f"  {ETIKET[s.durum]}: {s.kayit} {s.alan} = {_sayi(s.deger)} (madde {s.madde}, sayfa {s.sayfa})")

    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(rapor_md(sonuclar, args.cevap, args.pdf), encoding="utf-8")
    if args.csv:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            yazici = csv.DictWriter(f, fieldnames=SUTUNLAR)
            yazici.writeheader()
            for s in sonuclar:
                yazici.writerow({
                    "durum": s.durum, "kayit": s.kayit, "alan": s.alan, "deger": _sayi(s.deger),
                    "madde": s.madde, "sayfa": s.sayfa or "",
                    "madde_sayfada": "" if s.madde_sayfada is None else ("evet" if s.madde_sayfada else "hayır"),
                })
    return 1 if say.get("bulunamadi") or say.get("sayfa_yok") else 0


if __name__ == "__main__":
    sys.exit(main())
