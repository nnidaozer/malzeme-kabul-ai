#!/usr/bin/env python3
"""Karar motorunu sentetik sertifikalarda çalıştırıp yakalama ve yanlış kabul oranını ölçer.

Girdi: kabul dokümanı (JSON) ve sertifika klasörü (json/ ve dogru_kararlar.json).
Çıktı: <cikti>.md (rapor) ve <cikti>.csv (sertifika başına karar).

Ölçüm sertifikanın ham hücrelerini (json/) kullanır; yani belge okuma
kusursuz varsayılır ve yalnız karar motoru ölçülür.

Kullanım:
  python scripts/karar_olc.py data/cikti/MIL-PRF-23377K_kabul_dokumani.json \
      data/sentetik/sertifikalar/MIL-PRF-23377K --cikti data/cikti/MIL-PRF-23377K_karar_olcumu
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path

from malzeme_kabul.karar_motoru import KararAyarlari, KontrolSonucu, eslestir, kontrol_et
from malzeme_kabul.karar_olcumu import DogruKarar, Olcum, Oranlar, olc
from malzeme_kabul.sema import KabulDokumani
from malzeme_kabul.sertifika import Sertifika

KOK = Path(__file__).resolve().parents[1]


def _yuzde(x: float | None) -> str:
    return "-" if x is None else f"%{100 * x:.1f}"


def _oran_tablosu(baslik: str, o: Oranlar, etiketler: tuple[str, ...]) -> list[str]:
    satirlar = [
        f"### {baslik} ({o.adet})",
        "",
        "| Ölçüt | Değer |",
        "|---|---|",
        f"| Yanlış kabul oranı | {_yuzde(o.yanlis_kabul_orani)} |",
        f"| Yakalama oranı (red olması gerekenlerde red) | {_yuzde(o.yakalama_orani)} |",
        f"| Doğruluk | {_yuzde(o.dogruluk)} |",
        f"| Otomasyon oranı (insana gitmeyen) | {_yuzde(o.otomasyon_orani)} |",
        "",
        "Karışıklık matrisi (satır: doğru karar, sütun: motor):",
        "",
        "| doğru \\ motor | " + " | ".join(etiketler) + " |",
        "|---|" + "---|" * len(etiketler),
    ]
    for d in etiketler:
        satirlar.append(f"| {d} | " + " | ".join(str(o.karisiklik[d][t]) for t in etiketler) + " |")
    return satirlar + [""]


def rapor(
    dokuman: KabulDokumani,
    olcum: Olcum,
    dogrular: list[DogruKarar],
    tahminler: list[KontrolSonucu],
    sureler: list[float],
    ad_kapsami: tuple[int, int, list[str]] | None,
) -> str:
    std = dokuman.standart
    tahmin = {t.sertifika_no: t for t in tahminler}
    s = [
        f"# Karar motoru ölçümü: {std.belge_no}{std.revizyon}",
        "",
        f"{len(dogrular)} sentetik sertifika; belge okuma kusursuz varsayıldı (ham hücreler JSON'dan).",
        "Yanlış kabul yalnız motor \"kabul\" (satırda \"uygun\") dediğinde oluşur; \"inceleme\" kabul sayılmaz.",
        "",
        f"Belge başına süre: ortalama {1000 * sum(sureler) / len(sureler):.2f} ms, en çok {1000 * max(sureler):.2f} ms.",
        "",
    ]
    s += _oran_tablosu("Belge düzeyi", olcum.belge, ("kabul", "red", "inceleme"))
    s += _oran_tablosu("Test satırı düzeyi", olcum.satir, ("uygun", "uygun_degil", "insan_incelemeli"))
    s += ["### Hata türüne göre", "", "| Hata türü | Adet | Doğru karar | Yanlış kabul |", "|---|---|---|---|"]
    for tur, skor in olcum.hata_turune_gore.items():
        s.append(f"| {tur} | {skor.adet} | {skor.dogru} | {skor.yanlis_kabul} |")
    s.append("")

    farkli = [d for d in dogrular if d.belge_karari != tahmin[d.sertifika_no].belge_karari]
    s += ["### Doğru karardan ayrılan sertifikalar", ""]
    if not farkli:
        s.append("Yok.")
    for d in farkli:
        t = tahmin[d.sertifika_no]
        s.append(f"- {d.sertifika_no} ({d.hata_turu or 'temiz'}: {d.hata_aciklamasi or '-'}): doğru {d.belge_karari}, motor {t.belge_karari}")
        for satir in t.satirlar:
            if satir.karar != d.satirlar.get(satir.test_id):
                s.append(f"  - {satir.test_id}: {satir.karar} ({satir.gerekce})")
    s.append("")

    if ad_kapsami:
        eslesen, toplam, kacan = ad_kapsami
        s += [
            "### Ek: test adı varyantlarının kapsamı",
            "",
            f"Üreticideki {toplam} ad varyantının {eslesen} tanesi doğru teste eşleşiyor. "
            "Eşleşmeyenler insana gider (yanlış kabul oluşturmaz):",
            "",
        ]
        s += [f"- {k}" for k in kacan] + [""]
    s += [
        "### Sınırlar",
        "",
        "- Sertifikalar ve karar motoru aynı ekip tarafından, aynı kabul dokümanından yazıldı; bu sonuç",
        "  motorun kendi tasarım alanındaki üst sınırıdır. Gerçek CoC/TR'lerde oranlar düşebilir.",
        "- Belge okuma ölçülmedi: motor ham hücreleri JSON'dan aldı. PDF'ten okuma (kural ya da yerel",
        "  dil modeli) eklendiğinde okuma hataları da yanlış kabule yol açabilir.",
        "- Kabul dokümanı çıkarıcının onaylanmamış taslağıdır; standarttan eksik çıkarılan bir şart",
        "  (ör. kurşun sınırı) sertifikada da aranmaz.",
        "",
    ]
    return "\n".join(s)


def ad_varyant_kapsami(dokuman: KabulDokumani) -> tuple[int, int, list[str]]:
    from malzeme_kabul.sertifika_uretici import AD_VARYANTLARI

    eslesen, kacan = 0, []
    for test_id, adlar in AD_VARYANTLARI.items():
        test = next(t for t in dokuman.kabul_testleri if t.id == test_id)
        # Aynı tip/sınıftaki testler arasında eşleştir (renk gibi tipe bağlı testler çakışmasın).
        adaylar = [t for t in dokuman.kabul_testleri if not t.uygulanabilirlik or t.uygulanabilirlik == test.uygulanabilirlik]
        for ad in adlar:
            if eslestir(ad, adaylar) == test_id:
                eslesen += 1
            else:
                kacan.append(f"{ad!r} ({test_id})")
    return eslesen, eslesen + len(kacan), kacan


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("kabul_dokumani")
    ayr.add_argument("sertifika_klasoru")
    ayr.add_argument("--cikti", default=str(KOK / "data" / "cikti" / "MIL-PRF-23377K_karar_olcumu"))
    ayr.add_argument("--eksik-test", default="insan_incelemeli", choices=["insan_incelemeli", "uygun_degil"])
    ayr.add_argument("--yanlis-revizyon", default="insan_incelemeli", choices=["insan_incelemeli", "uygun_degil"])
    args = ayr.parse_args(argv)

    cikti = Path(args.cikti)
    if re.search(r"(^|/)data/gold(/|$)", cikti.resolve().as_posix()):
        raise SystemExit("data/gold/ klasörüne yazılmaz")
    dokuman = KabulDokumani.model_validate_json(Path(args.kabul_dokumani).read_text(encoding="utf-8"))
    klasor = Path(args.sertifika_klasoru)
    dogrular = [DogruKarar(**d) for d in json.loads((klasor / "dogru_kararlar.json").read_text(encoding="utf-8"))]
    ayar = KararAyarlari(eksik_test=args.eksik_test, yanlis_revizyon=args.yanlis_revizyon)

    tahminler, sureler = [], []
    for d in dogrular:
        sertifika = Sertifika.model_validate_json((klasor / "json" / f"{d.sertifika_no}.json").read_text(encoding="utf-8"))
        bas = time.perf_counter()
        tahminler.append(kontrol_et(dokuman, sertifika, ayar))
        sureler.append(time.perf_counter() - bas)

    olcum = olc(tahminler, dogrular)
    try:
        kapsam = ad_varyant_kapsami(dokuman)
    except StopIteration:
        kapsam = None
    cikti.parent.mkdir(parents=True, exist_ok=True)
    cikti.with_suffix(".md").write_text(rapor(dokuman, olcum, dogrular, tahminler, sureler, kapsam), encoding="utf-8")
    with open(cikti.with_suffix(".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sertifika_no", "hata_turu", "dogru_belge_karari", "motor_belge_karari", "insana_giden_satirlar", "red_satirlari"])
        tahmin = {t.sertifika_no: t for t in tahminler}
        for d in dogrular:
            t = tahmin[d.sertifika_no]
            satirlar = [t.revizyon, *t.satirlar]
            w.writerow(
                [
                    d.sertifika_no, d.hata_turu or "temiz", d.belge_karari, t.belge_karari,
                    ";".join(s.test_id for s in satirlar if s.karar == "insan_incelemeli"),
                    ";".join(s.test_id for s in satirlar if s.karar == "uygun_degil"),
                ]
            )
    b = olcum.belge
    print(
        f"yanlış kabul {_yuzde(b.yanlis_kabul_orani)}, yakalama {_yuzde(b.yakalama_orani)}, "
        f"doğruluk {_yuzde(b.dogruluk)}, otomasyon {_yuzde(b.otomasyon_orani)} -> {cikti.with_suffix('.md')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
