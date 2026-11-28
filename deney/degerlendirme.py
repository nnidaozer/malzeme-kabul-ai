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

from dataclasses import dataclass, field
from typing import Any

# Alan düzleştirme ürünle ortaktır (tek kaynak); aynı adlarla yeniden dışa verilir.
from malzeme_kabul.sozlesme.alanlar import (  # noqa: F401
    _NUMUNE_ALANLARI,
    _SINIR_ALANLARI,
    _TEST_ALANLARI,
    Anahtar,
    _Birim,
    _kaydet,
    _kaynak_ekle,
    _normal_metin,
    _sinir_ekle,
    _tur,
    alanlari_duzlestir,
    degerler_esit,
    kayit_bolumleri,
)
from malzeme_kabul.sozlesme.sema import KabulDokumani


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
