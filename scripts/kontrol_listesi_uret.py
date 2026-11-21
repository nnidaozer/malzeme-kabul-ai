#!/usr/bin/env python3
"""Doğru cevap taslağından elle işaretlenecek kontrol listesi (Markdown) üretir.

Her satır: boş kutu, ad, değer, birim, madde, PDF sayfası. Proje sahibi
değerleri PDF'le karşılaştırıp kutuyu [x] yapar.

Kullanım:
  python scripts/kontrol_listesi_uret.py data/gold_taslak/MIL-PRF-23377K.json
  (çıktı: aynı klasörde <ad>_kontrol_listesi.md)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from malzeme_kabul.dokuman_uretici import _sayi
from malzeme_kabul.sema import KabulDokumani, Kaynak, Sinir

SUTUNLAR = ["✓", "Ad", "Değer", "Birim", "Madde", "PDF sayfası"]
TEST_SUTUNLARI = SUTUNLAR + ["Kriter türü", "Test türü"]
KRITER_ADI = {"sayisal": "sayısal", "gecti_kaldi": "geçti/kaldı", "metinsel": "metinsel"}


def _hucre(metin: str) -> str:
    return metin.replace("|", "\\|").replace("\n", " ")


def _deger(sinir: Sinir) -> tuple[str, str]:
    """(değer, birim) metni."""
    if sinir.kriter_turu != "sayisal":
        return sinir.orijinal_metin, ""
    alt, ust = sinir.alt, sinir.ust
    if alt is not None and ust is not None:
        deger = f"= {_sayi(alt)}" if alt == ust else f"{_sayi(alt)} – {_sayi(ust)}"
    elif alt is not None:
        deger = f"{'≥' if sinir.alt_dahil else '>'} {_sayi(alt)}"
    else:
        deger = f"{'≤' if sinir.ust_dahil else '<'} {_sayi(ust)}"
    return deger, sinir.birim or ""


def _satir(ad: str, deger: str, birim: str, kaynak: Kaynak, *ek: str) -> str:
    hucreler = ["[ ]", ad, deger, birim, kaynak.madde, str(kaynak.sayfa or "?"), *ek]
    return "| " + " | ".join(_hucre(h) for h in hucreler) + " |"


def _tablo(sutunlar: list[str], satirlar: list[str]) -> list[str]:
    return ["| " + " | ".join(sutunlar) + " |", "|" + "---|" * len(sutunlar), *satirlar]


def kontrol_listesi(dok: KabulDokumani) -> str:
    """Kontrol listesini Markdown metni olarak döner."""
    belge = f"{dok.standart.belge_no}{dok.standart.revizyon}"
    parcalar = [
        f"# {belge} doğru cevap taslağı: kontrol listesi",
        "",
        "Her satırdaki değeri PDF'teki maddeyle karşılaştır; doğruysa `[ ]` kutusunu `[x]` yap, "
        f"yanlışsa satırın yanına doğrusunu yaz. Değerler `{belge}.json` dosyasından üretildi; "
        "PDF sayfası, PDF görüntüleyicideki sayfa numarasıdır.",
        "",
        f"## Testler ({len(dok.testler)})",
        "",
    ]
    satirlar = []
    for t in dok.testler:
        deger, birim = _deger(t.sinir)
        ek = [KRITER_ADI[t.sinir.kriter_turu], ", ".join(sorted(t.test_turleri))]
        satirlar.append(_satir(t.test_adi, deger, birim, t.kaynak, *ek))
    parcalar += _tablo(TEST_SUTUNLARI, satirlar)

    if dok.raf_omurleri:
        satirlar = []
        for r in dok.raf_omurleri:
            satirlar.append(_satir(f"Raf ömrü ({r.kap_turu or 'tümü'})", _sayi(r.sure), r.birim, r.kaynak))
            if r.kosul:
                deger, birim = _deger(r.kosul)
                satirlar.append(_satir(f"Raf ömrü ({r.kap_turu or 'tümü'}): depolama koşulu", deger, birim, r.kaynak))
        parcalar += ["", "## Raf ömrü", "", *_tablo(SUTUNLAR, satirlar)]

    if dok.kosullar:
        satirlar = []
        for k in dok.kosullar:
            deger, birim = _deger(k.sinir) if k.sinir else (k.aciklama or "", "")
            satirlar.append(_satir(k.ad, deger, birim, k.kaynak))
        parcalar += ["", "## Depolama ve kullanım koşulları", "", *_tablo(SUTUNLAR, satirlar)]

    if dok.numune_hazirlama:
        satirlar = []
        for n in dok.numune_hazirlama:
            satirlar.append(_satir(f"{n.id}: kupon", n.kupon_malzemesi or "", "", n.kaynak))
            satirlar.append(_satir(f"{n.id}: yüzey hazırlığı", n.yuzey_hazirligi or "", "", n.kaynak))
            if n.kuru_film_kalinligi:
                deger, birim = _deger(n.kuru_film_kalinligi)
                satirlar.append(_satir(f"{n.id}: kuru film kalınlığı", deger, birim, n.kaynak))
        parcalar += ["", "## Test panelleri (kupon, uygulama, kürlenme)", "", *_tablo(SUTUNLAR, satirlar)]

    baglantilar = [t for t in dok.testler if t.numune_hazirlama_id]
    if baglantilar:
        satirlar = [_satir(f"{t.test_adi} → panel", t.numune_hazirlama_id, "", t.metot_kaynagi or t.kaynak)
                    for t in baglantilar]
        parcalar += ["", "## Test–panel bağlantıları", "", *_tablo(SUTUNLAR, satirlar)]
    return "\n".join(parcalar) + "\n"


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("gold_taslak")
    ayr.add_argument("--cikti")
    args = ayr.parse_args(argv)
    yol = Path(args.gold_taslak)
    dok = KabulDokumani.model_validate_json(yol.read_text(encoding="utf-8"))
    cikti = Path(args.cikti) if args.cikti else yol.with_name(f"{yol.stem}_kontrol_listesi.md")
    cikti.write_text(kontrol_listesi(dok), encoding="utf-8")
    print(f"Kontrol listesi yazıldı: {cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
