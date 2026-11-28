#!/usr/bin/env python3
"""Yerel OCR katmanının ölçümü; metin tabanlı ve taranmış belgeler ayrı (docs/ocr.md "Ölçüm").

- Metin tabanlı belgeler (varsayılan MIL-PRF-23377H, J, K): her sayfa resme
  çevrilip OCR'dan geçirilir ve PDF'in kendi metniyle karşılaştırılır: kelime
  hata oranı (WER), sayısal değerlerin kesinlik / duyarlılık / F1'i, sayfa başına
  süre. Kural çıkarıcı hem PDF metninde hem OCR metninde çalıştırılır; alan
  bazında F1 PDF metninden çıkanlara göredir (gold değildir).
- Taranmış belgeler (varsayılan MIL-S-81733C; hazır OCR katmanlı MIL-PRF-23377G
  aynı grupta): ortalama Tesseract güveni, düşük güvenli kelime oranı, sayfa
  başına süre. Hazır katmanlı belgede katman ile yeni OCR arasındaki WER
  (katman referans alınır) ve iki okumadan kural çıkarıcının bulduğu test sayısı.
  Alan F1 için gold gerekir (proje sahibi etiketler).

Test kümesindeki (kilitli) ya da bölünmede olmayan belgeler okunmadan atlanır;
MIL-A-46146B varsayılan listede yoktur. Çıktılar (CIKTI, varsayılan
deney/sonuclar/ocr/): ocr_olcumu.md, ocr_olcumu.json, sayfalar.csv. data/gold
altına yazılmaz.

Kullanım:
  python deney/ocr_olcumu.py
  python deney/ocr_olcumu.py --belge MIL-PRF-23377K --dpi 300 --psm 3
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

# `python deney/<betik>.py` ile doğrudan çalışınca depo kökü yolda olsun (deney paketi için).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from malzeme_kabul.belge.ocr import OcrKelime, OcrKullanilamaz, OcrSonucu, TesseractMotoru, tesseract_var_mi
from malzeme_kabul.belge.pdf_okuyucu import KAYNAK_OCR, Belge, Sayfa, pdf_oku
from malzeme_kabul.belge.pdf_turu import pdf_turunu_belirle
from malzeme_kabul.cikarim import kural_cikarici

from deney.bolunme import VARSAYILAN_YOL, TestKumesiKilitli, bolunme_oku, gold_altinda_mi
from deney.degerlendirme import degerlendir

KOK = Path(__file__).resolve().parents[1]
HAM = KOK / "data" / "raw"
VARSAYILAN_CIKTI = KOK / "deney" / "sonuclar" / "ocr"
METIN_BELGELERI = ("MIL-PRF-23377H", "MIL-PRF-23377J", "MIL-PRF-23377K")
TARANMIS_BELGELER = ("MIL-S-81733C", "MIL-PRF-23377G")  # 23377G: hazır OCR katmanlı
SAYFA_SUTUNLARI = ["belge", "grup", "sayfa", "sure_s", "kelime_sayisi", "ortalama_guven", "dusuk_guvenli_oran",
                   "wer"]

# İşaret yalnız önünde rakam yoksa işarettir ("100-500" aralıktır). Binlik virgülün
# iki yanında OCR'ın koyduğu birer boşluk tolere edilir ("16 ,000", "16, 000").
_SAYI = re.compile(r"(?:(?<!\d)[-\u2212+])?(?:\d+(?:\s?,\s?\d{3})+(?!\d)|\d+(?:\.\d+)*)")


# --- Kelimeler ve WER ------------------------------------------------------------


def kelimelere_bol(metin: str) -> list[str]:
    """NFKC ile normalleştirip boşluklara göre böler (ﬁ -> fi, tam genişlikli rakam -> rakam)."""
    return unicodedata.normalize("NFKC", metin).split()


def _duzenleme_uzakligi(a: list[str], b: list[str]) -> int:
    onceki = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        simdiki = [i]
        for j, y in enumerate(b, 1):
            simdiki.append(min(onceki[j] + 1, simdiki[j - 1] + 1, onceki[j - 1] + (x != y)))
        onceki = simdiki
    return onceki[-1]


def kelime_hata_orani(referans: list[str], tahmin: list[str]) -> float:
    """Kelime düzeyinde Levenshtein uzaklığı / referans uzunluğu (büyük/küçük harfe duyarlı).

    İkisi de boşsa 0, yalnız referans boşsa 1.
    """
    if not referans:
        return 0.0 if not tahmin else 1.0
    return _duzenleme_uzakligi(referans, tahmin) / len(referans)


# --- Sayılar ---------------------------------------------------------------------


def sayilari_bul(metin: str) -> list[str]:
    """Metindeki sayılar, görünüş sırasıyla.

    Binlik virgül (OCR'ın virgülün iki yanına koyduğu boşluk dahil) kaldırılır:
    "16 ,000" ve "16, 000" -> "16000". Ondalık ve madde numarası tek belirteçtir
    ("3.6.3"); tire aralığı iki sayıdır ("100-500" -> "100", "500"). Önünde rakam
    olmayan "-" ya da U+2212 eksi işaretidir ("-40", "−65" -> "-65"); "+" atılır.
    """
    metin = unicodedata.normalize("NFKC", metin)
    sonuc = []
    for m in _SAYI.finditer(metin):
        sayi = re.sub(r"[\s,+]", "", m.group(0)).replace("\u2212", "-")
        sonuc.append(sayi)
    return sonuc


def karsilastirma_metni(metin: str) -> str:
    """WER ve sayı ölçümünden önce iki tarafa uygulanan normalleştirme.

    PDF glif kodları kural çıkarıcının `metni_normallestir`'iyle düzeltilir
    ("(cid:114)" -> "±") ve indirme sitesinin filigran satırları ("Downloaded
    from ...") atılır; OCR bunları okumaz ya da farklı okur.
    """
    satirlar = (kural_cikarici.metni_normallestir(s) for s in metin.splitlines())
    return "\n".join(s for s in satirlar if s and not s.startswith("Downloaded from"))


def sayi_olcumu(referans: list[str], tahmin: list[str]) -> dict[str, float]:
    """Çoklu küme kesişimiyle kesinlik, duyarlılık ve F1. İkisi de boşsa hepsi 1."""
    dp = sum((Counter(referans) & Counter(tahmin)).values())
    kesinlik = dp / len(tahmin) if tahmin else (1.0 if not referans else 0.0)
    duyarlilik = dp / len(referans) if referans else (1.0 if not tahmin else 0.0)
    f1 = 2 * kesinlik * duyarlilik / (kesinlik + duyarlilik) if kesinlik + duyarlilik else 0.0
    return {"kesinlik": kesinlik, "duyarlilik": duyarlilik, "f1": f1}


# --- Ölçüm -----------------------------------------------------------------------


def _yuvarla(deger: float | None, basamak: int = 4) -> float | None:
    return None if deger is None else round(deger, basamak)


def _sayfalari_ocrla(motor, yol: Path, sayfa_sayisi: int) -> tuple[list[OcrSonucu], list[float]]:
    sonuclar, sureler = [], []
    for no in range(1, sayfa_sayisi + 1):
        t0 = time.perf_counter()
        sonuclar.append(motor.sayfa_oku(yol, no))
        sureler.append(time.perf_counter() - t0)
    return sonuclar, sureler


def _ocr_belgesi(yol: Path, sonuclar: list[OcrSonucu]) -> Belge:
    return Belge(yol, [Sayfa(no=i, metin=s.metin, kaynak=KAYNAK_OCR, ocr_guveni=s.ortalama_guven)
                       for i, s in enumerate(sonuclar, 1)])


def _kural_cikar(yol: Path, etiket: str, hatalar: list[str], belge: Belge | None = None):
    """Kural çıkarıcı; hata atarsa hata `hatalar`'a yazılır ve None döner (ölçüm durmaz)."""
    try:
        return kural_cikarici.cikar(yol, etiket[:-1], etiket[-1], belge=belge)
    except Exception as hata:  # noqa: BLE001 - ölçüm bir belgedeki çıkarıcı hatasıyla durmamalı
        hatalar.append(f"{type(hata).__name__}: {hata}")
        return None


def _hata_yaz(satir: dict[str, Any], hatalar: list[str]) -> None:
    if hatalar:
        satir["kural_hatasi"] = "; ".join(dict.fromkeys(hatalar))


def _belge_wer(referanslar: list[str], tahminler: list[str]) -> float:
    """Sayfa sayfa düzenleme uzaklıklarının toplamı / toplam referans kelime sayısı."""
    hata = toplam = 0
    for r, t in zip(referanslar, tahminler):
        rk, tk = kelimelere_bol(r), kelimelere_bol(t)
        hata += _duzenleme_uzakligi(rk, tk) if rk else len(tk)
        toplam += len(rk)
    return hata / toplam if toplam else (0.0 if hata == 0 else 1.0)


def _havuz(sonuclar: list[OcrSonucu]) -> OcrSonucu:
    kelimeler: tuple[OcrKelime, ...] = tuple(k for s in sonuclar for k in s.kelimeler)
    return OcrSonucu("\n\n".join(s.metin for s in sonuclar), kelimeler)


def _sayfa_satirlari(etiket, grup, sonuclar, sureler, wer_listesi=None) -> list[dict[str, Any]]:
    return [
        {"belge": etiket, "grup": grup, "sayfa": i, "sure_s": round(sure, 3), "kelime_sayisi": len(s.kelimeler),
         "ortalama_guven": _yuvarla(s.ortalama_guven, 2), "dusuk_guvenli_oran": round(s.dusuk_guvenli_oran(), 4),
         "wer": "" if wer_listesi is None else round(wer_listesi[i - 1], 4)}
        for i, (s, sure) in enumerate(zip(sonuclar, sureler), 1)
    ]


def _metin_belgesi_olc(etiket: str, yol: Path, motor) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pdf = pdf_oku(yol)
    sonuclar, sureler = _sayfalari_ocrla(motor, yol, len(pdf.sayfalar))
    referans = [karsilastirma_metni(s.metin) for s in pdf.sayfalar]
    ocr_metni = [karsilastirma_metni(s.metin) for s in sonuclar]
    sayilar = sayi_olcumu(sayilari_bul("\n".join(referans)), sayilari_bul("\n".join(ocr_metni)))
    havuz = _havuz(sonuclar)

    hatalar: list[str] = []
    pdf_dok = _kural_cikar(yol, etiket, hatalar)
    ocr_dok = _kural_cikar(yol, etiket, hatalar, _ocr_belgesi(yol, sonuclar))
    alan_f1 = None
    if pdf_dok is not None and ocr_dok is not None:
        try:
            alan_f1 = degerlendir(tahmin=ocr_dok, gold=pdf_dok).genel.f1
        except Exception as hata:  # noqa: BLE001
            hatalar.append(f"değerlendirme: {type(hata).__name__}: {hata}")

    satir = {
        "belge": etiket,
        "sayfa_sayisi": len(pdf.sayfalar),
        "wer": _belge_wer(referans, ocr_metni),
        "sayi_kesinlik": sayilar["kesinlik"],
        "sayi_duyarlilik": sayilar["duyarlilik"],
        "sayi_f1": sayilar["f1"],
        "ortalama_guven": havuz.ortalama_guven,
        "sure_s_sayfa_basi": round(sum(sureler) / len(sureler), 3) if sureler else 0.0,
        "alan_f1_pdf_metnine_gore": alan_f1,
        "kural_test_sayisi_pdf": None if pdf_dok is None else len(pdf_dok.testler),
        "kural_test_sayisi_ocr": None if ocr_dok is None else len(ocr_dok.testler),
    }
    _hata_yaz(satir, hatalar)
    sayfa_wer = [kelime_hata_orani(kelimelere_bol(r), kelimelere_bol(t)) for r, t in zip(referans, ocr_metni)]
    return satir, _sayfa_satirlari(etiket, "metin_tabanli", sonuclar, sureler, sayfa_wer)


def _taranmis_belge_olc(etiket: str, yol: Path, motor, katmanli: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pdf = pdf_oku(yol)
    sonuclar, sureler = _sayfalari_ocrla(motor, yol, len(pdf.sayfalar))
    havuz = _havuz(sonuclar)
    hatalar: list[str] = []
    ocr_dok = _kural_cikar(yol, etiket, hatalar, _ocr_belgesi(yol, sonuclar))
    satir: dict[str, Any] = {
        "belge": etiket,
        "tur": "ocr_katmanlı" if katmanli else "taranmış",
        "sayfa_sayisi": len(pdf.sayfalar),
        "ortalama_guven": havuz.ortalama_guven,
        "dusuk_guvenli_oran": havuz.dusuk_guvenli_oran(),
        "sure_s_sayfa_basi": round(sum(sureler) / len(sureler), 3) if sureler else 0.0,
        "kural_test_sayisi_ocr": None if ocr_dok is None else len(ocr_dok.testler),
    }
    if katmanli:
        katman_dok = _kural_cikar(yol, etiket, hatalar, pdf)
        satir["katman_uyumu_wer"] = _belge_wer([karsilastirma_metni(s.metin) for s in pdf.sayfalar],
                                               [karsilastirma_metni(s.metin) for s in sonuclar])
        satir["kural_test_sayisi_katman"] = None if katman_dok is None else len(katman_dok.testler)
    _hata_yaz(satir, hatalar)
    return satir, _sayfa_satirlari(etiket, "taranmis", sonuclar, sureler)


def _motor_bilgisi(motor) -> dict[str, Any]:
    try:
        surum = motor.surum()
    except (OcrKullanilamaz, AttributeError):
        surum = None
    return {"ad": "tesseract", "surum": surum, "dil": getattr(motor, "dil", None),
            "psm": getattr(motor, "psm", None), "dpi": getattr(motor, "dpi", None)}


def olcum_yap(belgeler: list[tuple[str, Path]], motor, cikti: str | Path,
              bolunme: str | Path = VARSAYILAN_YOL, ham_klasor: str | Path | None = None) -> dict[str, Any]:
    """Belgeleri (etiket, pdf yolu) ölçer, raporları `cikti` altına yazar ve raporu döner.

    `cikti` data/gold altındaysa hiçbir şey okunmadan ValueError verir. Test
    kümesindeki, bölünmede olmayan ya da dosyası olmayan belge okunmadan atlanır.
    """
    cikti = Path(cikti)
    if gold_altinda_mi(cikti):
        raise ValueError(f"çıktı data/gold altına yazılamaz: {cikti}")
    if ham_klasor is not None and not Path(ham_klasor).is_dir():
        raise ValueError(f"ham klasör yok ya da klasör değil: {ham_klasor}")
    b = bolunme_oku(bolunme)
    rapor: dict[str, Any] = {
        "tarih": datetime.now().isoformat(timespec="seconds"),
        "makine": {"platform": platform.platform(), "islemci": platform.processor() or platform.machine(),
                   "cekirdek": os.cpu_count(), "python": platform.python_version()},
        "motor": _motor_bilgisi(motor),
        "metin_tabanli": [],
        "taranmis": [],
        "atlandi": [],
    }
    sayfa_satirlari: list[dict[str, Any]] = []
    for etiket, yol in belgeler:
        yol = Path(yol)
        try:
            etiket = b.belgeyi_denetle(yol, etiket, ocr=True,
                                       ham_klasor=ham_klasor)
        except (TestKumesiKilitli, ValueError) as hata:
            rapor["atlandi"].append({"belge": etiket, "neden": str(hata)})
            continue
        if not yol.is_file():
            rapor["atlandi"].append({"belge": etiket, "neden": f"dosya yok: {yol}"})
            continue
        tur = pdf_turunu_belirle(yol)
        if etiket in b.ocr_gerekli or tur.ocr_gerekli:
            satir, sayfalar = _taranmis_belge_olc(etiket, yol, motor, katmanli=bool(tur.ocr_katmanli_sayfalar))
            rapor["taranmis"].append(satir)
        else:
            satir, sayfalar = _metin_belgesi_olc(etiket, yol, motor)
            rapor["metin_tabanli"].append(satir)
        sayfa_satirlari += sayfalar

    cikti.mkdir(parents=True, exist_ok=True)
    (cikti / "ocr_olcumu.json").write_text(json.dumps(rapor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with open(cikti / "sayfalar.csv", "w", encoding="utf-8", newline="") as f:
        yazici = csv.DictWriter(f, fieldnames=SAYFA_SUTUNLARI)
        yazici.writeheader()
        yazici.writerows(sayfa_satirlari)
    (cikti / "ocr_olcumu.md").write_text(_markdown(rapor), encoding="utf-8")
    return rapor


def _h(deger: Any) -> str:
    if deger is None:
        return "-"
    if isinstance(deger, float):
        return f"{deger:.3f}"
    return str(deger)


def _markdown(rapor: dict[str, Any]) -> str:
    m, mk = rapor["motor"], rapor["makine"]
    satirlar = [
        "# OCR ölçümü",
        "",
        f"- Motor: tesseract {m['surum'] or 'bilinmiyor'} (dil {m['dil']}, dpi {m['dpi']}, psm {m['psm']})",
        f"- Makine: {mk['platform']}, {mk['islemci']}, {mk['cekirdek']} çekirdek, Python {mk['python']}",
        f"- Tarih: {rapor['tarih']}",
        "",
        "## Metin tabanlı belgeler",
        "",
        "Her sayfa resme çevrilip OCR'dan geçirildi ve PDF'in kendi metniyle karşılaştırıldı. "
        "Alan F1 gold'a göre DEĞİL, kural çıkarıcının PDF metninden çıkardığına göredir "
        "(OCR'ın çıkarımı ne kadar bozduğunu gösterir). OCR sayfalarında tablo okunmaz: bu ölçümde "
        "bütün sayfalar OCR'dan geçtiği için kural çıkarıcı test tablosunu (TABLE II) göremez; "
        "Alan F1 ve OCR tarafındaki test sayısı bu yüzden düşük çıkabilir. WER ve sayı ölçümünden önce "
        "iki tarafta glif kodları düzeltilir ve \"Downloaded from\" filigran satırları atılır.",
        "",
        "| Belge | Sayfa | WER | Sayı kesinlik | Sayı duyarlılık | Sayı F1 | Ort. güven | s/sayfa "
        "| Alan F1 (PDF metnine göre) | Kural test (PDF / OCR) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in rapor["metin_tabanli"]:
        satirlar.append(
            f"| {s['belge']} | {s['sayfa_sayisi']} | {_h(s['wer'])} | {_h(s['sayi_kesinlik'])} | "
            f"{_h(s['sayi_duyarlilik'])} | {_h(s['sayi_f1'])} | {_h(s['ortalama_guven'])} | "
            f"{_h(s['sure_s_sayfa_basi'])} | {_h(s['alan_f1_pdf_metnine_gore'])} | "
            f"{_h(s['kural_test_sayisi_pdf'])} / {_h(s['kural_test_sayisi_ocr'])} |"
        )
    satirlar += [
        "",
        "## Taranmış belgeler",
        "",
        "Doğru metin yok; Tesseract güveni ve süre raporlanır. Düşük güvenli kelime: güven < 60. "
        "Hazır OCR katmanlı belgede katman uyumu WER'i, hazır katman referans alınarak hesaplandı "
        "(ikisi de doğru metin değildir). Alan F1 gold etiketi gelene kadar yok (proje sahibi etiketler). "
        "Hazır OCR katmanlı MIL-PRF-23377G bu tabloda gösterilir; bölünmedeki tür sayımı (turlere_ayir) "
        "ise onu metin tabanlı sayar.",
        "",
        "| Belge | Tür | Sayfa | Ort. güven | Düşük güvenli oran | s/sayfa | Katman uyumu WER "
        "| Kural test (katman / OCR) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in rapor["taranmis"]:
        satirlar.append(
            f"| {s['belge']} | {s['tur']} | {s['sayfa_sayisi']} | {_h(s['ortalama_guven'])} | "
            f"{_h(s['dusuk_guvenli_oran'])} | {_h(s['sure_s_sayfa_basi'])} | {_h(s.get('katman_uyumu_wer'))} | "
            f"{_h(s.get('kural_test_sayisi_katman'))} / {_h(s['kural_test_sayisi_ocr'])} |"
        )
    hatali = [s for s in rapor["metin_tabanli"] + rapor["taranmis"] if s.get("kural_hatasi")]
    satirlar += ["", "## Kural çıkarıcı hataları", "",
                 "Kural çıkarıcı bu belgelerde hata verdi; ilgili alanlar boş (-), OCR ölçümü sürdü.", ""]
    satirlar += [f"- {s['belge']}: {s['kural_hatasi']}" for s in hatali] or ["- yok"]
    satirlar += ["", "## Atlananlar", ""]
    satirlar += [f"- {a['belge']}: {a['neden']}" for a in rapor["atlandi"]] or ["- yok"]
    return "\n".join(satirlar) + "\n"


def varsayilan_belgeler(ham: Path = HAM) -> list[tuple[str, Path]]:
    """Varsayılan ölçüm listesi (test kümesindeki MIL-A-46146B yok)."""
    return [(etiket, Path(ham) / f"{etiket}.pdf") for etiket in METIN_BELGELERI + TARANMIS_BELGELER]


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("--belge", action="append", help="Yalnız bu etiket(ler), ör. MIL-PRF-23377K (data/raw/ETIKET.pdf)")
    ayr.add_argument("--cikti", default=str(VARSAYILAN_CIKTI))
    ayr.add_argument("--bolunme", default=str(VARSAYILAN_YOL))
    ayr.add_argument("--ham-klasor",
                     help="İçerik kilidi için data/raw'a ek olarak taranan ham belge klasörü")
    ayr.add_argument("--dpi", type=int, default=300)
    ayr.add_argument("--psm", type=int, default=3)
    ayr.add_argument("--dil", default="eng")
    args = ayr.parse_args(argv)
    if args.ham_klasor is not None and not Path(args.ham_klasor).is_dir():
        print(f"ocr_olcumu: ham klasör yok ya da klasör değil: {args.ham_klasor}", file=sys.stderr)
        return 2

    if not tesseract_var_mi():
        print("ocr_olcumu: tesseract bulunamadı; kurulum: docs/ocr.md", file=sys.stderr)
        return 2
    belgeler = ([(e, HAM / f"{e}.pdf") for e in args.belge] if args.belge else varsayilan_belgeler())
    try:
        motor = TesseractMotoru(dil=args.dil, psm=args.psm, dpi=args.dpi)
        rapor = olcum_yap(belgeler, motor, args.cikti, args.bolunme, ham_klasor=args.ham_klasor)
    except (ValueError, OcrKullanilamaz) as hata:
        print(f"ocr_olcumu: {hata}", file=sys.stderr)
        return 2
    print(f"metin tabanlı {len(rapor['metin_tabanli'])}, taranmış {len(rapor['taranmis'])}, "
          f"atlanan {len(rapor['atlandi'])} -> {args.cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
