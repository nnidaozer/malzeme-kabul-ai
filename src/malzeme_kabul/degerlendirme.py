"""Çıkarıcı çıktısını doğru cevaplarla (gold) alan bazında karşılaştırır.

Her iki belge de `KabulDokumani` olarak okunur ve (alan, kayıt) anahtarlı
düz bir sözlüğe çevrilir:

- testler `id` ile eşleşir: ("test.sinir.alt", "viskozite")
- koşullar "kategori:ad" ile eşleşir: ("kosul.aciklama", "kullanim:pot life")
- numune hazırlama `id` ile, raf ömrü tek kayıttır.

Her alan için:
- doğru pozitif (dp): iki tarafta da var ve değerler eşit,
- yanlış pozitif (yp): tahminde var ama gold'da yok ya da değer farklı,
- yanlış negatif (yn): gold'da var ama tahminde yok ya da değer farklı.
Yanlış değer hem yp hem yn sayılır. Boş (None) alanlar hesaba girmez.

Metinler büyük/küçük harf ve boşluk farkı gözetmeden, sayılar küçük bir
toleransla karşılaştırılır. Birim çevrilmez: birim alanı metin olarak
karşılaştırılır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .sema import KabulDokumani, Sinir

Anahtar = tuple[str, str]

_SINIR_ALANLARI = ("tur", "alt", "ust", "birim", "ifade")
_TEST_ALANLARI = ("test_adi", "test_metodu", "test_turleri", "uygulanabilirlik")
_NUMUNE_ALANLARI = (
    "kupon_malzemesi", "kupon_boyutu", "yuzey_hazirligi", "uygulama_yontemi", "kurlenme",
)


def _normal_metin(deger: str) -> str:
    return " ".join(deger.casefold().split())


def _kaydet(alanlar: dict[Anahtar, Any], alan: str, kayit: str, deger: Any) -> None:
    if deger is None or deger == "" or deger == [] or deger == set():
        return
    if isinstance(deger, (set, list, tuple)):
        deger = tuple(sorted(str(d) for d in deger))
    alanlar[(alan, kayit)] = deger


def _sinir_ekle(alanlar, onek: str, kayit: str, sinir: Sinir | None) -> None:
    if sinir is None:
        return
    for ad in _SINIR_ALANLARI:
        _kaydet(alanlar, f"{onek}.sinir.{ad}", kayit, getattr(sinir, ad))


def alanlari_duzlestir(dokuman: KabulDokumani) -> dict[Anahtar, Any]:
    """Belgeyi {(alan, kayıt): değer} sözlüğüne çevirir."""
    alanlar: dict[Anahtar, Any] = {}
    for t in dokuman.testler:
        for ad in _TEST_ALANLARI:
            _kaydet(alanlar, f"test.{ad}", t.id, getattr(t, ad))
        _sinir_ekle(alanlar, "test", t.id, t.sinir)
        _kaydet(alanlar, "test.kaynak.madde", t.id, t.kaynak.madde)
        if t.metot_kaynagi:
            _kaydet(alanlar, "test.metot_kaynagi.madde", t.id, t.metot_kaynagi.madde)

    if dokuman.raf_omru:
        r = dokuman.raf_omru
        _kaydet(alanlar, "raf_omru.sure", "raf_omru", r.sure)
        _kaydet(alanlar, "raf_omru.birim", "raf_omru", r.birim)
        _kaydet(alanlar, "raf_omru.kaynak.madde", "raf_omru", r.kaynak.madde)

    for k in dokuman.kosullar:
        kayit = f"{k.kategori}:{_normal_metin(k.ad)}"
        _kaydet(alanlar, "kosul.aciklama", kayit, k.aciklama)
        _sinir_ekle(alanlar, "kosul", kayit, k.sinir)
        _kaydet(alanlar, "kosul.kaynak.madde", kayit, k.kaynak.madde)

    for n in dokuman.numune_hazirlama:
        for ad in _NUMUNE_ALANLARI:
            _kaydet(alanlar, f"numune.{ad}", n.id, getattr(n, ad))
        _sinir_ekle(alanlar, "numune.kuru_film_kalinligi", n.id, n.kuru_film_kalinligi)
        _kaydet(alanlar, "numune.kaynak.madde", n.id, n.kaynak.madde)
    return alanlar


def degerler_esit(a: Any, b: Any) -> bool:
    """İki alan değerini karşılaştırır (metin: normalize, sayı: toleranslı)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    if isinstance(a, str) and isinstance(b, str):
        return _normal_metin(a) == _normal_metin(b)
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(degerler_esit(x, y) for x, y in zip(a, b))
    return a == b


@dataclass
class AlanSkoru:
    dp: int = 0
    yp: int = 0
    yn: int = 0

    @property
    def precision(self) -> float:
        return self.dp / (self.dp + self.yp) if self.dp + self.yp else 0.0

    @property
    def recall(self) -> float:
        return self.dp / (self.dp + self.yn) if self.dp + self.yn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


@dataclass
class Degerlendirme:
    alanlar: dict[str, AlanSkoru] = field(default_factory=dict)

    @property
    def genel(self) -> AlanSkoru:
        """Bütün alanların mikro ortalaması."""
        return AlanSkoru(
            dp=sum(a.dp for a in self.alanlar.values()),
            yp=sum(a.yp for a in self.alanlar.values()),
            yn=sum(a.yn for a in self.alanlar.values()),
        )

    def tablo(self) -> list[dict[str, Any]]:
        def satir(ad: str, s: AlanSkoru) -> dict[str, Any]:
            return {
                "alan": ad, "dp": s.dp, "yp": s.yp, "yn": s.yn,
                "precision": round(s.precision, 4), "recall": round(s.recall, 4), "f1": round(s.f1, 4),
            }

        satirlar = [satir(ad, self.alanlar[ad]) for ad in sorted(self.alanlar)]
        satirlar.append(satir("GENEL (mikro)", self.genel))
        return satirlar


def degerlendir(tahmin: KabulDokumani, gold: KabulDokumani) -> Degerlendirme:
    """Tahmini gold ile karşılaştırıp alan bazında dp/yp/yn sayar."""
    t, g = alanlari_duzlestir(tahmin), alanlari_duzlestir(gold)
    sonuc = Degerlendirme()
    for anahtar in t.keys() | g.keys():
        skor = sonuc.alanlar.setdefault(anahtar[0], AlanSkoru())
        tahminde, goldda = anahtar in t, anahtar in g
        if tahminde and goldda and degerler_esit(t[anahtar], g[anahtar]):
            skor.dp += 1
            continue
        if tahminde:
            skor.yp += 1
        if goldda:
            skor.yn += 1
    return sonuc
