#!/usr/bin/env python3
"""Dizüstünde küçük yerel modellerle belge başına süre ve F1 ölçümü; ağın kapalı olduğunu da gösterir.

Amaç: Nida'nın Windows dizüstünde (7,7 GB RAM, GPU yok sayılabilir) Ollama ile
qwen2.5 1.5B ve 3B modellerini (Q4_K_M) geliştirme kümesindeki gold'lu
standartlarda üç modda (yalnız kural, yalnız dil modeli, hibrit;
`deney/uc_mod.py`) çalıştırmak, belge ve sayfa başına süreyi ve gold'lara karşı
alan F1'ini raporlamak. Ölçümden önce, her model x belge ölçümünden sonra
(`ag_ara`) ve en sonda ağ denenir (`scripts/ag_kapali_mi.py`: DNS, TCP, HTTPS,
sistem vekili). Rapor `ag_kapali_calisti: true` yazar ancak: bütün denetimlerde
hiçbir deneme dışarı çıkamadıysa, ara kayıttan devam edilmediyse ve en az bir dil
modeli ölçümü hiçbir sayfa isteği başarısız olmadan tamamlandıysa.

Her model belgelerden önce bir kez ısıtılır (yükleme süresi `yukleme_s`).
İstenen model adı Ollama'da yoksa `YEDEK_ADLAR`daki eş ad (ör. `qwen2.5:3b`)
kullanılır; eşleşmeler `model_eslesmeleri`ne yazılır.

Tek komut (Wi-Fi kapalı / Ethernet çıkarılmış, Ollama çalışırken):

  python deney/dizustu_olcum.py

Çıktılar (varsayılan deney/sonuclar/dizustu/):
  dizustu_olcum.json / .csv / .md   özet rapor ve model x belge x mod satırları
  MODEL_KLASORU/                    her model için uc_mod çıktıları ve ara kayıt
                                    (model adında <>:"/\\|?* -> '_'); kopan
                                    çalışma aynı komutla ara kayıttan devam eder
                                    (ağ kanıtı sayılmaz); --sifirdan ölçülen
                                    belgelerin ara kaydını silip baştan ölçer

Çıkış kodları:
  0  en az bir dil modeli ölçümü tamamlandı (varsa hatalar raporda)
  1  hiçbir dil modeli ölçümü tamamlanmadı (modeller Ollama'da yok, hepsi hatalı
     ya da sayfa istekleri başarısız)
  2  test kümesindeki / kilitli / OCR gerektiren belge, data/gold altına çıktı ya da geçersiz girdi
  3  ağ açık (izin verilmedi: --ag-acik-izin)
  4  Ollama'ya ulaşılamadı

Test kümesindeki belgeler açılmaz; data/gold/ altına hiçbir şey yazılmaz. Yol
işlemleri pathlib ile, dosyalar utf-8 ile yapılır (Windows uyumu).
"""

from __future__ import annotations

import argparse
import csv
import http.client
import importlib.util
import json
import os
import platform
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# `python deney/dizustu_olcum.py` ile doğrudan çalışınca depo kökü yolda olsun (deney paketi için).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from malzeme_kabul.belge.adlandirma import belge_no_ve_revizyon
from malzeme_kabul.cikarim.yerel_model import ModelYanitHatasi, YerelModelIstemcisi, adres_yerel_mi

from deney.bolunme import VARSAYILAN_YOL, TestKumesiKilitli, bolunme_oku
from deney.bolunme import gold_altinda_mi as _gold_altinda_mi
from deney.uc_mod import MODLAR, uc_mod_calistir, varsayilan_goldlar

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_MODELLER = ("qwen2.5:1.5b-instruct-q4_K_M", "qwen2.5:3b-instruct-q4_K_M")
VARSAYILAN_CIKTI = KOK / "deney" / "sonuclar" / "dizustu"
VARSAYILAN_ADRES = "http://127.0.0.1:11434"
SATIR_SUTUNLARI = ["model", "belge", "mod", "sayfa_sayisi", "test_sayisi", "sure_s", "sayfa_basi_s",
                   "f1_gold_taslak", "f1_gold_codex", "basarisiz_sayfa", "devam_edilen_sayfa"]
# İstenen ad Ollama'da yoksa sırayla denenen eş adlar (`ollama pull qwen2.5:3b` ile indirilen model).
YEDEK_ADLAR: dict[str, tuple[str, ...]] = {
    "qwen2.5:1.5b-instruct-q4_K_M": ("qwen2.5:1.5b", "qwen2.5:1.5b-instruct"),
    "qwen2.5:3b-instruct-q4_K_M": ("qwen2.5:3b", "qwen2.5:3b-instruct"),
}
ISTEK_BASARISIZ = "istek başarısız"  # deney/yalniz_dil_modeli.py sayfa hatası ön eki
ISINMA_SEMASI: dict[str, Any] = {"type": "object"}
ISINMA_MESAJLARI = [
    {"role": "system", "content": "Yalnız JSON yanıt ver."},
    {"role": "user", "content": 'Bu bir ısınma isteğidir; {"tamam": true} dön.'},
]
AG_BETIGI = KOK / "scripts" / "ag_kapali_mi.py"

# Bir belgenin ölçümünü düşürüp kalanlarla devam edilen hatalar: bağlantı / zaman aşımı ve
# kilit (OSError; TestKumesiKilitli bir PermissionError'dır), bozuk gold ya da yanıt (ValueError),
# sarılmış sunucu yanıtı hatası ve yarım HTTP yanıtı.
OLCUM_HATALARI: tuple[type[BaseException], ...] = (OSError, ValueError, ModelYanitHatasi, http.client.HTTPException)


class AgAcik(Exception):
    """Ölçümden önce ağ açık bulundu ve buna izin verilmedi."""


# --- Belgeler ---------------------------------------------------------------------


def varsayilan_belgeler(bolunme: str | Path = VARSAYILAN_YOL, kok: str | Path = KOK) -> list[Path]:
    """Geliştirme kümesinde PDF'i (data/raw/ETIKET.pdf) ve gold'u olan belgeler, bölünme sırasıyla.

    Gold, data/gold_taslak ya da data/gold_codex altındaki ETIKET.json'dur; data/gold sayılmaz.
    Taranmış (OCR gerekli) belgeler alınmaz.
    """
    kok = Path(kok)
    b = bolunme_oku(bolunme)
    belgeler = []
    for etiket in b.gelistirme:
        if etiket in b.ocr_gerekli:
            continue
        pdf = kok / "data" / "raw" / f"{etiket}.pdf"
        if pdf.is_file() and varsayilan_goldlar(etiket, kok):
            belgeler.append(pdf)
    return belgeler


# --- Ağ ve Ollama -----------------------------------------------------------------


def _ag_betigi():
    """scripts/ag_kapali_mi.py'yi dosya yolundan yükler (scripts bir paket değil)."""
    tanim = importlib.util.spec_from_file_location("_ag_kapali_mi", AG_BETIGI)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    return modul


def ag_denetimi(denemeler: Callable[[], list[tuple[str, bool, str]]] | None = None) -> dict[str, Any]:
    """Ağ denemelerini yapar; hiçbiri başarılı değilse `kapali` True.

    `denemeler` verilmezse scripts/ag_kapali_mi.py'deki DNS, TCP ve HTTPS denemeleri
    sistem vekili dahil (`vekil_dahil=True`) kullanılır ve sistem vekil ayarı `vekil`e yazılır.
    """
    vekil = None
    if denemeler is None:
        betik = _ag_betigi()
        ham = betik.denemeler(vekil_dahil=True)
        vekil = dict(urllib.request.getproxies())
    else:
        ham = denemeler()
    sonuc = [{"deneme": ad, "basarili": bool(basarili), "ayrinti": ayrinti} for ad, basarili, ayrinti in ham]
    rapor: dict[str, Any] = {"kapali": not any(d["basarili"] for d in sonuc), "denemeler": sonuc}
    if vekil is not None:
        rapor["vekil"] = vekil
    return rapor


def ollama_durumu(adres: str = VARSAYILAN_ADRES, acici: Any = None, zaman_asimi_s: float = 5.0) -> dict[str, Any]:
    """Yerel Ollama sunucusunun sürümü ve indirilmiş model adları.

    Adres localhost değilse istek yapılmadan ValueError. Sunucuya ulaşılamazsa
    `modeller` boş, `hata` dolu döner. Vekil ayarları yok sayılır.
    """
    adres = adres.rstrip("/")
    if not adres_yerel_mi(adres):
        raise ValueError(f"Ollama yalnız localhost'ta aranır, verilen adres: {adres!r}")
    if acici is None:
        acici = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with acici.open(adres + "/api/version", timeout=zaman_asimi_s) as cevap:
            surum = json.loads(cevap.read().decode("utf-8")).get("version")
        with acici.open(adres + "/api/tags", timeout=zaman_asimi_s) as cevap:
            modeller = [m["name"] for m in json.loads(cevap.read().decode("utf-8")).get("models", [])]
    except (OSError, ValueError, KeyError, TypeError, AttributeError, http.client.HTTPException) as hata:
        return {"surum": None, "modeller": [], "hata": f"{type(hata).__name__}: {hata}"}
    return {"surum": surum, "modeller": modeller, "hata": None}


def model_var_mi(model: str, mevcut: list[str]) -> bool:
    """Model Ollama'da var mı? Tam ad eşleşir; etiketsiz ad ':latest' ile de eşleşir."""
    if model in mevcut:
        return True
    return ":" not in model and f"{model}:latest" in mevcut


def model_coz(model: str, mevcut: list[str]) -> str | None:
    """Ollama'da kullanılacak ad: tam ad varsa o, yoksa `YEDEK_ADLAR`daki ilk mevcut eş ad, yoksa None."""
    if model_var_mi(model, mevcut):
        return model
    for yedek in YEDEK_ADLAR.get(model, ()):
        if yedek in mevcut:
            return yedek
    return None


# --- Sistem -----------------------------------------------------------------------


_VARSAYILAN = object()


def _ram_gb(meminfo: str | Path = Path("/proc/meminfo"), windll: Any = _VARSAYILAN) -> float | None:
    """Toplam RAM (GiB, bir ondalık): önce `windll` ile GlobalMemoryStatusEx, sonra `meminfo`; olmazsa None.

    `windll` verilmezse Windows'ta `ctypes.windll`, başka sistemlerde None kullanılır.
    """
    if windll is _VARSAYILAN:
        windll = None
        if sys.platform == "win32":
            import ctypes

            windll = getattr(ctypes, "windll", None)
    try:
        if windll is not None:
            import ctypes

            class _BellekDurumu(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            durum = _BellekDurumu()
            durum.dwLength = ctypes.sizeof(_BellekDurumu)
            if windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(durum)):
                return round(durum.ullTotalPhys / 1024**3, 1)
        meminfo = Path(meminfo)
        if meminfo.is_file():
            for satir in meminfo.read_text(encoding="utf-8").splitlines():
                if satir.startswith("MemTotal:"):
                    return round(int(satir.split()[1]) / 1024**2, 1)
    except (OSError, ValueError, AttributeError, IndexError):
        return None
    return None


def sistem_bilgisi() -> dict[str, Any]:
    """İşletim sistemi, Python sürümü, işlemci sayısı ve toplam RAM (GB ya da None)."""
    return {
        "isletim_sistemi": platform.platform() or sys.platform,
        "python": platform.python_version(),
        "islemci": platform.processor() or platform.machine(),
        "islemci_sayisi": os.cpu_count(),
        "ram_gb": _ram_gb(),
    }


# --- Ölçüm ------------------------------------------------------------------------


_GECERSIZ_KARAKTERLER = '<>:"/\\|?*'


def _model_klasoru(model: str) -> str:
    """Model adından klasör adı: Windows'ta geçersiz <>:"/\\|?* karakterleri '_' olur."""
    return "".join("_" if c in _GECERSIZ_KARAKTERLER else c for c in model)


def _basarisiz_sayfa(rapor: dict[str, Any]) -> int:
    """Dil modeli isteği başarısız (bağlantı, zaman aşımı, HTTP hatası) olan sayfa sayısı."""
    sayfalar = rapor.get("dil_modeli_raporu", {}).get("sayfalar", [])
    return sum(1 for s in sayfalar if any(str(h).startswith(ISTEK_BASARISIZ) for h in s.get("hatalar", [])))


def _devam_edilen_sayfa(rapor: dict[str, Any]) -> int:
    """Modele gönderilmeyip ara kayıttan okunan sayfa sayısı."""
    return len(rapor.get("dil_modeli_raporu", {}).get("devam_edilen_sayfalar", []))


def _satirlar(model: str, rapor: dict[str, Any]) -> list[dict[str, Any]]:
    sayfa = rapor["sayfa_sayisi"]
    olcum = rapor.get("olcum", {})
    basarisiz, devam = _basarisiz_sayfa(rapor), _devam_edilen_sayfa(rapor)
    satirlar = []
    for mod in MODLAR:
        m = rapor["modlar"][mod]
        dil_var = mod != "kural"
        satirlar.append({
            "model": model,
            "belge": rapor["belge"],
            "mod": mod,
            "sayfa_sayisi": sayfa,
            "test_sayisi": m["test_sayisi"],
            "sure_s": m["sure_s"],
            "sayfa_basi_s": round(m["sure_s"] / sayfa, 4) if sayfa else None,
            "f1_gold_taslak": olcum.get("gold_taslak", {}).get(mod),
            "f1_gold_codex": olcum.get("gold_codex", {}).get(mod),
            "basarisiz_sayfa": basarisiz if dil_var else 0,
            "devam_edilen_sayfa": devam if dil_var else 0,
        })
    return satirlar


def _tamamlandi_mi(satirlar: list[dict[str, Any]]) -> bool:
    """Hiçbir sayfa isteği başarısız olmadan biten en az bir dil modeli ölçümü var mı?"""
    return any(s["mod"] == "dil_modeli" and not s["basarisiz_sayfa"] for s in satirlar)


def _belgeleri_denetle(belgeler: list[Path], bolunme: str | Path) -> list[tuple[Path, str, str]]:
    """Hiçbir model çağrılmadan bütün belgeleri bölünmeye göre denetler; (yol, belge no, revizyon)."""
    b = bolunme_oku(bolunme)
    sonuc = []
    for belge in belgeler:
        belge_no, revizyon = belge_no_ve_revizyon(belge.name)
        b.yol_kullanima_izin_ver(belge)
        b.kullanima_izin_ver(f"{belge_no}{revizyon}")
        sonuc.append((belge, belge_no, revizyon))
    return sonuc


def _f(deger: Any, bicim: str = ".3f") -> str:
    return "-" if deger is None else format(deger, bicim)


def _md(rapor: dict[str, Any]) -> str:
    def ag_satiri(ad: str, ag: dict[str, Any]) -> str:
        durum = "ağ kapalı" if ag["kapali"] else "AĞ AÇIK"
        basarili = [d["deneme"] for d in ag["denemeler"] if d["basarili"]]
        return f"- {ad}: {durum} ({len(ag['denemeler'])} deneme" + (f"; dışarı çıkan: {', '.join(basarili)})" if basarili else ")")

    s = rapor["sistem"]
    o = rapor["ollama"]
    satirlar = [
        "# Dizüstü ölçümü",
        "",
        f"- Tarih: {rapor['tarih']}",
        f"- Sistem: {s['isletim_sistemi']}, Python {s['python']}, {s['islemci_sayisi']} işlemci, RAM "
        + (f"{s['ram_gb']} GB" if s["ram_gb"] is not None else "bilinmiyor"),
        f"- Ollama: sürüm {o.get('surum') or '-'}",
        ag_satiri("Ölçümden önce", rapor["ag_once"]),
        *[ag_satiri(f"Ara denetim {i}", a) for i, a in enumerate(rapor["ag_ara"], 1)],
        ag_satiri("Ölçümden sonra", rapor["ag_sonra"]),
        "- Sonuç: " + ("ağ kapalıyken çalıştı (ag_kapali_calisti: true)" if rapor["ag_kapali_calisti"]
                       else "ağ kapalı çalıştığı gösterilmedi (ag_kapali_calisti: false)"),
    ]
    if rapor["devam_edildi"]:
        satirlar.append("- Devam edildi: bazı sayfalar önceki çalışmanın ara kaydından okundu; bu çalışma ağ "
                        "kanıtı sayılmaz. Baştan ölçmek için --sifirdan ile yeniden çalıştır.")
    if rapor["yukleme_s"]:
        satirlar.append("- Model yükleme (ısınma) süresi: "
                        + ", ".join(f"{m} {_f(s, '.1f')} s" for m, s in rapor["yukleme_s"].items()))
    satirlar += [
        "",
        "Süreler saniyedir. Hibrit süresi kural ve dil modeli sürelerini içerir. Sayfa başı süre belgenin "
        "bütün sayfalarına (metinsiz sayfalar dahil) bölünür. Başarısız sayfalı satırlar \"geçersiz\" "
        "işaretlidir (RAM yetmezliği ya da zaman aşımı belirtisi).",
        "",
        "| Model | Belge | Mod | Sayfa | Test | Süre (s) | Sayfa başı (s) | F1 gold_taslak | F1 gold_codex "
        "| Başarısız sayfa | Devam edilen sayfa |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rapor["satirlar"]:
        basarisiz = f"{r['basarisiz_sayfa']} (geçersiz)" if r["basarisiz_sayfa"] else "0"
        satirlar.append(f"| {r['model']} | {r['belge']} | {r['mod']} | {r['sayfa_sayisi']} | {r['test_sayisi']} | "
                        f"{_f(r['sure_s'], '.1f')} | {_f(r['sayfa_basi_s'], '.1f')} | {_f(r['f1_gold_taslak'])} | "
                        f"{_f(r['f1_gold_codex'])} | {basarisiz} | {r['devam_edilen_sayfa']} |")
    if rapor["atlananlar"]:
        satirlar += ["", "## Atlanan modeller", ""] + [f"- {a['model']}: {a['neden']}" for a in rapor["atlananlar"]]
    if rapor["hatalar"]:
        satirlar += ["", "## Hatalar", ""] + [f"- {h['model']} / {h['belge'] or 'ısınma'}: {h['hata']}"
                                              for h in rapor["hatalar"]]
    return "\n".join(satirlar) + "\n"


def _dosyalari_yaz(rapor: dict[str, Any], cikti: Path) -> None:
    cikti.mkdir(parents=True, exist_ok=True)
    (cikti / "dizustu_olcum.json").write_text(json.dumps(rapor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with open(cikti / "dizustu_olcum.csv", "w", encoding="utf-8", newline="") as f:
        yazici = csv.DictWriter(f, fieldnames=SATIR_SUTUNLARI)
        yazici.writeheader()
        yazici.writerows(rapor["satirlar"])
    (cikti / "dizustu_olcum.md").write_text(_md(rapor), encoding="utf-8")


def _isit(istemci: Any) -> float:
    """Modeli bir kez kısa bir istekle belleğe yükler; geçen süre (s). Yanıt doğrulanmaz."""
    t0 = time.perf_counter()
    istemci.sohbet([dict(m) for m in ISINMA_MESAJLARI], dict(ISINMA_SEMASI))
    return round(time.perf_counter() - t0, 3)


def olcum_yap(
    modeller: list[str],
    belgeler: list[str | Path],
    cikti: str | Path,
    istemci_uret: Callable[[str], Any],
    ag_denetle: Callable[[], dict[str, Any]],
    ollama: dict[str, Any],
    bolunme: str | Path = VARSAYILAN_YOL,
    kok: str | Path = KOK,
    ag_acik_izin: bool = False,
    sifirdan: bool = False,
) -> dict[str, Any]:
    """Her model x belge için üç modu çalıştırır, raporu yazar ve döner (modül açıklaması).

    Model çağrılmadan ve hiçbir şey yazılmadan: data/gold altındaki çıktı için
    ValueError, test kümesindeki / kilitli klasördeki belge için TestKumesiKilitli,
    izin yokken ağ açıksa AgAcik yükselir. Ne tam adı ne yedek adı Ollama'da olan
    model atlanır. Her model belgelerden önce ısıtılır; ısınma hatası `hatalar`a
    belgesiz (`belge: None`) yazılır ve o model atlanır. Bir belgedeki hata ya da
    başarısız sayfa isteği `hatalar`a yazılır ve kalan belgelerle devam edilir.
    `sifirdan` True ise her ölçümden önce yalnız o model x belgenin ara kayıt
    klasörü (cikti/MODEL_KLASORU/ETIKET_ara) silinir.
    """
    cikti = Path(cikti)
    if _gold_altinda_mi(cikti):
        raise ValueError(f"çıktı data/gold altına yazılamaz: {cikti}")
    denetlenen = _belgeleri_denetle([Path(b) for b in belgeler], bolunme)

    ag_once = ag_denetle()
    if not ag_once["kapali"] and not ag_acik_izin:
        raise AgAcik("ağ açık: ölçüm internetsiz çalışmayı göstermek için ağ kapalıyken yapılmalı")

    satirlar: list[dict[str, Any]] = []
    atlananlar: list[dict[str, str]] = []
    hatalar: list[dict[str, Any]] = []
    ag_ara: list[dict[str, Any]] = []
    eslesmeler: dict[str, str] = {}
    yukleme_s: dict[str, float] = {}
    for model in modeller:
        cozulen = model_coz(model, ollama.get("modeller", []))
        if cozulen is None:
            atlananlar.append({"model": model,
                               "neden": f"Ollama'da yok; internet varken bir kez: ollama pull {model}"})
            print(f"atlandı {model}: Ollama'da yok (ollama pull {model})", flush=True)
            continue
        eslesmeler[model] = cozulen
        istemci = istemci_uret(cozulen)
        try:
            yukleme_s[model] = _isit(istemci)
        except OLCUM_HATALARI as hata:
            hatalar.append({"model": model, "belge": None, "hata": f"ısınma başarısız: {type(hata).__name__}: {hata}"})
            print(f"HATA {model} ısınma: {type(hata).__name__}: {hata}", flush=True)
            continue
        print(f"{model} ({cozulen}) yüklendi: {yukleme_s[model]:.1f} s", flush=True)
        klasor = cikti / _model_klasoru(model)
        for belge, belge_no, revizyon in denetlenen:
            etiket = f"{belge_no}{revizyon}"
            try:
                if sifirdan:  # Windows'ta kilitli dosya OSError verirse yalnız bu belge atlanır
                    ara = klasor / f"{etiket}_ara"
                    if ara.is_dir():
                        shutil.rmtree(ara)
                rapor = uc_mod_calistir(belge, istemci, klasor, model_adi=model,
                                        goldlar=varsayilan_goldlar(etiket, kok),
                                        belge_no=belge_no, revizyon=revizyon, bolunme=bolunme)
            except OLCUM_HATALARI as hata:
                hatalar.append({"model": model, "belge": str(belge), "hata": f"{type(hata).__name__}: {hata}"})
                print(f"HATA {model} {etiket}: {type(hata).__name__}: {hata}", flush=True)
                ag_ara.append(ag_denetle())
                continue
            yeni = _satirlar(model, rapor)
            satirlar += yeni
            dil = next(s for s in yeni if s["mod"] == "dil_modeli")
            if dil["basarisiz_sayfa"]:
                hatalar.append({"model": model, "belge": str(belge),
                                "hata": f"{ISTEK_BASARISIZ}: {dil['basarisiz_sayfa']} sayfa (RAM yetmezliği ya da "
                                        "zaman aşımı belirtisi); ölçüm geçersiz"})
                print(f"HATA {model} {etiket}: {dil['basarisiz_sayfa']} sayfada istek başarısız", flush=True)
            print(f"{model} {etiket}: dil modeli {dil['sure_s']:.1f} s ({dil['sayfa_basi_s'] or 0:.1f} s/sayfa), "
                  f"F1 taslak {_f(dil['f1_gold_taslak'])}", flush=True)
            ag_ara.append(ag_denetle())

    ag_sonra = ag_denetle()
    tamamlandi = _tamamlandi_mi(satirlar)
    devam_edildi = any(s["devam_edilen_sayfa"] for s in satirlar)
    ag_hep_kapali = ag_once["kapali"] and ag_sonra["kapali"] and all(a["kapali"] for a in ag_ara)
    sonuc: dict[str, Any] = {
        "tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modeller": list(modeller),
        "model_eslesmeleri": eslesmeler,
        "yukleme_s": yukleme_s,
        "belgeler": [str(b) for b, _, _ in denetlenen],
        "sistem": sistem_bilgisi(),
        "ollama": ollama,
        "ag_once": ag_once,
        "ag_ara": ag_ara,
        "ag_sonra": ag_sonra,
        "devam_edildi": devam_edildi,
        "ag_kapali_calisti": bool(ag_hep_kapali and tamamlandi and not devam_edildi),
        "satirlar": satirlar,
        "atlananlar": atlananlar,
        "hatalar": hatalar,
    }
    sonuc = json.loads(json.dumps(sonuc, ensure_ascii=False))  # dönen sözlük dosyadakiyle aynı olsun
    _dosyalari_yaz(sonuc, cikti)
    return sonuc


# --- Komut satırı -----------------------------------------------------------------


def _konsolu_hazirla() -> None:
    """stdout/stderr'de kodlamaya sığmayan harfler hata yerine '?' olur (ör. Windows cp1252 konsolu)."""
    for akis in (sys.stdout, sys.stderr):
        yeniden = getattr(akis, "reconfigure", None)
        if yeniden is None:
            continue
        try:
            yeniden(errors="replace")
        except (ValueError, OSError, TypeError):
            pass


def main(argv: list[str] | None = None) -> int:
    _konsolu_hazirla()
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("--modeller", nargs="+", default=list(VARSAYILAN_MODELLER), help="Ollama etiketleri")
    ayr.add_argument("--belgeler", nargs="+", help="PDF yolları; boşsa geliştirme kümesindeki gold'lu belgeler")
    ayr.add_argument("--cikti", default=str(VARSAYILAN_CIKTI))
    ayr.add_argument("--bolunme", default=str(VARSAYILAN_YOL), help="Geliştirme/test bölünmesi (data/bolunme.yaml)")
    ayr.add_argument("--adres", default=VARSAYILAN_ADRES, help="Yerel Ollama adresi (yalnız localhost)")
    ayr.add_argument("--baglam", type=int, default=8192, help="Bağlam penceresi (token)")
    ayr.add_argument("--ag-acik-izin", action="store_true",
                     help="Ağ açıkken de ölç (ölçüm internetsiz çalışmayı kanıtlamaz)")
    ayr.add_argument("--sifirdan", action="store_true",
                     help="Ölçülen belgelerin ara kaydını silip baştan ölç (devam edilen çalışma ağ kanıtı sayılmaz)")
    args = ayr.parse_args(argv)

    try:
        belgeler = [Path(b) for b in args.belgeler] if args.belgeler else varsayilan_belgeler(args.bolunme)
        if _gold_altinda_mi(Path(args.cikti)):
            raise ValueError(f"çıktı data/gold altına yazılamaz: {args.cikti}")
        ollama = ollama_durumu(args.adres)
        if ollama["hata"]:
            print(f"dizustu_olcum: Ollama'ya ulaşılamadı ({args.adres}): {ollama['hata']}\n"
                  "Ollama'yı başlat (görev çubuğu simgesi ya da `ollama serve`) ve yeniden dene.", file=sys.stderr)
            return 4
        rapor = olcum_yap(
            args.modeller, belgeler, args.cikti,
            istemci_uret=lambda model: YerelModelIstemcisi(model=model, arka_uc="ollama", adres=args.adres,
                                                           baglam=args.baglam),
            ag_denetle=ag_denetimi, ollama=ollama, bolunme=args.bolunme, ag_acik_izin=args.ag_acik_izin,
            sifirdan=args.sifirdan,
        )
    except AgAcik as hata:
        print(f"dizustu_olcum: {hata}\nWi-Fi'yi kapat / Ethernet'i çıkar (uçak modu) ve yeniden çalıştır; "
              "ağ açıkken ölçmek için --ag-acik-izin.", file=sys.stderr)
        return 3
    except (TestKumesiKilitli, ValueError) as hata:  # OcrGerekli de ValueError'dır
        print(f"dizustu_olcum: {hata}", file=sys.stderr)
        return 2

    for a in rapor["atlananlar"]:
        print(f"atlandı {a['model']}: {a['neden']}")
    if rapor["hatalar"]:
        print(f"{len(rapor['hatalar'])} ölçüm hatalı; ayrıntı raporda.")
    if not (rapor["ag_once"]["kapali"] and rapor["ag_sonra"]["kapali"] and all(a["kapali"] for a in rapor["ag_ara"])):
        print("UYARI: ölçüm sırasında ağ açıktı; bu ölçüm internetsiz çalışmayı kanıtlamaz.")
    if rapor["devam_edildi"]:
        print("UYARI: ara kayıttan devam edildi; bu ölçüm internetsiz çalışmayı kanıtlamaz (--sifirdan ile baştan ölç).")
    print(f"ag_kapali_calisti: {str(rapor['ag_kapali_calisti']).lower()} -> {Path(args.cikti) / 'dizustu_olcum.md'}")
    if not _tamamlandi_mi(rapor["satirlar"]):
        print("dizustu_olcum: hiçbir dil modeli ölçümü tamamlanmadı.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
