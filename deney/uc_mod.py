#!/usr/bin/env python3
"""Bir standart PDF'ini üç modda çıkarır: yalnız kural, yalnız dil modeli ve hibrit.

Dil modeli yerel bir Ollama ya da llama.cpp sunucusunda çalışır; betik yalnız
localhost'a bağlanır. Hibrit tanımı `deney/hibrit_standart.py` içindedir.
Çıktılar (CIKTI altında, ETIKET = belge no + revizyon, ör. MIL-PRF-23377K):
  ETIKET_kural.json, ETIKET_dil_modeli.json, ETIKET_hibrit.json  KabulDokumani
  ETIKET_uc_mod_rapor.json   model, süreler, test sayıları, alt raporlar, anlaşmazlıklar
  ETIKET_uc_mod_olcum.csv    gold verilirse her mod x her gold için hizalı alan F1'leri
  ETIKET_ara/                dil modelinin sayfa başına ara kaydı (kopan çalışma buradan devam eder)

Kullanım:
  python deney/uc_mod.py data/raw/MIL-PRF-23377K.pdf --model qwen3:8b --dusunme-kapali

Varsayılan gold'lar data/gold_taslak/ETIKET.json ve data/gold_codex/ETIKET.json
(varsa); yalnız okunur. data/gold/ altına çıktı yazılmaz. Yalnız data/bolunme.yaml'daki
geliştirme kümesi çalıştırılır; kilitli ya da geçersiz durumda betik 2 koduyla çıkar.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

# `python deney/<betik>.py` ile doğrudan çalışınca depo kökü yolda olsun (deney paketi için).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from malzeme_kabul.belge.adlandirma import belge_no_ve_revizyon
from malzeme_kabul.belge.pdf_okuyucu import pdf_oku
from malzeme_kabul.cikarim import kural_cikarici
from malzeme_kabul.cikarim.yerel_model import ARKA_UCLAR, SohbetIstemcisi, YerelModelIstemcisi
from malzeme_kabul.sozlesme.sema import KabulDokumani

from deney.bolunme import VARSAYILAN_YOL, TestKumesiKilitli, bolunme_oku
from deney.degerlendirme import degerlendir
from deney.hibrit_standart import hibrit_birlestir
from deney.taslak_karsilastirma import _b_yi_a_adlariyla_yaz, kaydi_eslestir
from deney.yalniz_dil_modeli import ara_kayit_parmak_izi, belgeden_cikar

KOK = Path(__file__).resolve().parents[1]
GOLD = KOK / "data" / "gold"
VARSAYILAN_CIKTI = KOK / "deney" / "sonuclar" / "colab_uc_mod"
MODLAR = ("kural", "dil_modeli", "hibrit")
OLCUM_SUTUNLARI = ["gold", "mod", "alan", "dp", "yp", "yn", "precision", "recall", "f1"]


def _gold_altinda_mi(yol: Path) -> bool:
    gercek = Path(yol).resolve()
    if gercek == GOLD.resolve() or GOLD.resolve() in gercek.parents:
        return True
    parcalar = [p.casefold() for p in gercek.parts]
    return any(a == "data" and b == "gold" for a, b in zip(parcalar, parcalar[1:]))


def varsayilan_goldlar(etiket: str, kok: Path = KOK) -> dict[str, Path]:
    """gold_taslak/ETIKET.json ve gold_codex/ETIKET.json (data altında); yalnız var olanlar."""
    adaylar = {ad: Path(kok) / "data" / ad / f"{etiket}.json" for ad in ("gold_taslak", "gold_codex")}
    return {ad: yol for ad, yol in adaylar.items() if yol.is_file()}


def _goldlari_oku(goldlar: dict[str, Path]) -> dict[str, KabulDokumani]:
    """Gold dosyalarını (yalnız okuyarak) doğrular; okunamaz ya da şemaya uymazsa ValueError."""
    sonuc = {}
    for ad, yol in goldlar.items():
        try:
            sonuc[ad] = KabulDokumani.model_validate_json(Path(yol).read_text(encoding="utf-8"))
        except (OSError, ValueError) as hata:  # pydantic ValidationError da ValueError'dır
            raise ValueError(f"gold geçersiz ({ad}: {yol}): {hata}") from hata
    return sonuc


def _insan_incelemeli(d: KabulDokumani) -> int:
    """Yönü 'belirsiz' olan sayısal test sınırı sayısı (karar motoru insan incelemesine gönderir)."""
    return sum(1 for t in d.testler if t.sinir.kriter_turu == "sayisal" and t.sinir.yon == "belirsiz")


def _json_yaz(yol: Path, veri: Any) -> None:
    yol.write_text(json.dumps(veri, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def uc_mod_calistir(
    pdf_yolu: str | Path,
    istemci: SohbetIstemcisi,
    cikti: str | Path,
    model_adi: str,
    goldlar: dict[str, Path] | None = None,
    belge_no: str | None = None,
    revizyon: str | None = None,
    bolunme: str | Path = VARSAYILAN_YOL,
) -> dict[str, Any]:
    """Üç modu çalıştırır, çıktıları `cikti` altına yazar ve raporu döner (modül açıklaması).

    Test kümesindeki belge için `TestKumesiKilitli`, data/gold altındaki çıktı
    klasörü ya da okunamayan / şemaya uymayan gold için `ValueError` yükselir; bu
    denetimler model çağrılmadan ve hiçbir şey yazılmadan yapılır. Dil modeli
    süresi sayfa sürelerinin toplamıdır (devam edilen sayfalar ara kayıttaki süreyle).
    """
    cikti = Path(cikti)
    if _gold_altinda_mi(cikti):
        raise ValueError(f"çıktı data/gold altına yazılamaz: {cikti}")
    if belge_no is None or revizyon is None:
        belge_no, revizyon = belge_no_ve_revizyon(Path(pdf_yolu).name)
    etiket = f"{belge_no}{revizyon}"
    b = bolunme_oku(bolunme)
    b.kullanima_izin_ver(etiket)
    b.yol_kullanima_izin_ver(pdf_yolu)
    gold_dokumanlari = _goldlari_oku(goldlar or {})

    t0 = time.perf_counter()
    kural = kural_cikarici.cikar(pdf_yolu, belge_no, revizyon)
    kural_sure = round(time.perf_counter() - t0, 3)

    belge = pdf_oku(pdf_yolu)
    cikti.mkdir(parents=True, exist_ok=True)
    dil, dil_rapor = belgeden_cikar(belge, belge_no, revizyon, istemci, ara_kayit=cikti / f"{etiket}_ara",
                                    parmak_izi=ara_kayit_parmak_izi(istemci))
    # Kopan çalışmada devam edilen sayfaların süresi ara kayıttan gelir; duvar saati değil toplam kullanılır.
    dil_sure = round(sum(s.sure_s for s in dil_rapor.sayfalar), 3)

    t0 = time.perf_counter()
    hibrit, hibrit_rapor = hibrit_birlestir(kural, dil, belge)
    hibrit_sure = round(kural_sure + dil_sure + (time.perf_counter() - t0), 3)

    dokumanlar = {"kural": kural, "dil_modeli": dil, "hibrit": hibrit}
    sureler = {"kural": kural_sure, "dil_modeli": dil_sure, "hibrit": hibrit_sure}
    for mod, d in dokumanlar.items():
        (cikti / f"{etiket}_{mod}.json").write_text(d.model_dump_json(indent=2) + "\n", encoding="utf-8")

    rapor: dict[str, Any] = {
        "model": model_adi,
        "belge": etiket,
        "sayfa_sayisi": len(belge.sayfalar),
        "modlar": {
            mod: {"test_sayisi": len(d.testler), "sure_s": sureler[mod], "insan_incelemeli_sinir": _insan_incelemeli(d)}
            for mod, d in dokumanlar.items()
        },
        "anlasmazlik_sayisi": hibrit_rapor.anlasmazlik_sayisi,
        "anlasmazlikli_test_sayisi": hibrit_rapor.anlasmazlikli_test_sayisi,
        "dil_modeli_raporu": dil_rapor.sozluk(),
        "hibrit_raporu": hibrit_rapor.sozluk(),
    }

    if gold_dokumanlari:
        satirlar: list[dict[str, Any]] = []
        olcum: dict[str, dict[str, float]] = {}
        for ad, gold in gold_dokumanlari.items():
            olcum[ad] = {}
            for mod, tahmin in dokumanlar.items():
                hizali = _b_yi_a_adlariyla_yaz(tahmin, kaydi_eslestir(gold, tahmin), gold)
                sonuc = degerlendir(hizali, gold)
                olcum[ad][mod] = round(sonuc.genel.f1, 4)
                satirlar += [{"gold": ad, "mod": mod, **s} for s in sonuc.tablo()]
        with open(cikti / f"{etiket}_uc_mod_olcum.csv", "w", encoding="utf-8", newline="") as f:
            yazici = csv.DictWriter(f, fieldnames=OLCUM_SUTUNLARI)
            yazici.writeheader()
            yazici.writerows(satirlar)
        rapor["olcum"] = olcum

    rapor = json.loads(json.dumps(rapor, ensure_ascii=False))  # dönen sözlük dosyadakiyle aynı olsun
    _json_yaz(cikti / f"{etiket}_uc_mod_rapor.json", rapor)
    return rapor


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("pdf")
    ayr.add_argument("--model", required=True, help="Ollama etiketi (ör. qwen3:8b) ya da llama.cpp model adı")
    ayr.add_argument("--arka-uc", choices=sorted(ARKA_UCLAR), default="ollama")
    ayr.add_argument("--adres", help="Yerel sunucu adresi; boşsa arka ucun varsayılanı")
    ayr.add_argument("--belge-no")
    ayr.add_argument("--revizyon")
    ayr.add_argument("--baglam", type=int, default=8192, help="Bağlam penceresi (token)")
    ayr.add_argument("--dusunme-kapali", action="store_true", help="Qwen3 gibi modellerde düşünme kipini kapatır")
    ayr.add_argument("--cikti", default=str(VARSAYILAN_CIKTI))
    ayr.add_argument("--gold-yok", action="store_true", help="Gold'lara karşı ölçüm yapma")
    ayr.add_argument("--bolunme", default=str(VARSAYILAN_YOL), help="Geliştirme/test bölünmesi (data/bolunme.yaml)")
    args = ayr.parse_args(argv)

    try:
        if args.belge_no and args.revizyon:
            belge_no, revizyon = args.belge_no, args.revizyon
        else:
            belge_no, revizyon = belge_no_ve_revizyon(Path(args.pdf).name)
        etiket = f"{belge_no}{revizyon}"
        istemci = YerelModelIstemcisi(
            model=args.model, arka_uc=args.arka_uc, adres=args.adres, baglam=args.baglam,
            dusunme=False if args.dusunme_kapali else None,
        )
        goldlar = None if args.gold_yok else varsayilan_goldlar(etiket)
        rapor = uc_mod_calistir(args.pdf, istemci, args.cikti, model_adi=args.model, goldlar=goldlar,
                                belge_no=belge_no, revizyon=revizyon, bolunme=args.bolunme)
    except (TestKumesiKilitli, ValueError) as hata:  # OcrGerekli de ValueError'dır
        print(f"uc_mod: {hata}", file=sys.stderr)
        return 2

    modlar = rapor["modlar"]
    print(f"{etiket}: " + ", ".join(f"{m} {modlar[m]['test_sayisi']} test {modlar[m]['sure_s']:.1f} s" for m in MODLAR)
          + f"; anlaşmazlık {rapor['anlasmazlik_sayisi']} -> {args.cikti}")
    for ad, f1ler in rapor.get("olcum", {}).items():
        print(f"  {ad}: " + ", ".join(f"{m} F1 {f1ler[m]:.3f}" for m in MODLAR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
