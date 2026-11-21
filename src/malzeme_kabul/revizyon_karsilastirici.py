"""Revizyon karşılaştırıcı: bir standardın iki revizyonu arasındaki şart farkları.

Dil modeli kullanmaz; karşılaştırma tamamen kurallarla yapılır. Üç düzeyde
fark bulunur:

1. Numaralı paragraflar (şartlar): eklenen, kaldırılan, değişen ve numarası
   değişen maddeler. Paragraflar önce aynı numara ve benzer başlıkla, sonra
   aynı başlıkla (numarası değişmişse), sonra aynı numara ve benzer metinle
   eşleştirilir. Eşleşmeyenler eklendi/kaldırıldı sayılır.
2. Test tablosu ("Requirement Paragraph / Test Paragraph" tablosu): eklenen,
   kaldırılan testler ve şart maddesi, test maddesi ya da test metodu değişen
   testler.
3. Kabul (conformance) muayenesi kapsamı: "with the exception of" ile kabul
   dışında bırakılan testlerin değişimi.

Değişen paragraflar önem derecesiyle işaretlenir:
- sayisal: metindeki sayı/birim değerleri değişti (sınır, süre, sıcaklık...).
- metin: sayılar aynı, ifade değişti.
- bicimsel: yalnız boşluk, tire, büyük/küçük harf gibi yazım farkı.

`guncelleme_onerileri` eski revizyondan üretilmiş bir kabul dokümanında hangi
satırların farklardan etkilendiğini ve ne yapılması gerektiğini önerir.
Öneriler karar değildir; mühendis onaylar.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from .kural_cikarici import kabul_disi_testler, metni_normallestir, paragraflara_bol
from .pdf_okuyucu import Tablo, pdf_oku
from .sema import KabulDokumani

FarkTuru = Literal["eklendi", "kaldirildi", "degisti"]
Onem = Literal["sayisal", "metin", "bicimsel"]
OneriTuru = Literal["guncelle", "kaldir", "ekle", "numara", "gozden_gecir"]

# Son paragrafa yapışan arka kapak metni (görevli birimler, DD Form 1426).
_ARKA_KAPAK = re.compile(r"\s*Custodians:.*$", re.S)
# Paragrafa yapışan tablo metni: "TABLE II. Test methods. <satırlar> 1/ <dipnot>".
_TABLO_BASLIGI = re.compile(r"\bTABLE ([IVXLC]+)\.\s+([^.]+?)(?:\s*-\s*Continued)?\.\s*")
_DIPNOT = re.compile(r"\b1/ (?=[A-Z][a-z])")


# --- Veri yapıları ------------------------------------------------------------------


@dataclass(frozen=True)
class Sart:
    """Standarttaki numaralı bir paragraf ya da tablo ("TABLE I")."""

    madde: str
    baslik: str
    metin: str
    sayfa: int
    ust: str | None = None
    """Tablolarda, tablonun içinde geçtiği paragrafın numarası."""

    @property
    def tablo(self) -> bool:
        return self.madde.startswith("TABLE ")

    @property
    def bolum(self) -> int:
        return int((self.ust if self.tablo and self.ust else self.madde).split(".")[0])

    @property
    def sira(self) -> tuple[int, ...]:
        if self.tablo:
            return tuple(int(p) for p in (self.ust or "9").split(".")) + (999,)
        return tuple(int(p) for p in self.madde.split("."))


@dataclass
class MetinDegisikligi:
    """Kelime düzeyinde tek bir değişiklik parçası. Boş taraf ekleme ya da silmedir."""

    eski: str
    yeni: str


@dataclass
class SartFarki:
    tur: FarkTuru
    eski: Sart | None
    yeni: Sart | None
    yeniden_numaralandi: bool = False
    baslik_degisti: bool = False
    onem: Onem | None = None
    """Yalnız metni değişen maddelerde dolu; yalnız numarası değişende None."""
    degisiklikler: list[MetinDegisikligi] = field(default_factory=list)
    eski_degerler: list[str] = field(default_factory=list)
    """Eski metinde olup yenide olmayan sayı/birim değerleri."""
    yeni_degerler: list[str] = field(default_factory=list)
    """Yeni metinde olup eskide olmayan sayı/birim değerleri."""

    @property
    def madde(self) -> str:
        return (self.yeni or self.eski).madde

    @property
    def baslik(self) -> str:
        return (self.yeni or self.eski).baslik

    @property
    def icerik_degisti(self) -> bool:
        return self.tur != "degisti" or self.onem in ("sayisal", "metin")


@dataclass(frozen=True)
class TestSatiri:
    """Test tablosundaki bir satır."""

    __test__ = False  # pytest bu sınıfı test sınıfı sanmasın

    ad: str
    sart_maddesi: str
    test_maddesi: str | None
    metot: str | None
    sayfa: int


@dataclass
class TestFarki:
    __test__ = False

    tur: FarkTuru
    ad: str
    eski: TestSatiri | None
    yeni: TestSatiri | None
    degisen_alanlar: list[str] = field(default_factory=list)


@dataclass
class GuncellemeOnerisi:
    hedef: str
    """'test:<id>', 'raf_omru[:<kap türü>]', 'kosul:<ad>', 'numune:<id>', 'yeni_test:<ad>',
    'yeni_sart:<madde>' ya da 'kabul_kapsami:<test>'."""
    tur: OneriTuru
    madde: str
    oneri: str


@dataclass
class RevizyonFarki:
    belge_no: str
    eski_revizyon: str
    yeni_revizyon: str
    sart_farklari: list[SartFarki]
    ayni_kalan: int
    test_farklari: list[TestFarki]
    eski_kabul_disi: list[str]
    yeni_kabul_disi: list[str]

    @property
    def eski_etiket(self) -> str:
        return f"{self.belge_no}{self.eski_revizyon}"

    @property
    def yeni_etiket(self) -> str:
        return f"{self.belge_no}{self.yeni_revizyon}"

    def ozet(self) -> dict[str, int]:
        sf = self.sart_farklari
        degisen = [f for f in sf if f.tur == "degisti" and f.onem in ("sayisal", "metin")]
        return {
            "eklenen_sart": sum(f.tur == "eklendi" for f in sf),
            "kaldirilan_sart": sum(f.tur == "kaldirildi" for f in sf),
            "degisen_sart": len(degisen),
            "sayisal_degisen_sart": sum(f.onem == "sayisal" for f in degisen),
            "yeniden_numaralanan_sart": sum(f.yeniden_numaralandi for f in sf),
            "ayni_kalan_sart": self.ayni_kalan,
            "eklenen_test": sum(t.tur == "eklendi" for t in self.test_farklari),
            "kaldirilan_test": sum(t.tur == "kaldirildi" for t in self.test_farklari),
            "degisen_test": sum(t.tur == "degisti" for t in self.test_farklari),
        }

    def sozluk(self) -> dict:
        veri = asdict(self)
        veri["ozet"] = self.ozet()
        for f, ham in zip(self.sart_farklari, veri["sart_farklari"]):
            ham["madde"] = f.madde
        return veri

    def json(self, oneriler: list[GuncellemeOnerisi] | None = None) -> str:
        veri = self.sozluk()
        if oneriler is not None:
            veri["guncelleme_onerileri"] = [asdict(o) for o in oneriler]
        return json.dumps(veri, ensure_ascii=False, indent=2) + "\n"


# --- Normalleştirme -------------------------------------------------------------------

_TIRELER = str.maketrans({"–": "-", "—": "-", "‐": "-", "’": "'", "‘": "'", "“": '"', "”": '"'})


def _goruntu_metni(metin: str) -> str:
    """Karşılaştırmada kullanılan metin: glifler düzeltilmiş, tire/tırnak ve derece yazımı tek biçimde."""
    metin = metni_normallestir(metin).translate(_TIRELER)
    metin = re.sub(r"\s*°\s*([CF])\b", r" °\1", metin)  # "46° C", "46 °C" -> "46 °C"
    return re.sub(r"±\s+", "±", metin)


def _iskelet(metin: str) -> str:
    """Yalnız harf ve rakamlar, küçük harfle: biçimsel farkları yok sayar."""
    return re.sub(r"[^a-z0-9µ°]", "", metin.lower())


def _baslik_anahtari(baslik: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", baslik.lower()).strip()


def _benzerlik(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


# --- Sayısal değerler ------------------------------------------------------------------

_KELIME_SAYILAR = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fourteen": 14,
    "twenty": 20, "thirty": 30,
}
_BIRIMLER = [
    (r"°\s?C", "°C"), (r"°\s?F", "°F"), (r"%|percent", "%"), (r"g/L", "g/L"),
    (r"seconds?", "second"), (r"minutes?", "minute"), (r"hours?", "hour"), (r"days?", "day"),
    (r"weeks?", "week"), (r"months?", "month"), (r"years?", "year"),
    (r"mils?", "mil"), (r"µm|microns?", "µm"), (r"mm|millimeters?", "mm"), (r"nm|nanometers?", "nm"),
    (r"inch(?:es)?", "inch"), (r"quarts?", "quart"), (r"pints?", "pint"), (r"gallons?", "gallon"),
    (r"mL|milliliters?", "mL"), (r"ppm|parts per million", "ppm"), (r"psi", "psi"),
]
_BIRIM = "|".join(f"(?:{k})" for k, _ in _BIRIMLER)
_SAYI = r"\d+(?:\.\d+)?|" + "|".join(_KELIME_SAYILAR)
_DEGER = re.compile(
    r"(?<![\w\-/.])(" + _SAYI + r")(?![\w\-/]|\.\d)(?:\s*(" + _BIRIM + r")(?![A-Za-z]))?",
    re.I,
)
# Madde ya da tablo atfı olan sayıların önündeki sözcükler.
_ATIF_ONCESI = re.compile(
    r"(?:\bsee|\bin|\bper|\bof|\bto|\bwith|\bparagraphs?|\bsection|\band|\bor|,)\s*$", re.I
)


def _birimi_adlandir(birim: str) -> str:
    for kalip, ad in _BIRIMLER:
        if re.fullmatch(kalip, birim, flags=re.I):
            return ad
    return birim


def sayisal_degerler(metin: str) -> list[str]:
    """Metindeki sayı/birim değerlerini sırasıyla döner: 'six months' -> '6 month'.

    Madde atıfları ("see 4.5.2", "in 4.5"), parantez içi atıflar ve belge
    numaraları (ASTM D3335, MIL-PRF-23377) sayılmaz. Sözle yazılan sayılar
    rakama çevrilir. Birim karşılaştırma için tekil ada indirgenir; birim
    dönüşümü yapılmaz.
    """
    metin = _goruntu_metni(metin)
    metin = re.sub(r"\((?:see|table|figure|\d+\.\d)[^)]*\)", " ", metin, flags=re.I)
    bulunan: list[list] = []  # [sayı, birim, başlangıç, bitiş]
    for m in _DEGER.finditer(metin):
        sayi, birim = m.group(1), m.group(2)
        if sayi.lower() in _KELIME_SAYILAR:
            if not birim:  # "one complete kit" gibi sözel sayılar değer değil
                continue
            sayi = str(_KELIME_SAYILAR[sayi.lower()])
        bulunan.append([sayi, _birimi_adlandir(birim) if birim else None, m.start(), m.end()])

    # Aralık ve toleranslarda birim yalnız sonda yazılır: "0.5 to 1.0 mils", "65.5 ±3 °C".
    for i in range(len(bulunan) - 2, -1, -1):
        onceki, sonraki = bulunan[i], bulunan[i + 1]
        arada = metin[onceki[3]: sonraki[2]].strip()
        if onceki[1] is None and sonraki[1] and arada in {"to", "-", "±", "and", "or"}:
            onceki[1] = sonraki[1]

    degerler = []
    for sayi, birim, bas, _ in bulunan:
        if re.fullmatch(r"[1-6](\.[1-9]\d*)+", sayi) and not birim and _ATIF_ONCESI.search(metin[:bas]):
            continue  # madde atfı: "specified in 4.5"
        degerler.append(f"{sayi} {birim}" if birim else sayi)
    return degerler


# --- Şartlar ve eşleştirme --------------------------------------------------------------


def tablolari_ayir(metin: str, ust: str, sayfa: int) -> tuple[str, list[Sart]]:
    """Paragraf metnine yapışan tabloları ayırır: (paragrafın kendi metni, tablolar).

    Her tablo "TABLE <no>" maddesi olur. Test tablosunun ("Test methods")
    satırları `tablo_satirlari` ile ayrıca karşılaştırıldığı için metninde yalnız
    dipnotları ("1/ ...") kalır; dipnotlar şart taşıyabilir. Diğer tablolar bütün
    metinleriyle tutulur.
    """
    basliklar = list(_TABLO_BASLIGI.finditer(metin))
    if not basliklar:
        return metin, []
    tablolar = []
    for i, m in enumerate(basliklar):
        son = basliklar[i + 1].start() if i + 1 < len(basliklar) else len(metin)
        govde = metin[m.end(): son].strip()
        baslik = m.group(2).strip()
        if "test method" in baslik.lower():
            dipnot = _DIPNOT.search(govde)
            govde = govde[dipnot.start():] if dipnot else ""
        tablolar.append(Sart(madde=f"TABLE {m.group(1)}", baslik=baslik, metin=govde, sayfa=sayfa, ust=ust))
    return metin[: basliklar[0].start()].strip(), tablolar


def sartlari_cikar(belge, belge_etiketi: str) -> dict[str, Sart]:
    """Okunmuş PDF'ten {madde: Sart}; tablolar "TABLE I" gibi ayrı madde olur.

    Arka kapak metni son paragraftan atılır. Tablodan sonra paragrafın devam
    eden cümlesi varsa tablonun metnine karışır; bu bilinen bir sınırdır.
    """
    sartlar: dict[str, Sart] = {}
    for no, p in paragraflara_bol(belge, belge_no=belge_etiketi).items():
        metin, tablolar = tablolari_ayir(_ARKA_KAPAK.sub("", p.metin), no, p.sayfa)
        sartlar[no] = Sart(madde=no, baslik=p.baslik, metin=metin, sayfa=p.sayfa)
        for t in tablolar:
            onceki = sartlar.get(t.madde)
            if onceki is not None:  # sayfalara bölünmüş tablo ("Continued")
                t = Sart(madde=t.madde, baslik=onceki.baslik, metin=f"{onceki.metin} {t.metin}".strip(),
                         sayfa=onceki.sayfa, ust=onceki.ust)
            sartlar[t.madde] = t
    return sartlar


def sartlari_eslestir(eski: dict[str, Sart], yeni: dict[str, Sart]) -> list[tuple[Sart | None, Sart | None]]:
    """İki revizyonun paragraflarını eşleştirir; eşleşmeyenler (s, None) ya da (None, s) olur."""
    kalan_eski = dict(eski)
    kalan_yeni = dict(yeni)
    ciftler: list[tuple[Sart | None, Sart | None]] = []

    def esle(e: Sart, y: Sart) -> None:
        ciftler.append((e, y))
        del kalan_eski[e.madde]
        del kalan_yeni[y.madde]

    def basliga_gore(sartlar: dict[str, Sart]) -> dict[str, list[Sart]]:
        gruplar: dict[str, list[Sart]] = {}
        for s in sartlar.values():
            gruplar.setdefault(_baslik_anahtari(s.baslik), []).append(s)
        return gruplar

    # 1. Aynı numara, aynı başlık.
    for no in list(kalan_eski):
        if no in kalan_yeni and _baslik_anahtari(kalan_eski[no].baslik) == _baslik_anahtari(kalan_yeni[no].baslik):
            esle(kalan_eski[no], kalan_yeni[no])

    # 2. Aynı başlık, farklı numara (iki tarafta da tekse): taşınan ya da kayan maddeler.
    eski_b, yeni_b = basliga_gore(kalan_eski), basliga_gore(kalan_yeni)
    for anahtar, es in eski_b.items():
        ys = yeni_b.get(anahtar, [])
        if len(es) == 1 and len(ys) == 1:
            esle(es[0], ys[0])

    # 3. Aynı numara, benzer başlık ("Class C" -> "Class C1") ve metin de benzer.
    # Kısa başlıklar ("Class C2"/"Class C3") metne bakmadan kolayca benzer çıkar.
    for no in list(kalan_eski):
        if no in kalan_yeni:
            e, y = kalan_eski[no], kalan_yeni[no]
            metin_benzer = not (e.metin and y.metin) or _benzerlik(_iskelet(e.metin), _iskelet(y.metin)) >= 0.5
            if metin_benzer and _benzerlik(_baslik_anahtari(e.baslik), _baslik_anahtari(y.baslik)) >= 0.6:
                esle(e, y)

    # 4. Aynı numara, başlık değişmiş ama metin benzer.
    for no in list(kalan_eski):
        if no in kalan_yeni:
            e, y = kalan_eski[no], kalan_yeni[no]
            if e.metin and y.metin and _benzerlik(_iskelet(e.metin), _iskelet(y.metin)) >= 0.6:
                esle(e, y)

    ciftler += [(e, None) for e in kalan_eski.values()]
    ciftler += [(None, y) for y in kalan_yeni.values()]
    ciftler.sort(key=lambda c: (c[1] or c[0]).sira)
    return ciftler


def _metin_degisiklikleri(eski: str, yeni: str) -> list[MetinDegisikligi]:
    a, b = eski.split(), yeni.split()
    parcalar = []
    for islem, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if islem != "equal":
            parcalar.append(MetinDegisikligi(eski=" ".join(a[i1:i2]), yeni=" ".join(b[j1:j2])))
    return parcalar


def sart_farki(eski: Sart | None, yeni: Sart | None) -> SartFarki | None:
    """İki paragrafın farkı; aynıysa None."""
    if eski is None and yeni is None:
        raise ValueError("en az bir şart gerekli")
    if eski is None:
        return SartFarki(tur="eklendi", eski=None, yeni=yeni, yeni_degerler=sayisal_degerler(yeni.metin))
    if yeni is None:
        return SartFarki(tur="kaldirildi", eski=eski, yeni=None, eski_degerler=sayisal_degerler(eski.metin))

    eski_metin, yeni_metin = _goruntu_metni(eski.metin), _goruntu_metni(yeni.metin)
    numara = eski.madde != yeni.madde
    baslik = _baslik_anahtari(eski.baslik) != _baslik_anahtari(yeni.baslik)
    if eski_metin == yeni_metin:
        onem = None
    elif _iskelet(eski_metin) == _iskelet(yeni_metin):
        onem = "bicimsel"
    else:
        onem = "metin"

    if onem is None and not numara and not baslik:
        return None

    fark = SartFarki(tur="degisti", eski=eski, yeni=yeni, yeniden_numaralandi=numara,
                     baslik_degisti=baslik, onem=onem)
    if onem == "metin":
        e_say, y_say = Counter(sayisal_degerler(eski_metin)), Counter(sayisal_degerler(yeni_metin))
        fark.eski_degerler = list((e_say - y_say).elements())
        fark.yeni_degerler = list((y_say - e_say).elements())
        if fark.eski_degerler or fark.yeni_degerler:
            fark.onem = "sayisal"
        fark.degisiklikler = _metin_degisiklikleri(eski_metin, yeni_metin)
    return fark


# --- Test tablosu -------------------------------------------------------------------------


def _hucre(deger: str) -> str | None:
    deger = _goruntu_metni(deger.replace("\n", " "))
    return None if deger in {"", "-", "--", "---"} else deger


def tablo_satirlari(tablolar: list[tuple[int, Tablo]]) -> list[TestSatiri]:
    """'Requirement Paragraph / Test Paragraph' tablolarının satırları.

    Metot sütunları birleştirilir: H/J'de ayrı olan FED-STD-141 ve ASTM sütunları
    tek "metot" alanında toplanır. Test adındaki dipnot işaretleri ("1/") atılır.
    """
    satirlar: list[TestSatiri] = []
    gorulen: set[str] = set()
    for sayfa, tablo in tablolar:
        if not tablo:
            continue
        baslik = [_goruntu_metni(h.replace("\n", " ")) for h in tablo[0]]
        birlesik = " ".join(baslik).lower()
        if not ("requirement" in birlesik and "test paragraph" in birlesik):
            continue
        for ham in tablo[1:]:
            if len(ham) < 4 or not _hucre(ham[0]):
                continue
            ad = re.sub(r"\s*\d/$", "", _hucre(ham[0]))
            sart_maddesi = _hucre(ham[1]) or ""
            if not re.fullmatch(r"[1-6](\.\d+)*", sart_maddesi) or ad.lower() in gorulen:
                continue
            gorulen.add(ad.lower())
            metotlar = []
            for etiket, hucre in zip(baslik[3:], ham[3:]):
                deger = _hucre(hucre)
                if deger is None:
                    continue
                if etiket.upper().startswith("FED-STD-141") and re.fullmatch(r"\d+", deger):
                    deger = f"FED-STD-141 Method {deger}"
                metotlar.append(deger)
            satirlar.append(TestSatiri(
                ad=ad, sart_maddesi=sart_maddesi, test_maddesi=_hucre(ham[2]),
                metot="; ".join(metotlar) or None, sayfa=sayfa,
            ))
    return satirlar


def _test_anahtari(ad: str) -> str:
    return _baslik_anahtari(re.sub(r"\s*\d/$", "", ad))


def tablo_farklari(eski: list[TestSatiri], yeni: list[TestSatiri]) -> list[TestFarki]:
    """Test tablosu farkları. Test adı yazım farkı gözetmeden eşleştirilir."""
    eski_s = {_test_anahtari(t.ad): t for t in eski}
    yeni_s = {_test_anahtari(t.ad): t for t in yeni}
    farklar: list[TestFarki] = []
    for anahtar, e in eski_s.items():
        y = yeni_s.get(anahtar)
        if y is None:
            farklar.append(TestFarki(tur="kaldirildi", ad=e.ad, eski=e, yeni=None))
            continue
        alanlar = [
            alan for alan in ("sart_maddesi", "test_maddesi", "metot")
            if _iskelet(getattr(e, alan) or "") != _iskelet(getattr(y, alan) or "")
        ]
        if alanlar:
            farklar.append(TestFarki(tur="degisti", ad=y.ad, eski=e, yeni=y, degisen_alanlar=alanlar))
    for anahtar, y in yeni_s.items():
        if anahtar not in eski_s:
            farklar.append(TestFarki(tur="eklendi", ad=y.ad, eski=None, yeni=y))
    return farklar


# --- Kabul muayenesi kapsamı ------------------------------------------------------------------


def kabul_disi_listesi(sartlar: dict[str, Sart]) -> list[str]:
    """Kabul muayenesinin dışında bırakılan testler (küçük harf, sıralı)."""
    for s in sorted(sartlar.values(), key=lambda s: s.sira):
        konu = f"{s.baslik} {s.metin}".lower()
        if s.bolum == 4 and "conformance" in konu and "with the exception of" in konu:
            adlar = (re.sub(r"\s*\([^)]*\)", "", a).strip() for a in kabul_disi_testler(s.metin))
            return sorted({a for a in adlar if a})
    return []


# --- Karşılaştırma -----------------------------------------------------------------------------


def karsilastir(
    belge_no: str,
    eski_revizyon: str, eski_sartlar: dict[str, Sart], eski_tablo: list[TestSatiri],
    yeni_revizyon: str, yeni_sartlar: dict[str, Sart], yeni_tablo: list[TestSatiri],
) -> RevizyonFarki:
    farklar, ayni = [], 0
    for e, y in sartlari_eslestir(eski_sartlar, yeni_sartlar):
        f = sart_farki(e, y)
        if f is None:
            ayni += 1
        else:
            farklar.append(f)
    return RevizyonFarki(
        belge_no=belge_no, eski_revizyon=eski_revizyon, yeni_revizyon=yeni_revizyon,
        sart_farklari=farklar, ayni_kalan=ayni,
        test_farklari=tablo_farklari(eski_tablo, yeni_tablo),
        eski_kabul_disi=kabul_disi_listesi(eski_sartlar),
        yeni_kabul_disi=kabul_disi_listesi(yeni_sartlar),
    )


def revizyonlari_karsilastir(
    eski_pdf: str | Path, yeni_pdf: str | Path, belge_no: str, eski_revizyon: str, yeni_revizyon: str,
) -> RevizyonFarki:
    """İki revizyonun PDF'lerini okuyup karşılaştırır."""
    eski_belge, yeni_belge = pdf_oku(eski_pdf), pdf_oku(yeni_pdf)
    return karsilastir(
        belge_no,
        eski_revizyon, sartlari_cikar(eski_belge, f"{belge_no}{eski_revizyon}"),
        tablo_satirlari(eski_belge.tablolar()),
        yeni_revizyon, sartlari_cikar(yeni_belge, f"{belge_no}{yeni_revizyon}"),
        tablo_satirlari(yeni_belge.tablolar()),
    )


# --- Kabul dokümanı güncelleme önerileri -------------------------------------------------------


def _deger_ozeti(f: SartFarki) -> str:
    eski = ", ".join(f.eski_degerler) or "yok"
    yeni = ", ".join(f.yeni_degerler) or "yok"
    return f"kaldırılan değerler: {eski}; eklenen değerler: {yeni}"


def _sart_onerisi(hedef: str, f: SartFarki, yeni_etiket: str) -> GuncellemeOnerisi | None:
    madde = f.eski.madde
    if f.tur == "kaldirildi":
        return GuncellemeOnerisi(hedef, "kaldir", madde,
                                 f"{madde} {yeni_etiket} revizyonunda yok; satır çıkarılmalı ya da yeni dayanağı bulunmalı.")
    parcalar = []
    tur: OneriTuru = "numara"
    if f.onem == "sayisal":
        tur = "guncelle"
        parcalar.append(f"{madde} maddesinde sayısal değerler değişti ({_deger_ozeti(f)}); "
                        "sınır yeniden çıkarılıp onaylanmalı.")
    elif f.onem == "metin":
        tur = "gozden_gecir"
        parcalar.append(f"{madde} maddesinin metni değişti; kriter metni gözden geçirilmeli.")
    if f.yeniden_numaralandi:
        parcalar.append(f"Madde numarası {f.eski.madde} → {f.yeni.madde} olarak güncellenmeli.")
    if not parcalar:
        return None
    return GuncellemeOnerisi(hedef, tur, madde, " ".join(parcalar))


def guncelleme_onerileri(fark: RevizyonFarki, dokuman: KabulDokumani) -> list[GuncellemeOnerisi]:
    """Eski revizyondan üretilmiş kabul dokümanını yeni revizyona taşımak için öneriler."""
    if dokuman.standart.revizyon != fark.eski_revizyon:
        raise ValueError(
            f"kabul dokümanı {dokuman.standart.revizyon} revizyonundan; karşılaştırmanın eski revizyonu "
            f"{fark.eski_revizyon} olmalı"
        )
    eski_madde = {f.eski.madde: f for f in fark.sart_farklari if f.eski is not None}
    oneriler: list[GuncellemeOnerisi] = []

    def sart_ekle(hedef: str, madde: str | None) -> None:
        f = eski_madde.get(madde) if madde else None
        if f is not None:
            o = _sart_onerisi(hedef, f, fark.yeni_etiket)
            if o and o not in oneriler:
                oneriler.append(o)

    tablo_farki = {_test_anahtari(t.ad): t for t in fark.test_farklari}
    eski_tablo_maddesi: dict[str, list[TestFarki]] = {}
    for tf in fark.test_farklari:
        if tf.eski is not None:
            eski_tablo_maddesi.setdefault(tf.eski.sart_maddesi, []).append(tf)
    for t in dokuman.testler:
        hedef = f"test:{t.id}"
        tf = tablo_farki.get(_test_anahtari(t.test_adi))
        if tf is None and len(eski_tablo_maddesi.get(t.kaynak.madde, [])) == 1:
            tf = eski_tablo_maddesi[t.kaynak.madde][0]  # ad farklı yazılmış: şart maddesiyle bağla
        if not (tf and tf.tur == "kaldirildi"):
            sart_ekle(hedef, t.kaynak.madde)
            sart_ekle(hedef, t.metot_kaynagi.madde if t.metot_kaynagi else None)
        if tf and tf.tur == "kaldirildi":
            oneriler.append(GuncellemeOnerisi(
                hedef, "kaldir", t.kaynak.madde,
                f"'{t.test_adi}' testi {fark.yeni_etiket} test tablosunda yok; satır çıkarılmalı."))
        elif tf and tf.tur == "degisti":
            alanlar = ", ".join(tf.degisen_alanlar)
            ayrinti = "; ".join(
                f"{a}: {getattr(tf.eski, a) or '—'} → {getattr(tf.yeni, a) or '—'}" for a in tf.degisen_alanlar)
            oneriler.append(GuncellemeOnerisi(
                hedef, "guncelle", t.kaynak.madde,
                f"'{t.test_adi}' testinin {alanlar} bilgisi değişti ({ayrinti})."))

    for r in dokuman.raf_omurleri:
        sart_ekle(f"raf_omru:{r.kap_turu}" if r.kap_turu else "raf_omru", r.kaynak.madde)
    for k in dokuman.kosullar:
        sart_ekle(f"kosul:{k.ad}", k.kaynak.madde)
    for n in dokuman.numune_hazirlama:
        sart_ekle(f"numune:{n.id}", n.kaynak.madde)

    yeni_test_maddeleri = set()
    for tf in fark.test_farklari:
        if tf.tur == "eklendi":
            yeni_test_maddeleri.add(tf.yeni.sart_maddesi)
            oneriler.append(GuncellemeOnerisi(
                f"yeni_test:{tf.ad}", "ekle", tf.yeni.sart_maddesi,
                f"'{tf.ad}' testi {fark.yeni_etiket} test tablosuna eklendi (şart {tf.yeni.sart_maddesi}"
                + (f", test {tf.yeni.test_maddesi}" if tf.yeni.test_maddesi else "")
                + "); kabul dokümanına eklenmeli."))
    for f in fark.sart_farklari:
        if f.tur == "eklendi" and f.yeni.bolum == 3 and f.madde not in yeni_test_maddeleri:
            oneriler.append(GuncellemeOnerisi(
                f"yeni_sart:{f.madde}", "gozden_gecir", f.madde,
                f"Yeni şart {f.madde} {f.baslik}: kabul dokümanına eklenip eklenmeyeceği incelenmeli."))

    eski_haric, yeni_haric = set(fark.eski_kabul_disi), set(fark.yeni_kabul_disi)
    for ad in sorted(yeni_haric - eski_haric):
        oneriler.append(GuncellemeOnerisi(
            f"kabul_kapsami:{ad}", "gozden_gecir", "4.3",
            f"'{ad}' {fark.yeni_etiket} revizyonunda kabul muayenesi dışında; test türü 'yeterlilik' olmalı."))
    kaldirilan_testler = {_test_anahtari(t.ad) for t in fark.test_farklari if t.tur == "kaldirildi"}
    for ad in sorted(eski_haric - yeni_haric):
        if _test_anahtari(ad) in kaldirilan_testler:
            continue  # test tamamen kaldırıldı; kaldırma önerisi yeterli
        oneriler.append(GuncellemeOnerisi(
            f"kabul_kapsami:{ad}", "gozden_gecir", "4.3",
            f"'{ad}' {fark.yeni_etiket} revizyonunda artık kabul muayenesinde; test türüne 'kabul' eklenmeli."))
    return oneriler


# --- Markdown raporu -----------------------------------------------------------------------------

_TUR_ADI = {"eklendi": "Eklendi", "kaldirildi": "Kaldırıldı", "degisti": "Değişti"}
_ONEM_ADI = {"sayisal": "sayısal", "metin": "metin", "bicimsel": "biçimsel", None: "yalnız numara/başlık"}


def _hucre_md(metin: str, sinir: int = 220) -> str:
    metin = metin.replace("|", "\\|").replace("\n", " ")
    return metin if len(metin) <= sinir else metin[: sinir - 1] + "…"


def _degisiklik_md(f: SartFarki) -> str:
    if f.tur == "eklendi":
        return _hucre_md(f.yeni.metin or "(başlık)")
    if f.tur == "kaldirildi":
        return _hucre_md(f.eski.metin or "(başlık)")
    parcalar = []
    for d in f.degisiklikler[:4]:
        if d.eski and d.yeni:
            parcalar.append(f"~~{_hucre_md(d.eski, 80)}~~ → **{_hucre_md(d.yeni, 80)}**")
        elif d.eski:
            parcalar.append(f"~~{_hucre_md(d.eski, 100)}~~")
        else:
            parcalar.append(f"**+ {_hucre_md(d.yeni, 100)}**")
    if len(f.degisiklikler) > 4:
        parcalar.append(f"(+{len(f.degisiklikler) - 4} değişiklik daha)")
    if f.baslik_degisti:
        parcalar.insert(0, f"başlık: {_hucre_md(f.eski.baslik, 60)} → {_hucre_md(f.yeni.baslik, 60)}")
    return "<br>".join(parcalar) or "—"


def _madde_md(f: SartFarki) -> str:
    if f.yeniden_numaralandi:
        return f"{f.eski.madde} → {f.yeni.madde}"
    return f.madde


def markdown_raporu(fark: RevizyonFarki, oneriler: list[GuncellemeOnerisi] | None = None) -> str:
    oz = fark.ozet()
    satirlar = [
        f"# {fark.eski_etiket} → {fark.yeni_etiket} revizyon farkları",
        "",
        "Bu rapor kurallarla üretilmiş bir taslaktır; değişikliklerin kabul dokümanına "
        "etkisini kalite mühendisi onaylar. Standart, değişiklikleri kenar işaretiyle "
        "göstermediğini belirttiği için karşılaştırma bütün metin üzerinden yapılmıştır.",
        "",
        "## Özet",
        "",
        "| | Adet |",
        "|---|---|",
        f"| Eklenen madde | {oz['eklenen_sart']} |",
        f"| Kaldırılan madde | {oz['kaldirilan_sart']} |",
        f"| İçeriği değişen madde | {oz['degisen_sart']} (sayısal değeri değişen: {oz['sayisal_degisen_sart']}) |",
        f"| Numarası değişen madde | {oz['yeniden_numaralanan_sart']} |",
        f"| Aynı kalan madde | {oz['ayni_kalan_sart']} |",
        f"| Test tablosu: eklenen / kaldırılan / değişen test | "
        f"{oz['eklenen_test']} / {oz['kaldirilan_test']} / {oz['degisen_test']} |",
        "",
    ]

    satirlar += ["## Test tablosu", ""]
    if fark.test_farklari:
        satirlar += ["| Test | Fark | Eski | Yeni |", "|---|---|---|---|"]

        def tsat(t: TestSatiri | None) -> str:
            if t is None:
                return "—"
            return _hucre_md(f"şart {t.sart_maddesi}, test {t.test_maddesi or '—'}, metot {t.metot or '—'}")

        for t in fark.test_farklari:
            tur = _TUR_ADI[t.tur] + (f" ({', '.join(t.degisen_alanlar)})" if t.degisen_alanlar else "")
            satirlar.append(f"| {_hucre_md(t.ad)} | {tur} | {tsat(t.eski)} | {tsat(t.yeni)} |")
    else:
        satirlar.append("Test tablosunda fark yok.")
    satirlar.append("")

    satirlar += [
        "## Kabul muayenesi kapsamı",
        "",
        f"- {fark.eski_etiket} kabul dışı: {', '.join(fark.eski_kabul_disi) or '—'}",
        f"- {fark.yeni_etiket} kabul dışı: {', '.join(fark.yeni_kabul_disi) or '—'}",
        "",
    ]

    icerik = [f for f in fark.sart_farklari if f.onem != "bicimsel"]
    for bolumler, baslik in (((3, 4), "Şart ve doğrulama maddeleri (bölüm 3–4)"),
                             ((1, 2, 5, 6), "Diğer bölümler (1, 2, 5, 6)")):
        secilen = [f for f in icerik if (f.yeni or f.eski).bolum in bolumler]
        satirlar += [f"## {baslik}", ""]
        if not secilen:
            satirlar += ["Fark yok.", ""]
            continue
        satirlar += ["| Madde | Başlık | Fark | Önem | Değerler (eski → yeni) | Değişiklik |",
                     "|---|---|---|---|---|---|"]
        for f in secilen:
            onem = _ONEM_ADI[f.onem] if f.tur == "degisti" else "—"
            degerler = f"{', '.join(f.eski_degerler) or '—'} → {', '.join(f.yeni_degerler) or '—'}"
            if not (f.eski_degerler or f.yeni_degerler):
                degerler = "—"
            satirlar.append(
                f"| {_madde_md(f)} | {_hucre_md(f.baslik, 60)} | {_TUR_ADI[f.tur]} | {onem} | "
                f"{_hucre_md(degerler, 120)} | {_degisiklik_md(f)} |"
            )
        satirlar.append("")

    bicimsel = [f for f in fark.sart_farklari if f.onem == "bicimsel"]
    if bicimsel:
        satirlar += ["## Yalnız yazım farkı olan maddeler", "",
                     ", ".join(f"{_madde_md(f)} {f.baslik}" for f in bicimsel), ""]

    if oneriler is not None:
        satirlar += ["## Kabul dokümanı güncelleme önerileri", ""]
        if oneriler:
            satirlar += ["| Hedef | Öneri türü | Madde | Öneri |", "|---|---|---|---|"]
            for o in oneriler:
                satirlar.append(f"| {_hucre_md(o.hedef, 60)} | {o.tur} | {o.madde} | {_hucre_md(o.oneri, 400)} |")
        else:
            satirlar.append("Kabul dokümanını etkileyen fark bulunmadı.")
        satirlar.append("")
    return "\n".join(satirlar)
