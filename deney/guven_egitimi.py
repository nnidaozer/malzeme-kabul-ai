#!/usr/bin/env python3
"""Güven skoru eğitimi: L2 lojistik regresyon, dışarıda bırakmalı tahmin, eşik (docs/guven_skoru.md).

Saf Python (numpy yok), Newton yöntemi (IRLS); sabit terim düzenlenmez.
Aynı girdiyle her zaman aynı model çıkar. Eğri, her revizyon ailesi (ör. 23377)
dışarıda bırakılıp kalanlarla eğitilen modelin o aile için verdiği güvenlerle çizilir. Eşik,
hedef riski aşmayan en yüksek kapsamı veren güven değeridir. Son model bütün
örneklerle eğitilir.

Kullanım:
  python deney/guven_egitimi.py --girdi deney/sonuclar/colab_uc_mod --cikti deney/sonuclar/guven_skoru
  (seçenekler: --l2 1.0 --hedef-risk 0.01 --bolunme data/bolunme.yaml --kok .)

Çıktılar: model.json, tahminler.csv, egitim_raporu.json. Gold yalnız okunur;
data/gold altına çıktı, test kümesindeki ya da taranmış (OCR gerekli) belge,
geçersiz hedef_risk ya da hiç örnek yokluğu 2 koduyla reddedilir; bu durumlarda
hiçbir şey yazılmaz.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deney.bolunme import VARSAYILAN_YOL, TestKumesiKilitli, aile
from deney.guven_verisi import GuvenOrnegi, klasorden_oku
from deney.risk_kapsam import aurc, egri
from malzeme_kabul.kural.guven_skoru import (
    OZELLIK_ADLARI, GuvenGirdileri, GuvenModeli, _gold_altinda_mi, _sigmoid,
)

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_GIRDI = KOK / "deney" / "sonuclar" / "colab_uc_mod"
VARSAYILAN_CIKTI = KOK / "deney" / "sonuclar" / "guven_skoru"
TAHMIN_SUTUNLARI = ["belge", "test_id", *OZELLIK_ADLARI, "hatali", "zorunlu_inceleme", "guven"]
_EN_COK_ADIM = 100
_TOLERANS = 1e-10
_KARARLILIK = 1e-10  # yalnız Hessian'ı tekil olmaktan korur; çözümün yerini değiştirmez


def _softplus(z: float) -> float:
    return max(z, 0.0) + math.log1p(math.exp(-abs(z)))


def _kayip(b: list[float], X: list[list[float]], y: list[float], l2: float) -> float:
    toplam = sum(_softplus(sum(bi * xi for bi, xi in zip(b, x))) - yi * sum(bi * xi for bi, xi in zip(b, x))
                 for x, yi in zip(X, y))
    return toplam + l2 / 2 * sum(bi * bi for bi in b[1:])


def _coz(A: list[list[float]], v: list[float]) -> list[float]:
    """Gauss eliminasyonu (kısmi pivotlama)."""
    n = len(v)
    M = [satir[:] + [v[i]] for i, satir in enumerate(A)]
    for k in range(n):
        p = max(range(k, n), key=lambda i: abs(M[i][k]))
        M[k], M[p] = M[p], M[k]
        for i in range(k + 1, n):
            c = M[i][k] / M[k][k]
            for j in range(k, n + 1):
                M[i][j] -= c * M[k][j]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))) / M[i][i]
    return x


def egit(girdiler: list[GuvenGirdileri], hatalilar: list[bool], l2: float = 1.0) -> GuvenModeli:
    """Hata olasılığı için L2 lojistik regresyon; eşik 0.5 (asıl eşik `esik_sec` ile seçilir)."""
    if not girdiler:
        raise ValueError("eğitim için örnek yok")
    if len(girdiler) != len(hatalilar):
        raise ValueError("girdiler ve hatalilar aynı uzunlukta olmalı")
    if not math.isfinite(l2) or l2 < 0:
        raise ValueError(f"l2 negatif olmayan sonlu bir sayı olmalı: {l2}")
    X = [[1.0, *g.vektor()] for g in girdiler]
    y = [1.0 if h else 0.0 for h in hatalilar]
    n = len(X[0])
    b = [0.0] * n
    kayip = _kayip(b, X, y, l2)
    for _ in range(_EN_COK_ADIM):
        p = [_sigmoid(sum(bi * xi for bi, xi in zip(b, x))) for x in X]
        grad = [sum((pi - yi) * x[j] for x, pi, yi in zip(X, p, y)) + (l2 * b[j] if j else 0.0) for j in range(n)]
        if max(abs(g) for g in grad) < _TOLERANS:
            break
        H = [[sum(pi * (1 - pi) * x[j] * x[k] for x, pi in zip(X, p)) + (l2 if j == k and j else 0.0)
              + (_KARARLILIK if j == k else 0.0) for k in range(n)] for j in range(n)]
        adim = _coz(H, grad)
        oran = 1.0
        for _ in range(50):  # kayıp azalana kadar adımı yarıla
            yeni = [bi - oran * di for bi, di in zip(b, adim)]
            yeni_kayip = _kayip(yeni, X, y, l2)
            if yeni_kayip <= kayip:
                break
            oran /= 2
        else:
            break
        b, kayip = yeni, yeni_kayip
    return GuvenModeli(
        agirliklar=dict(zip(OZELLIK_ADLARI, b[1:])), sabit=b[0], esik=0.5,
        bilgi={"ornek_sayisi": len(X), "l2": l2},
    )


def disarida_birakmali_tahmin(ornekler: list[GuvenOrnegi], l2: float = 1.0) -> list[float]:
    """Her örneğin güveni, kendi revizyon ailesi dışarıda bırakılarak eğitilen modelden (girdi sırasıyla).

    Aynı ailenin revizyonları (ör. 23377G ve 23377K) birlikte dışarıda kalır.
    """
    aileler = [aile(o.belge) for o in ornekler]
    if len(set(aileler)) < 2:
        raise ValueError("dışarıda bırakmalı tahmin için en az iki revizyon ailesi gerekli")
    guvenler = [0.0] * len(ornekler)
    for grup in sorted(set(aileler)):
        egitim = [o for o, a in zip(ornekler, aileler) if a != grup]
        m = egit([o.girdiler for o in egitim], [o.hatali for o in egitim], l2=l2)
        for i, (o, a) in enumerate(zip(ornekler, aileler)):
            if a == grup:
                guvenler[i] = m.guven(o.girdiler)
    return guvenler


def esik_sec(guvenler: list[float], hatalilar: list[bool], zorunlular: list[bool],
             hedef_risk: float = 0.01) -> float:
    """Riski hedefi aşmayan en yüksek kapsamlı noktanın eşiği; yoksa 1.0.

    Model güveni 1.0'a ulaşmadığından 1.0 eşiği "otomatik geçiş yok" demektir.
    hedef_risk [0, 1] içinde sonlu olmalı; değilse ValueError.
    """
    if isinstance(hedef_risk, bool) or not isinstance(hedef_risk, (int, float)) or not 0.0 <= hedef_risk <= 1.0:
        raise ValueError(f"hedef_risk 0 ile 1 arasında sonlu bir sayı olmalı: {hedef_risk!r}")
    uygun = [n for n in egri(guvenler, hatalilar, zorunlular) if n.risk <= hedef_risk]
    en_iyi = max(uygun, key=lambda n: n.kapsam)
    return min(en_iyi.esik, 1.0)


def _yaz_tahminler(yol: Path, ornekler: list[GuvenOrnegi], guvenler: list[float]) -> None:
    with open(yol, "w", encoding="utf-8", newline="") as f:
        yazici = csv.writer(f)
        yazici.writerow(TAHMIN_SUTUNLARI)
        for o, g in zip(ornekler, guvenler):
            ozellikler = [int(getattr(o.girdiler, ad)) for ad in OZELLIK_ADLARI]  # bool -> 0/1
            yazici.writerow([o.belge, o.test_id, *ozellikler, int(o.hatali), int(o.zorunlu_inceleme), repr(g)])


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("--girdi", default=str(VARSAYILAN_GIRDI), help="deney/uc_mod.py çıktı klasörü")
    ayr.add_argument("--cikti", default=str(VARSAYILAN_CIKTI))
    ayr.add_argument("--bolunme", default=str(VARSAYILAN_YOL), help="Geliştirme/test bölünmesi (data/bolunme.yaml)")
    ayr.add_argument("--kok", default=str(KOK), help="Gold'ların arandığı kök (KOK/data/gold_taslak ...)")
    ayr.add_argument("--l2", type=float, default=1.0)
    ayr.add_argument("--hedef-risk", type=float, default=0.01)
    args = ayr.parse_args(argv)

    cikti = Path(args.cikti)
    if _gold_altinda_mi(cikti):
        print(f"guven_egitimi: çıktı data/gold altına yazılamaz: {cikti}", file=sys.stderr)
        return 2
    try:
        ornekler, atlanan = klasorden_oku(args.girdi, bolunme=args.bolunme, kok=args.kok)
        if not ornekler:
            print(f"guven_egitimi: sonuç yok ({args.girdi} altında gold'u olan üç mod çıktısı bulunamadı)",
                  file=sys.stderr)
            return 2
        guvenler = disarida_birakmali_tahmin(ornekler, l2=args.l2)
        hatalilar = [o.hatali for o in ornekler]
        zorunlular = [o.zorunlu_inceleme for o in ornekler]
        esik = esik_sec(guvenler, hatalilar, zorunlular, hedef_risk=args.hedef_risk)
        model = egit([o.girdiler for o in ornekler], hatalilar, l2=args.l2)
    except (TestKumesiKilitli, ValueError) as hata:
        print(f"guven_egitimi: {hata}", file=sys.stderr)
        return 2

    belgeler = sorted({o.belge for o in ornekler})
    model = replace(model, esik=esik, bilgi={**model.bilgi, "hedef_risk": args.hedef_risk, "belgeler": belgeler})
    cikti.mkdir(parents=True, exist_ok=True)
    model.kaydet(cikti / "model.json")
    _yaz_tahminler(cikti / "tahminler.csv", ornekler, guvenler)
    rapor = {
        "ornek_sayisi": len(ornekler),
        "hatali_sayisi": sum(hatalilar),
        "zorunlu_inceleme_sayisi": sum(zorunlular),
        "belgeler": belgeler,
        "atlanan": atlanan,
        "l2": args.l2,
        "hedef_risk": args.hedef_risk,
        "esik": esik,
        "aurc_disarida_birakmali": aurc(egri(guvenler, hatalilar, zorunlular)),
        "agirliklar": model.agirliklar,
        "sabit": model.sabit,
    }
    (cikti / "egitim_raporu.json").write_text(json.dumps(rapor, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8")
    print(f"{len(ornekler)} örnek, {len(belgeler)} belge, eşik {esik:.4f}, "
          f"AURC {rapor['aurc_disarida_birakmali']:.4f} -> {cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
