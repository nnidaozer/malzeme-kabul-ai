"""Çıkarıcı çıktısını doğru cevaplarla (gold) alan bazında karşılaştırır.

Her iki belge de `KabulDokumani` olarak okunur ve (alan, kayıt) anahtarlı
düz bir sözlüğe çevrilir:

- testler `id` ile eşleşir: ("test.sinir.alt", "viskozite")
- koşullar "kategori:ad" ile eşleşir: ("kosul.aciklama", "kullanim:pot life")
- numune hazırlama `id` ile, raf ömrü kap türüyle ("genel" kap türü boşsa).

Her alan için:
- doğru pozitif (dp): iki tarafta da var ve değerler eşit,
- yanlış pozitif (yp): tahminde var ama gold'da yok ya da değer farklı,
- yanlış negatif (yn): gold'da var ama tahminde yok ya da değer farklı.
Yanlış değer hem yp hem yn sayılır. Boş (None) alanlar hesaba girmez.

F1 iki biçimde raporlanır: genel (bütün alanların mikro ortalaması) ve bölüm
bazında. Bölüm, kaydın şart maddesidir (`kaynak.madde`, ör. "3.3.2.8" ya da
"TABLE I"); gold'da olan kayıt gold'daki maddeye, yalnız tahminde olan kayıt
tahmindeki maddeye yazılır. Bölüm ortalaması her bölümün precision, recall ve
F1 değerlerinin aritmetik ortalamasıdır; böylece satır satır tutulan büyük bir
tablo (ör. MIL-PRF-81733D soyulma mukavemeti, 126 kayıt) ölçümü domine etmez
(etiketleme kılavuzu K10).

Metinler büyük/küçük harf ve boşluk farkı gözetmeden, sayılar küçük bir
toleransla karşılaştırılır. Birimler pint ile çözülüp karşılaştırılır ("s" ile
"second" aynıdır) ama değerler çevrilmez. Sınırın orijinal metni ölçülmez;
yalnızca yapılandırılmış alanlar ölçülür.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from malzeme_kabul.kural.birimler import birimi_coz
from malzeme_kabul.sozlesme.sema import KabulDokumani, Kaynak, Sinir

Anahtar = tuple[str, str]

_SINIR_ALANLARI = ("kriter_turu", "alt", "ust", "alt_dahil", "ust_dahil", "birim")
_TEST_ALANLARI = ("test_adi", "kaynak_tablo_adi", "test_metodu", "test_turleri", "uygulanabilirlik", "numune_hazirlama_id")
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


class _Birim(str):
    """Birim alanı: pint ile çözülerek karşılaştırılır."""


def _sinir_ekle(alanlar, onek: str, kayit: str, sinir: Sinir | None, ad_oneki: str = "sinir") -> None:
    if sinir is None:
        return
    for ad in _SINIR_ALANLARI:
        deger = getattr(sinir, ad)
        # "dahil mi" bilgisi yalnızca ilgili sınır varsa anlamlıdır; yoksa puanı şişirmesin.
        if (ad == "alt_dahil" and sinir.alt is None) or (ad == "ust_dahil" and sinir.ust is None):
            continue
        if ad == "birim" and deger is not None:
            deger = _Birim(deger)
        _kaydet(alanlar, f"{onek}.{ad_oneki}.{ad}", kayit, deger)


def _kaynak_ekle(alanlar, onek: str, kayit: str, kaynak: Kaynak | None) -> None:
    if kaynak is None:
        return
    for ad in ("belge_no", "revizyon", "madde"):
        _kaydet(alanlar, f"{onek}.{ad}", kayit, getattr(kaynak, ad))


def alanlari_duzlestir(dokuman: KabulDokumani) -> dict[Anahtar, Any]:
    """Belgeyi {(alan, kayıt): değer} sözlüğüne çevirir."""
    alanlar: dict[Anahtar, Any] = {}
    for t in dokuman.testler:
        for ad in _TEST_ALANLARI:
            _kaydet(alanlar, f"test.{ad}", t.id, getattr(t, ad))
        _sinir_ekle(alanlar, "test", t.id, t.sinir)
        _kaynak_ekle(alanlar, "test.kaynak", t.id, t.kaynak)
        _kaynak_ekle(alanlar, "test.metot_kaynagi", t.id, t.metot_kaynagi)

    for r in dokuman.raf_omurleri:
        kayit = _normal_metin(r.kap_turu) if r.kap_turu else "genel"
        _kaydet(alanlar, "raf_omru.sure", kayit, r.sure)
        _kaydet(alanlar, "raf_omru.birim", kayit, _Birim(r.birim))
        _sinir_ekle(alanlar, "raf_omru", kayit, r.kosul, ad_oneki="kosul")
        _kaynak_ekle(alanlar, "raf_omru.kaynak", kayit, r.kaynak)

    for k in dokuman.kosullar:
        kayit = f"{k.kategori}:{_normal_metin(k.ad)}"
        _kaydet(alanlar, "kosul.aciklama", kayit, k.aciklama)
        _sinir_ekle(alanlar, "kosul", kayit, k.sinir)
        _kaynak_ekle(alanlar, "kosul.kaynak", kayit, k.kaynak)

    for n in dokuman.numune_hazirlama:
        for ad in _NUMUNE_ALANLARI:
            _kaydet(alanlar, f"numune.{ad}", n.id, getattr(n, ad))
        _sinir_ekle(alanlar, "numune", n.id, n.kuru_film_kalinligi, ad_oneki="kuru_film_kalinligi")
        _kaynak_ekle(alanlar, "numune.kaynak", n.id, n.kaynak)
    return alanlar


def _tur(alan: str) -> str:
    return alan.split(".", 1)[0]


def kayit_bolumleri(dokuman: KabulDokumani) -> dict[tuple[str, str], str]:
    """{(kayıt türü, kayıt): şart maddesi}; kayıt adları `alanlari_duzlestir` ile aynı."""
    bolum: dict[tuple[str, str], str] = {}
    for t in dokuman.testler:
        bolum[("test", t.id)] = t.kaynak.madde
    for r in dokuman.raf_omurleri:
        bolum[("raf_omru", _normal_metin(r.kap_turu) if r.kap_turu else "genel")] = r.kaynak.madde
    for k in dokuman.kosullar:
        bolum[("kosul", f"{k.kategori}:{_normal_metin(k.ad)}")] = k.kaynak.madde
    for n in dokuman.numune_hazirlama:
        bolum[("numune", n.id)] = n.kaynak.madde
    return bolum


def degerler_esit(a: Any, b: Any) -> bool:
    """İki alan değerini karşılaştırır (metin: normalize, sayı: toleranslı)."""
    if isinstance(a, _Birim) and isinstance(b, _Birim):
        try:
            return birimi_coz(a) == birimi_coz(b)
        except ValueError:
            return _normal_metin(a) == _normal_metin(b)
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
    bolumler: dict[str, AlanSkoru] = field(default_factory=dict)

    @property
    def bolum_ortalamasi(self) -> dict[str, float]:
        """Bölümlerin precision, recall ve F1 değerlerinin aritmetik (makro) ortalaması."""
        if not self.bolumler:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
        n = len(self.bolumler)
        return {
            ad: sum(getattr(b, ad) for b in self.bolumler.values()) / n
            for ad in ("precision", "recall", "f1")
        }

    def bolum_tablosu(self) -> list[dict[str, Any]]:
        """Bölüm başına dp/yp/yn ve P/R/F1, madde sırasıyla."""
        def sira(madde: str) -> list[Any]:
            return [(0, int(p)) if p.isdigit() else (1, p) for p in madde.replace(" ", ".").split(".")]

        return [
            {"bolum": ad, "dp": b.dp, "yp": b.yp, "yn": b.yn, "precision": round(b.precision, 4),
             "recall": round(b.recall, 4), "f1": round(b.f1, 4)}
            for ad, b in sorted(self.bolumler.items(), key=lambda x: sira(x[0]))
        ]

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
        ort = self.bolum_ortalamasi
        satirlar.append({
            "alan": "GENEL (bölüm ortalaması)", "dp": "", "yp": "", "yn": "",
            **{ad: round(d, 4) for ad, d in ort.items()},
        })
        return satirlar


def degerlendir(tahmin: KabulDokumani, gold: KabulDokumani) -> Degerlendirme:
    """Tahmini gold ile karşılaştırıp alan bazında dp/yp/yn sayar."""
    t, g = alanlari_duzlestir(tahmin), alanlari_duzlestir(gold)
    gold_bolum, tahmin_bolum = kayit_bolumleri(gold), kayit_bolumleri(tahmin)
    sonuc = Degerlendirme()
    for anahtar in t.keys() | g.keys():
        kayit = (_tur(anahtar[0]), anahtar[1])
        bolum = gold_bolum.get(kayit) or tahmin_bolum.get(kayit) or "?"
        skorlar = (sonuc.alanlar.setdefault(anahtar[0], AlanSkoru()), sonuc.bolumler.setdefault(bolum, AlanSkoru()))
        tahminde, goldda = anahtar in t, anahtar in g
        for skor in skorlar:
            if tahminde and goldda and degerler_esit(t[anahtar], g[anahtar]):
                skor.dp += 1
                continue
            if tahminde:
                skor.yp += 1
            if goldda:
                skor.yn += 1
    return sonuc
