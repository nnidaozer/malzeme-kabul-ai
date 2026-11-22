"""İki bağımsız doğru cevap taslağını alan alan karşılaştırır.

Doğru cevaplar iki modelle ayrı ayrı hazırlanır (bkz.
docs/bagimsiz_etiketleme_istemi.md). Proje sahibi yalnızca iki taslağın
ayrıştığı satırlara ve uyuşan satırlardan rastgele seçilen bir kontrol örneğine
bakar.

Bir "satır", bir kayıttaki tek bir alanın değeridir (ör. viskozite testinin
üst sınırı). Satırlar `degerlendirme.alanlari_duzlestir` ile çıkarılır ve
`degerlendirme.degerler_esit` ile karşılaştırılır; F1 ölçümüyle aynı kural.

İki model aynı kayda farklı kimlik verebilir. Kayıtlar önce anahtarla
eşleşir (test ve numune: `id`, koşul: kategori + ad, raf ömrü: kap türü).
Anahtarı tutmayan kayıtlar, aynı kaynak maddesinde (koşulda aynı kategoride)
ve adları yeterince benzerse eşleştirilir; bu eşleşmeler `benzerlik` diye
işaretlenir, çünkü yanlış eşleşme olabilirler ve elle bakılmaları gerekir.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Literal

from .degerlendirme import _normal_metin, alanlari_duzlestir, degerler_esit
from .sema import KabulDokumani

Durum = Literal["uyusan", "ayrisan", "yalniz_a", "yalniz_b"]
Yontem = Literal["anahtar", "benzerlik"]

BENZERLIK_ESIGI = 0.6
VARSAYILAN_ORAN = 0.2
VARSAYILAN_SEED = 20261209

# Düzleştirilmiş alan adının öneki -> kayıt türü
_ONEK_TUR = {"test": "test", "kosul": "kosul", "raf_omru": "raf_omru", "numune": "numune"}


@dataclass(frozen=True)
class Eslesme:
    """A ve B taslağındaki aynı kaydın eşleşmesi."""

    tur: str
    a: str
    b: str
    yontem: Yontem
    benzerlik: float = 1.0
    madde: str | None = None


@dataclass(frozen=True)
class Satir:
    durum: Durum
    alan: str
    kayit_a: str | None
    kayit_b: str | None
    a: Any
    b: Any
    eslesme: Yontem | None
    madde: str | None = None

    @property
    def kayit(self) -> str:
        if self.kayit_a and self.kayit_b and self.kayit_a != self.kayit_b:
            return f"{self.kayit_a} ≈ {self.kayit_b}"
        return self.kayit_a or self.kayit_b or ""

    @property
    def sira(self) -> tuple[str, str]:
        return (self.alan, self.kayit)


@dataclass(frozen=True)
class _Kayit:
    tur: str
    kimlik: str  # kullanıcıya gösterilen ad
    anahtar: str  # düzleştirmedeki kayıt anahtarı
    ad: str  # benzerlik için ad
    madde: str
    grup: str = ""  # yalnızca aynı gruptakiler eşleşir (koşulda kategori)


def _kayitlar(d: KabulDokumani) -> list[_Kayit]:
    sonuc = [_Kayit("test", t.id, t.id, t.test_adi, t.kaynak.madde) for t in d.testler]
    sonuc += [
        _Kayit("kosul", f"{k.kategori}:{k.ad}", f"{k.kategori}:{_normal_metin(k.ad)}", k.ad, k.kaynak.madde, k.kategori)
        for k in d.kosullar
    ]
    sonuc += [
        _Kayit(
            "raf_omru", r.kap_turu or "genel", _normal_metin(r.kap_turu) if r.kap_turu else "genel",
            r.kap_turu or "genel", r.kaynak.madde,
        )
        for r in d.raf_omurleri
    ]
    sonuc += [_Kayit("numune", n.id, n.id, n.id, n.kaynak.madde) for n in d.numune_hazirlama]
    return sonuc


def _sozcukler(metin: str) -> list[str]:
    return [s for s in re.split(r"[\W_]+", metin.casefold()) if s]


def ad_benzerligi(a: str, b: str) -> float:
    """0..1 arası benzerlik: karakter benzerliği ile ortak sözcük oranının büyüğü."""
    sa, sb = _sozcukler(a), _sozcukler(b)
    karakter = SequenceMatcher(None, " ".join(sa), " ".join(sb)).ratio()
    if not sa or not sb:
        return karakter
    ortak = len(set(sa) & set(sb)) / min(len(set(sa)), len(set(sb)))
    return max(karakter, ortak)


def kaydi_eslestir(a: KabulDokumani, b: KabulDokumani) -> list[Eslesme]:
    """A ve B'deki kayıtları önce anahtarla, kalanları ad benzerliğiyle eşleştirir."""
    ka, kb = _kayitlar(a), _kayitlar(b)
    eslesmeler: list[Eslesme] = []
    b_anahtar = {(k.tur, k.anahtar): k for k in kb}
    kalan_a, kullanilan_b = [], set()
    for k in ka:
        karsi = b_anahtar.get((k.tur, k.anahtar))
        if karsi is not None and (karsi.tur, karsi.anahtar) not in kullanilan_b:
            eslesmeler.append(Eslesme(k.tur, k.kimlik, karsi.kimlik, "anahtar", 1.0, k.madde))
            kullanilan_b.add((karsi.tur, karsi.anahtar))
        else:
            kalan_a.append(k)
    kalan_b = [k for k in kb if (k.tur, k.anahtar) not in kullanilan_b]

    adaylar = []
    for x in kalan_a:
        for y in kalan_b:
            if x.tur != y.tur or x.madde != y.madde or x.grup != y.grup:
                continue
            puan = ad_benzerligi(x.ad, y.ad)
            if puan >= BENZERLIK_ESIGI:
                karakter = SequenceMatcher(None, x.ad.casefold(), y.ad.casefold()).ratio()
                adaylar.append((-puan, -karakter, x.kimlik, y.kimlik, x, y, puan))
    adaylar.sort(key=lambda t: t[:4])
    alinan_a, alinan_b = set(), set()
    for *_, x, y, puan in adaylar:
        if (x.tur, x.anahtar) in alinan_a or (y.tur, y.anahtar) in alinan_b:
            continue
        alinan_a.add((x.tur, x.anahtar))
        alinan_b.add((y.tur, y.anahtar))
        eslesmeler.append(Eslesme(x.tur, x.kimlik, y.kimlik, "benzerlik", round(puan, 3), x.madde))
    return sorted(eslesmeler, key=lambda e: (e.tur, e.a))


def _b_yi_a_adlariyla_yaz(b: KabulDokumani, eslesmeler: list[Eslesme], a: KabulDokumani) -> KabulDokumani:
    """Benzerlikle eşleşen B kayıtlarına A'daki kimliklerini verir."""
    harita = {(e.tur, e.b): e.a for e in eslesmeler if e.yontem == "benzerlik"}
    a_kosul = {f"{k.kategori}:{k.ad}": k for k in a.kosullar}
    veri = b.model_dump(mode="json")
    numune = {}
    for n in veri["numune_hazirlama"]:
        yeni = harita.get(("numune", n["id"]))
        if yeni:
            numune[n["id"]] = yeni
            n["id"] = yeni
    for t in veri["testler"]:
        t["id"] = harita.get(("test", t["id"]), t["id"])
        if t.get("numune_hazirlama_id") in numune:
            t["numune_hazirlama_id"] = numune[t["numune_hazirlama_id"]]
    for k in veri["kosullar"]:
        yeni = harita.get(("kosul", f"{k['kategori']}:{k['ad']}"))
        if yeni:
            k["ad"] = a_kosul[yeni].ad
    for r in veri["raf_omurleri"]:
        yeni = harita.get(("raf_omru", r["kap_turu"] or "genel"))
        if yeni:
            r["kap_turu"] = None if yeni == "genel" else yeni
    return KabulDokumani.model_validate(veri)


@dataclass
class Karsilastirma:
    satirlar: list[Satir] = field(default_factory=list)
    eslesmeler: list[Eslesme] = field(default_factory=list)

    def _durumdakiler(self, durum: Durum) -> list[Satir]:
        return [s for s in self.satirlar if s.durum == durum]

    @property
    def uyusan(self) -> list[Satir]:
        return self._durumdakiler("uyusan")

    @property
    def ayrisan(self) -> list[Satir]:
        return self._durumdakiler("ayrisan")

    @property
    def yalniz_a(self) -> list[Satir]:
        return self._durumdakiler("yalniz_a")

    @property
    def yalniz_b(self) -> list[Satir]:
        return self._durumdakiler("yalniz_b")

    @property
    def benzerlik_eslesmeleri(self) -> list[Eslesme]:
        return [e for e in self.eslesmeler if e.yontem == "benzerlik"]

    @property
    def uyusma_orani(self) -> float:
        """Uyuşan satır sayısı / bütün satırlar (ayrışan ve tek tarafta olanlar dahil)."""
        return len(self.uyusan) / len(self.satirlar) if self.satirlar else 0.0

    def alan_dokumu(self) -> list[dict[str, Any]]:
        sayac: dict[str, dict[str, int]] = {}
        for s in self.satirlar:
            d = sayac.setdefault(s.alan, {"uyusan": 0, "ayrisan": 0, "yalniz_a": 0, "yalniz_b": 0})
            d[s.durum] += 1
        sonuc = []
        for alan in sorted(sayac):
            d = sayac[alan]
            toplam = sum(d.values())
            sonuc.append({"alan": alan, **d, "toplam": toplam, "oran": round(d["uyusan"] / toplam, 4)})
        return sonuc

    def kontrol_ornegi(self, oran: float = VARSAYILAN_ORAN, seed: int = VARSAYILAN_SEED) -> list[Satir]:
        """Uyuşan satırlardan tekrarlanabilir rastgele örnek (oran yukarı yuvarlanır)."""
        if not 0.0 <= oran <= 1.0:
            raise ValueError(f"oran 0 ile 1 arasında olmalı: {oran}")
        havuz = sorted(self.uyusan, key=lambda s: s.sira)
        adet = math.ceil(round(len(havuz) * oran, 9))
        return sorted(random.Random(seed).sample(havuz, adet), key=lambda s: s.sira)


def karsilastir(a: KabulDokumani, b: KabulDokumani) -> Karsilastirma:
    """İki taslağı satır satır karşılaştırır."""
    eslesmeler = kaydi_eslestir(a, b)
    b_yeni = _b_yi_a_adlariyla_yaz(b, eslesmeler, a)

    # Düzleştirme anahtarı -> (A kimliği, B kimliği, yöntem, madde)
    def anahtar(tur: str, kimlik: str, d: KabulDokumani) -> str:
        return next(k.anahtar for k in _kayitlar(d) if k.tur == tur and k.kimlik == kimlik)

    bilgi: dict[tuple[str, str], tuple[str | None, str | None, Yontem | None, str | None]] = {}
    for k in _kayitlar(a):
        bilgi[(k.tur, k.anahtar)] = (k.kimlik, None, None, k.madde)
    for k in _kayitlar(b):
        bilgi.setdefault((k.tur, k.anahtar), (None, k.kimlik, None, k.madde))
    for e in eslesmeler:
        bilgi[(e.tur, anahtar(e.tur, e.a, a))] = (e.a, e.b, e.yontem, e.madde)

    ta, tb = alanlari_duzlestir(a), alanlari_duzlestir(b_yeni)
    satirlar = []
    for alan, kayit in ta.keys() | tb.keys():
        tur = _ONEK_TUR[alan.split(".", 1)[0]]
        kimlik_a, kimlik_b, yontem, madde = bilgi.get((tur, kayit), (kayit, kayit, None, None))
        a_var, b_var = (alan, kayit) in ta, (alan, kayit) in tb
        va, vb = ta.get((alan, kayit)), tb.get((alan, kayit))
        if a_var and b_var:
            durum: Durum = "uyusan" if degerler_esit(va, vb) else "ayrisan"
        else:
            durum = "yalniz_a" if a_var else "yalniz_b"
        satirlar.append(Satir(durum, alan, kimlik_a, kimlik_b, va, vb, yontem, madde))
    satirlar.sort(key=lambda s: s.sira)
    return Karsilastirma(satirlar=satirlar, eslesmeler=eslesmeler)
