"""Karar motoru: tedarikçi sertifikasını kabul dokümanıyla karşılaştırır.

Her kabul testi için "uygun / uygun_degil / insan_incelemeli" kararı verir ve
dayandığı standart maddesini gösterir. Bütün adımlar kesin kurallardır; dil
modeli kullanılmaz (CLAUDE.md, kural 1):

1. Atıf: sertifikadaki "MIL-PRF-23377K Type I Class C2" metninden belge no,
   revizyon, tip ve sınıf çıkarılır; revizyon kabul dokümanıyla karşılaştırılır.
2. Aranacak testler: yalnız kabul testleri (yeterlilik testleri aranmaz) ve
   yalnız sertifikadaki tip/sınıfa uygulananlar.
3. Eşleştirme: sertifikadaki test adı normalleştirilir; kabul dokümanındaki
   ad, kimlik ve `ESANLAMLILAR` tablosuyla birebir; olmazsa kaynak tablo adıyla
   (ör. "Lead and cadmium content"; birden çok teste uyarsa belirsiz); o da
   olmazsa kelime benzerliğiyle (tek ve açık bir en iyi aday varsa) eşleştirilir.
4. Sonuç: "320", "1,5", "<1", "5A", "Conforms", "Fail" gibi metinler sayı
   aralığına ya da geçti/kaldı sonucuna çevrilir.
5. Birim: pint ile hedef birime çevrilir ("mil" uzunluk olarak, bkz.
   `birimler.pint_ifadesi`). Çevrilemeyen birim insana bırakılır.
6. Karşılaştırma: okunan değer aralığı sınırın tamamen içindeyse uygun,
   tamamen dışındaysa uygun değil, ikisi de değilse ("<8 saat" ile "en çok 5
   saat") insan incelemeli. Yuvarlama yapılmaz: standarttaki ve sertifikadaki
   değerler olduğu gibi karşılaştırılır. Okunan (çevrilmiş) değerin bir ucu bir
   sınıra `SINIR_YAKINLIK_BAGIL` / `SINIR_YAKINLIK_MUTLAK` bandında yakınsa
   karar insan incelemelidir ("sınıra çok yakın"); istisna: birim dönüşümü
   yoksa, değer sınıra tam eşitse ve sertifikadaki sayı metni float'a kayıpsız
   sığıyorsa dahil/hariç kuralı karar verir (docs/sinir_yakinligi.md). Yönü belirsiz şartlarda
   ("en az" mı "tam" mı belli değil, `Sinir.yon == "belirsiz"`) karşılaştırma
   yapılmaz; karar insan incelemelidir.
7. Sonuç kaynağı: kabul dokümanında sonucu iç laboratuvardan gelen testler
   (`sonuc_kaynagi == "ic_laboratuvar"`) CoC'de aranmaz. Bu sürümde iç
   laboratuvar sonucu henüz girilemediği için bu testler insan incelemelidir
   (parti bekletilir; docs/mimari.md madde 5).

8. Tip/sınıf: katalogdan gelirse (`kontrol_et(..., tip=, sinif=)`) şartların
   uygulanabilirliği ona göre seçilir; sertifikadaki atıf yalnız çelişki
   denetimi için okunur (çelişirse `tip_sinif` satırı insan incelemelidir).
   Katalog yoksa eski davranış: tip/sınıf sertifikadaki atıftan okunur.
   Kabul dokümanı tip/sınıf listesi tanımlıyorsa katalogdaki kod tanımlı ve
   listede olmalıdır; değilse insan incelemeli (atfa düşülmez).
9. Parti kuralı (`parti_karari`): bir satır uygun değilse parti uygun değil
   (red); kabul yalnız liste boş değilse ve her karar "uygun"sa; geri kalan
   her durum (insan incelemeli, boş liste, tanınmayan değer) inceleme.
   Uygulanan kabul testi yoksa belge kabul edilmez.
10. Geçti/kaldı sonucu beyaz listeyle okunur: açık kaldı sözcükleri ("Fail",
   "Non-conforming", "Uygun değil") kaldı; normalleştirilmiş metin bilinen bir
   olumlu ifadeye ("Pass", "Conforms", "Complies", "OK", "Uygun", "Geçti",
   "Kabul", "Satisfactory", "Conforms to specification", "Meets requirement(s)"...) birebir
   eşitse geçti; geri kalan her metin ("Not passed", "Pass*", "OK per report")
   belirsizdir ve insana gider. Bilinçli seçim: gerçek CoA'larda görülen
   "Conforms to structure" ve "Conforms to reference" da listede değildir; neye
   uyduğu belgeden doğrulanmalıdır, bu yüzden insana gider.

Emin olunmayan her durumda karar insana bırakılır; böylece belirsizlik yanlış
kabule dönüşmez.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from malzeme_kabul.kural.birimler import birimi_coz, kayit
from malzeme_kabul.sozlesme.sema import KabulDokumani, Sinir, TestSarti
from malzeme_kabul.sozlesme.sertifika import Sertifika

Karar = Literal["uygun", "uygun_degil", "insan_incelemeli"]
BelgeKarari = Literal["kabul", "red", "inceleme"]
# Politika ayarları yalnız kısıtlayıcı olabilir: belge sorunu hiçbir zaman "uygun" sayılmaz (K8).
KisitlayiciKarar = Literal["uygun_degil", "insan_incelemeli"]


class KararAyarlari(BaseModel):
    """Politikaya bağlı kararlar. Varsayılanlar belge sorunlarını insana bırakır."""

    model_config = ConfigDict(extra="forbid")

    eksik_test: KisitlayiciKarar = "insan_incelemeli"
    yanlis_revizyon: KisitlayiciKarar = "insan_incelemeli"


class KararSatiri(BaseModel):
    """Bir kabul testi (ya da revizyon kontrolü) için verilen karar."""

    model_config = ConfigDict(extra="forbid")

    test_id: str
    test_adi: str
    karar: Karar
    gerekce: str
    madde: str | None = None
    sayfa: int | None = None  # standarttaki şartın PDF sayfası
    sertifikadaki_ad: str | None = None
    okunan_sonuc: str | None = None
    okunan_birim: str | None = None
    cevrilmis_deger: float | None = None
    hedef_birim: str | None = None


class KontrolSonucu(BaseModel):
    """Bir sertifikanın kontrol sonucu."""

    model_config = ConfigDict(extra="forbid")

    sertifika_no: str
    belge_karari: BelgeKarari
    revizyon: KararSatiri
    satirlar: list[KararSatiri]
    tip_sinif: KararSatiri | None = None
    eslesmeyen_satirlar: list[str] = []


# --- metin normalleştirme -------------------------------------------------

_TR = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g"})


def _normal(metin: str) -> str:
    """Küçük harf, aksansız, yalnız harf/rakam ve tek boşluk."""
    metin = metin.translate(_TR).casefold()
    metin = "".join(c for c in unicodedata.normalize("NFKD", metin) if not unicodedata.combining(c))
    metin = re.sub(r"[^a-z0-9]+", " ", metin)
    return " ".join(metin.split())


# --- atıf -----------------------------------------------------------------


@dataclass(frozen=True)
class Atif:
    belge_no: str | None
    revizyon: str | None
    tip: str | None
    sinif: str | None


# Revizyon harfi numaraya bitişik ya da tek boşlukla yazılabilir ("23377K", "23377 K,").
_BELGE = re.compile(r"\b(MIL)[-\s]?(PRF|DTL|C|P|S)[-\s]?(\d+)(?:\s?([A-Z]))?(?![A-Z0-9])")
_REV = re.compile(r"\bREV(?:IZYON|ISION)?\.?\s*:?\s*([A-Z])(?![A-Z0-9])")
_TIP = re.compile(r"\b(?:TYPE|TIP)\s*:?\s*(II|I|2|1)(?![A-Z0-9])")
_SINIF = re.compile(r"\b(?:CLASS|SINIF)\s*:?\s*(C1|C2|N)(?![A-Z0-9])")
_ROMEN = {"1": "I", "2": "II"}


def atfi_coz(metin: str) -> Atif:
    """Sertifikadaki standart atfından belge no, revizyon, tip ve sınıfı çıkarır."""
    buyuk = metin.translate(_TR).upper() if metin else ""
    buyuk = "".join(c for c in unicodedata.normalize("NFKD", buyuk) if not unicodedata.combining(c))
    belge_no = revizyon = tip = sinif = None
    m = _BELGE.search(buyuk)
    if m:
        belge_no = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        revizyon = m.group(4)
        if revizyon is None:
            r = _REV.search(buyuk, m.end())
            revizyon = r.group(1) if r else None
    t = _TIP.search(buyuk)
    if t:
        tip = _ROMEN.get(t.group(1), t.group(1))
    s = _SINIF.search(buyuk)
    if s:
        sinif = s.group(1)
    return Atif(belge_no, revizyon, tip, sinif)


# --- uygulanabilirlik -----------------------------------------------------

_UYG = re.compile(r"^\s*(type|class)\s+(\S+)\s*$", re.IGNORECASE)


def uygulanir_mi(uygulanabilirlik: list[str], tip: str | None, sinif: str | None) -> bool | None:
    """Test sertifikadaki tip/sınıfa uygulanır mı? Bilinemiyorsa None."""
    if not uygulanabilirlik:
        return True
    gruplar: dict[str, set[str]] = {}
    for kayit_ in uygulanabilirlik:
        m = _UYG.match(kayit_)
        if not m:
            return None
        deger = m.group(2).upper()
        gruplar.setdefault(m.group(1).lower(), set()).add(_ROMEN.get(deger, deger))
    sertifika = {"type": tip, "class": sinif}
    bilinmeyen = False
    for kategori, izinli in gruplar.items():
        deger = sertifika[kategori]
        if deger is None:
            bilinmeyen = True
        elif deger not in izinli:
            return False
    return None if bilinmeyen else True


# --- sonuç ayrıştırma -----------------------------------------------------


@dataclass(frozen=True)
class Sonuc:
    """Sertifikadaki sonucun ayrıştırılmış hali.

    tur "sayi" ise değer [alt, ust] aralığıdır (tek değerde alt == ust);
    "<1" gibi ifadelerde bir uç açıktır. `birim_ek`, sonuç hücresine yazılmış
    birimdir ("4 h"). `sayi_metni`, sayının sertifikadaki yazılışıdır ("<"/">"
    öneki ve birim olmadan; "ND (<0.5 ppm)" için "0.5"); float'a kayıpsız
    sığıp sığmadığı tam eşitlik istisnasında denetlenir.
    """

    tur: Literal["sayi", "gecti", "kaldi", "belirsiz"]
    alt: float | None = None
    ust: float | None = None
    alt_dahil: bool = True
    ust_dahil: bool = True
    birim_ek: str | None = None
    sayi_metni: str | None = None


_SAYI = re.compile(
    r"^(?P<op><=|>=|≤|≥|<|>)?\s*(?P<sayi>[+-]?\d+(?:[.,]\d+)?)\s*(?P<ek>[A-Za-zµμ°%/][A-Za-z0-9µμ°%/.\- ]*)?$"
)
_DERECE_HARFI = re.compile(r"^[A-B]$")  # ASTM D3359 yapışma derecesi: 4A, 5B
_KALDI = ("does not conform", "not conform", "non conform", "nonconform", "uygun degil", "fail", "failed", "fails",
          "kaldi", "reject", "rejected", "reddedildi")
# Beyaz liste (K1): sonuç yalnız bu ifadelerden birine birebir eşitse geçti sayılır.
# Karşılaştırma `_ifade` ile normalleştirilmiş metinde yapılır (büyük/küçük harf, boşluk,
# Türkçe harfler); noktalama korunur, "Pass*" ya da "OK per report" listede değildir.
_GECTI = frozenset({
    "pass", "passed", "passes", "passes test",
    "conforms", "conforms to specification",
    "complies", "ok", "uygun", "gecti", "kabul", "meets requirements",
    "satisfactory", "meets requirement",
})


_ALGILANMADI = re.compile(r"^(nd|n d|not detected|none detected|tespit edilmedi|saptanmadi|bulunmadi)\b")
_ALGILAMA_SINIRI = re.compile(r"(<=|≤|<)\s*[+-]?\d+(?:[.,]\d+)?\s*(?:[A-Za-zµμ°%/][A-Za-z0-9µμ°%/.]*)?")


def _ifade(metin: str) -> str:
    """Beyaz liste karşılaştırması için: küçük harf, aksansız, tek boşluk; noktalama korunur."""
    metin = metin.translate(_TR).casefold()
    metin = "".join(c for c in unicodedata.normalize("NFKD", metin) if not unicodedata.combining(c))
    return " ".join(metin.split())


def sonucu_ayristir(metin: str) -> Sonuc:
    """Sonuç hücresini sayı aralığına ya da geçti/kaldı sonucuna çevirir.

    "ND" (algılanmadı) ancak algılama sınırıyla birlikte verilmişse ("ND
    (<0.5 ppm)") o sınır kullanılır; sınırsız "ND" belirsizdir.
    """
    ham = (metin or "").strip()
    if _ALGILANMADI.match(_normal(ham)):
        m = _ALGILAMA_SINIRI.search(ham)
        return sonucu_ayristir(m.group(0)) if m else Sonuc("belirsiz")
    m = _SAYI.match(ham)
    if m:
        sayi_metni = m.group("sayi")
        sayi = float(sayi_metni.replace(",", "."))
        ek = (m.group("ek") or "").strip() or None
        if ek and _DERECE_HARFI.match(ek):
            ek = None
        op = m.group("op")
        if op in ("<", "≤", "<="):
            return Sonuc("sayi", None, sayi, True, op != "<", ek, sayi_metni)
        if op in (">", "≥", ">="):
            return Sonuc("sayi", sayi, None, op != ">", True, ek, sayi_metni)
        return Sonuc("sayi", sayi, sayi, True, True, ek, sayi_metni)
    normal = _normal(ham)
    if any(re.search(rf"\b{k}", normal) for k in _KALDI):
        return Sonuc("kaldi")
    if _ifade(ham) in _GECTI:
        return Sonuc("gecti")
    return Sonuc("belirsiz")


# --- birim dönüşümü -------------------------------------------------------

BIRIM_ESANLAMLILARI = {
    "um": "µm", "μm": "µm", "micron": "µm", "microns": "µm", "mikron": "µm",
    "min": "minute", "mins": "minute", "dk": "minute", "dak": "minute", "dakika": "minute",
    "h": "hour", "hr": "hour", "hrs": "hour", "hours": "hour", "sa": "hour", "saat": "hour",
    "gün": "day", "gun": "day", "days": "day",
    "s": "second", "sec": "second", "secs": "second", "seconds": "second", "sn": "second", "san": "second",
    "saniye": "second",
    "g/l": "g/L", "gr/l": "g/L", "lbs/gal": "lb/gal",
    "%": "percent", "wt%": "percent", "% wt": "percent",
    "°c": "degC", "ºc": "degC", "°f": "degF", "ºf": "degF",
}


def _pint_birimi(birim: str) -> str:
    anahtar = birim.strip()
    return BIRIM_ESANLAMLILARI.get(anahtar.lower(), BIRIM_ESANLAMLILARI.get(anahtar, anahtar))


# Sınıra yakınlık bandı (docs/sinir_yakinligi.md). Değerler yuvarlanmadan
# karşılaştırılır; sınıra bu kadar yakın değerler insana gider. 1e-6 bağıl
# tolerans pint dönüşümündeki kayan nokta hatasının (~1e-15) çok üstünde,
# gerçek CoC ölçüm çözünürlüğünün çok altındadır; yalnız "sınırda" sayılabilecek
# değerleri yakalar. Mutlak tolerans (sınır birimi cinsinden) sıfır sınır içindir.
# Eşik proje sahibinin onayına açık bir karardır.
SINIR_YAKINLIK_BAGIL = 1e-6
SINIR_YAKINLIK_MUTLAK = 1e-12


def birimi_cevir(deger: float, kaynak: str | None, hedef: str | None) -> float:
    """Değeri kaynak birimden hedef birime pint ile çevirir; olmazsa ValueError."""
    if not kaynak and not hedef:
        return deger
    if not kaynak or not hedef:
        raise ValueError(f"birim eksik: {kaynak!r} -> {hedef!r}")
    try:
        q = kayit().Quantity(deger, birimi_coz(_pint_birimi(kaynak)))
        return q.to(birimi_coz(_pint_birimi(hedef))).magnitude
    except Exception as hata:  # pint: tanımsız birim, boyut uyumsuzluğu, sözdizimi
        raise ValueError(f"birim çevrilemedi: {kaynak!r} -> {hedef!r}") from hata


# --- test eşleştirme ------------------------------------------------------

# Standartlardaki ve sertifikalardaki yaygın test adları (İngilizce ve Türkçe).
# Kabul dokümanındaki test kimliğine göre yazılmıştır; sertifika üreticisinden
# önce, standart terminolojisinden hazırlandı.
ESANLAMLILAR: dict[str, list[str]] = {
    # "Lead and cadmium content" tablo adıdır (kaynak_tablo_adi); burada yalnız kadmiyum adları durur.
    "lead_and_cadmium_content": ["cadmium content", "cadmium", "kadmiyum", "kadmiyum icerigi"],
    "chromium_content_class_n_only": ["hexavalent chromium", "chromium", "cr vi", "krom", "krom icerigi"],
    "voc_solvent_content": [
        "voc", "voc content", "volatile organic compound content", "volatile organic compounds",
        "voc icerigi", "ucucu organik bilesik", "ucucu organik bilesik icerigi",
    ],
    "fineness_of_grind": ["grind", "hegman", "fineness of dispersion", "dispersion", "ogutme inceligi", "inceltik"],
    "condition_in_container": ["condition in can", "container condition", "kap ici durum", "kaptaki durum"],
    "odor": ["odour", "koku"],
    "viscosity": ["initial viscosity", "viskozite", "baslangic viskozitesi"],
    "pot_life": ["pot life viscosity", "kap omru", "kullanim omru"],
    "surface_appearance": ["appearance", "film appearance", "gorunum", "yuzey gorunumu"],
    "drying_time": ["dry time", "tack free", "tack free time", "set to touch", "kuruma suresi", "kuruma"],
    "lifting": ["lifting resistance", "kalkma"],
    "adhesion": ["wet tape adhesion", "tape adhesion", "yapisma", "yapisma direnci"],
    "flexibility": ["elongation", "impact flexibility", "ge impact", "esneklik", "uzama"],
    "infrared_reflectance_type_ii_only": ["ir reflectance", "total reflectance", "kizilotesi yansima"],
    "water_resistance": ["water immersion", "water immersion resistance", "su direnci"],
    "solvent_resistance_cure": ["solvent resistance", "solvent rub", "mek rub", "mek resistance", "cozucu direnci"],
    "fluid_resistance": ["hydraulic fluid resistance", "fluid immersion", "sivi direnci"],
    "mixing_and_dilution": ["mixing", "dilution", "mixing and thinning", "karistirma", "karistirma ve inceltme"],
    "application": ["dry film thickness", "dft", "film thickness", "uygulama", "kuru film kalinligi", "sprayability"],
    "color_type_i": ["color", "colour", "renk"],
    "color_type_ii": ["color", "colour", "renk"],
}

_EK_TEMIZLE = re.compile(r"\s*\([^)]*\)")  # "(class N only)", "(Hegman)"
_TIP_EKI = re.compile(r"\s+(type|class)\s+\S+(\s+only)?$")  # "color type i", "... type ii only"
_DOLGU = {"of", "the", "and", "test", "a", "ve", "testi"}


def _taban_adlar(test: TestSarti) -> set[str]:
    adlar = {test.test_adi}
    kimlik = test.id.replace("_", " ")
    if not (test.kaynak_tablo_adi and _normal(kimlik).startswith(_normal(test.kaynak_tablo_adi))):
        adlar.add(kimlik)  # tablo adından türeyen kimlik tablo adı gibi ikinci sırada kalır
    adlar |= {_EK_TEMIZLE.sub("", a) for a in list(adlar)}
    normal = {_normal(a) for a in adlar}
    normal |= {_TIP_EKI.sub("", a) for a in list(normal)}
    normal |= {_normal(a) for a in ESANLAMLILAR.get(test.id, [])}
    return {a for a in normal if a}


def _tablo_adlari(test: TestSarti) -> set[str]:
    """Test tablosundaki satır adı (test adından farklıysa); ikinci sırada denenir."""
    if not test.kaynak_tablo_adi:
        return set()
    return {a for a in {_normal(test.kaynak_tablo_adi), _normal(_EK_TEMIZLE.sub("", test.kaynak_tablo_adi))} if a}


def _kelimeler(metin: str) -> set[str]:
    return {k for k in metin.split() if k not in _DOLGU}


def eslestir(ad: str, testler: list[TestSarti], esik: float = 0.6) -> str | None:
    """Sertifikadaki test adını kabul dokümanındaki bir teste eşler; yoksa None."""
    adaylar = {_normal(ad), _normal(_EK_TEMIZLE.sub("", ad))} - {""}
    # Önce testin kendi adı ve eş anlamlıları, sonra kaynak tablo adı. Aynı tablo
    # satırından gelen iki test (kadmiyum, kurşun) tablo adıyla belirsiz kalır.
    for ad_kumesi in (_taban_adlar, _tablo_adlari):
        birebir = [t.id for t in testler if adaylar & ad_kumesi(t)]
        if len(birebir) == 1:
            return birebir[0]
        if len(birebir) > 1:
            return None  # belirsiz
    puanlar: list[tuple[float, str]] = []
    for t in testler:
        en_iyi = 0.0
        for aday in adaylar:
            k1 = _kelimeler(aday)
            for taban in _taban_adlar(t):
                k2 = _kelimeler(taban)
                if k1 and k2:
                    en_iyi = max(en_iyi, len(k1 & k2) / len(k1 | k2))
        puanlar.append((en_iyi, t.id))
    puanlar.sort(reverse=True)
    if not puanlar or puanlar[0][0] < esik:
        return None
    if len(puanlar) > 1 and puanlar[1][0] == puanlar[0][0]:
        return None
    return puanlar[0][1]


# --- karşılaştırma --------------------------------------------------------


def _icinde_mi(s: Sonuc, sinir: Sinir) -> Karar:
    """Okunan aralık sınırın tamamen içinde mi, tamamen dışında mı?"""
    alt_tamam = sinir.alt is None or (
        s.alt is not None and (s.alt > sinir.alt or (s.alt == sinir.alt and (sinir.alt_dahil or not s.alt_dahil)))
    )
    ust_tamam = sinir.ust is None or (
        s.ust is not None and (s.ust < sinir.ust or (s.ust == sinir.ust and (sinir.ust_dahil or not s.ust_dahil)))
    )
    if alt_tamam and ust_tamam:
        return "uygun"
    ustunde = sinir.ust is not None and s.alt is not None and (
        s.alt > sinir.ust or (s.alt == sinir.ust and not (sinir.ust_dahil and s.alt_dahil))
    )
    altinda = sinir.alt is not None and s.ust is not None and (
        s.ust < sinir.alt or (s.ust == sinir.alt and not (sinir.alt_dahil and s.ust_dahil))
    )
    if ustunde or altinda:
        return "uygun_degil"
    return "insan_incelemeli"


def _sinir_metni(sinir: Sinir) -> str:
    b = f" {sinir.birim}" if sinir.birim else ""
    if sinir.alt is not None and sinir.ust is not None:
        return f"{sinir.alt:g}–{sinir.ust:g}{b}"
    if sinir.ust is not None:
        return f"en çok {sinir.ust:g}{b}" + ("" if sinir.ust_dahil else " (hariç)")
    return f"en az {sinir.alt:g}{b}" + ("" if sinir.alt_dahil else " (hariç)")


def _degerlendir(test: TestSarti, sonuc_metni: str, birim: str | None) -> tuple[Karar, str, float | None]:
    s = sonucu_ayristir(sonuc_metni)
    sinir = test.sinir
    if sinir.kriter_turu != "sayisal":
        if s.tur == "gecti":
            return "uygun", "sertifika şartı sağladığını belirtiyor", None
        if s.tur == "kaldi":
            return "uygun_degil", "sertifika şartı sağlamadığını belirtiyor", None
        return "insan_incelemeli", f"sonuç geçti/kaldı olarak yorumlanamadı: {sonuc_metni!r}", None

    if sinir.yon_belirsiz:
        return "insan_incelemeli", f"şartın yönü belirsiz ('en az' mı 'tam' mı belli değil): {sinir.orijinal_metin!r}", None
    if s.tur != "sayi":
        return "insan_incelemeli", f"sayısal şart için sayı okunamadı: {sonuc_metni!r}", None
    kaynak_birim = birim or s.birim_ek
    if birim and s.birim_ek and _pint_birimi(birim) != _pint_birimi(s.birim_ek):
        return "insan_incelemeli", f"sonuç ve birim hücreleri çelişiyor: {s.birim_ek!r} / {birim!r}", None
    try:
        alt = None if s.alt is None else birimi_cevir(s.alt, kaynak_birim, sinir.birim)
        ust = None if s.ust is None else birimi_cevir(s.ust, kaynak_birim, sinir.birim)
    except ValueError:
        return "insan_incelemeli", f"birim {kaynak_birim!r} şarttaki {sinir.birim!r} birimine çevrilemedi", None
    deger = alt if alt is not None else ust
    okunan = f"{sonuc_metni} {kaynak_birim or ''}".strip()
    donusum_yok = (not kaynak_birim and not sinir.birim) or (
        bool(kaynak_birim) and bool(sinir.birim) and _pint_birimi(kaynak_birim) == _pint_birimi(sinir.birim)
    )
    # Tam eşitlik istisnası yalnız sertifikadaki sayı float'a kayıpsız sığıyorsa
    # geçerlidir ("1.00000000000000001" float'ta 1.0 olur; gerçek değer sınırın üstünde).
    kayipsiz = s.sayi_metni is not None and (
        Decimal(s.sayi_metni.replace(",", ".")) == Decimal(repr(s.alt if s.alt is not None else s.ust))
    )
    for e in (alt, ust):
        if e is None:
            continue
        for b in (sinir.alt, sinir.ust):
            if b is None or (donusum_yok and kayipsiz and e == b):
                continue
            if math.isclose(e, b, rel_tol=SINIR_YAKINLIK_BAGIL, abs_tol=SINIR_YAKINLIK_MUTLAK):
                hedef = f" {sinir.birim}" if sinir.birim else ""
                return (
                    "insan_incelemeli",
                    f"{okunan} (= {e!r}{hedef}) sınıra çok yakın (şart {_sinir_metni(sinir)}, "
                    f"sınır {b!r}); yuvarlanmadan karar verilemez",
                    deger,
                )
    cevrilmis = Sonuc("sayi", alt, ust, s.alt_dahil, s.ust_dahil)
    karar = _icinde_mi(cevrilmis, sinir)
    if kaynak_birim and sinir.birim and _pint_birimi(kaynak_birim) != _pint_birimi(sinir.birim):
        okunan += f" (= {deger:g} {sinir.birim})"
    gerekce = {
        "uygun": f"{okunan}, şart {_sinir_metni(sinir)} içinde",
        "uygun_degil": f"{okunan}, şart {_sinir_metni(sinir)} dışında",
        "insan_incelemeli": f"{okunan} ile şart {_sinir_metni(sinir)} karşılaştırılamıyor",
    }[karar]
    return karar, gerekce, deger


# --- ana fonksiyon --------------------------------------------------------


def parti_karari(kararlar: list[Karar]) -> BelgeKarari:
    """Parti kuralı: bir uygun değil → red; yoksa kabul yalnız liste boş değilse ve hepsi "uygun"sa.

    Boş liste, insan incelemeli ya da tanınmayan bir değer inceleme verir (K6).
    """
    if "uygun_degil" in kararlar:
        return "red"
    if kararlar and all(k == "uygun" for k in kararlar):
        return "kabul"
    return "inceleme"


def _revizyon_kontrolu(dokuman: KabulDokumani, atif: Atif, ayar: KararAyarlari) -> KararSatiri:
    std = dokuman.standart
    beklenen = f"{std.belge_no}{std.revizyon}"

    def satir(karar: Karar, gerekce: str) -> KararSatiri:
        return KararSatiri(test_id="revizyon", test_adi="Standart ve revizyon atfı", karar=karar, gerekce=gerekce, madde=beklenen)

    if atif.belge_no is None:
        return satir("insan_incelemeli", "sertifikada standart atfı bulunamadı")
    if atif.belge_no != std.belge_no:
        return satir("uygun_degil", f"sertifika başka bir standarda atıf yapıyor: {atif.belge_no}")
    if atif.revizyon is None:
        return satir("insan_incelemeli", "sertifikada revizyon harfi yok")
    if atif.revizyon != std.revizyon:
        return satir(ayar.yanlis_revizyon, f"sertifika {atif.belge_no}{atif.revizyon} diyor, beklenen {beklenen}")
    return satir("uygun", f"atıf {beklenen}")


_KOD_ONEKI = re.compile(r"^(?:TYPE|CLASS)(?=\s|$)")


def _kod(deger: str | None) -> str | None:
    """Katalogdaki tip/sınıf kodunu uygulanabilirlikle aynı biçime getirir.

    "Type"/"Class" öneki ve boşluklar atılır, büyük harfe çevrilir, 1/2 Roma
    rakamına çevrilir: '1' -> 'I', 'n' -> 'N', 'Class N' -> 'N', 'C 2' -> 'C2',
    'TYPE 2' -> 'II'. Boş değer None'dır.
    """
    if deger is None:
        return None
    deger = _KOD_ONEKI.sub("", deger.strip().upper())
    deger = "".join(deger.split())
    if not deger:
        return None
    return _ROMEN.get(deger, deger)


kod_normallestir = _kod


def _liste_kodu(kod: str) -> str | None:
    """Ürün tanımındaki kodu ('Type I', 'Class 1', 'N') katalog koduyla aynı biçime getirir."""
    return _kod(kod)


# Ürün tanımı olmayan dokümanlar için standardın bilinen tip/sınıf kodları (belge no -> boyut -> kodlar).
# Katalogdaki kod ne burada ne de dokümanın uygulanabilirlik kodlarında varsa insana gider (K7).
BILINEN_KODLAR: dict[str, dict[str, frozenset[str]]] = {
    "MIL-PRF-23377": {"type": frozenset({"I", "II"}), "class": frozenset({"C1", "C2", "N"})},
}


def _uygulanabilirlik_kodlari(dokuman: KabulDokumani, kategori: str) -> set[str]:
    """Dokümanın şartlarında `kategori` ('type'/'class') için geçen uygulanabilirlik kodları."""
    kodlar = set()
    for t in dokuman.testler:
        for u in t.uygulanabilirlik:
            if (m := _UYG.match(u)) and m.group(1).lower() == kategori and (k := _kod(m.group(2))):
                kodlar.add(k)
    return kodlar


def _boyuta_bagli_testler(dokuman: KabulDokumani, kategori: str) -> list[str]:
    """Uygulanabilirliği tipe ('type') ya da sınıfa ('class') bağlı kabul testlerinin kimlikleri."""
    return [
        t.id for t in dokuman.kabul_testleri
        if any((m := _UYG.match(u)) and m.group(1).lower() == kategori for u in t.uygulanabilirlik)
    ]


def _tip_sinif_kontrolu(
    atif: Atif, tip: str | None, sinif: str | None, dokuman: KabulDokumani | None = None
) -> KararSatiri:
    """Katalogdaki tip/sınıfı dokümanın ürün tanımına ve sertifika atfına karşı denetler.

    Doküman bir tip (sınıf) listesi tanımlıyorsa katalogdaki tip (sınıf) tanımlı
    olmalı ve listede bulunmalıdır; değilse insan incelemeli (K5, K7). Liste boşsa
    ya da ürün tanımı yoksa: katalogdaki tip (sınıf) tanımsızken bir kabul
    testinin uygulanabilirliği tipe (sınıfa) bağlıysa insan incelemeli;
    tanımlıysa kod, dokümanın uygulanabilirlik kodlarında ya da standardın
    bilinen kodlarında (`BILINEN_KODLAR`) olmalıdır. Standardın bilinen kodu
    yoksa yalnız boyuta bağlı kabul testi varken dokümanın kodlarına bakılır. Sertifika atfı yalnız çelişki
    denetimi içindir; katalogdaki eksik değerin yerine konmaz.
    """

    def satir(karar: Karar, gerekce: str) -> KararSatiri:
        return KararSatiri(test_id="tip_sinif", test_adi="Tip ve sınıf (katalog)", karar=karar, gerekce=gerekce)

    if dokuman is not None:
        urun = dokuman.urun_tanimi
        sorunlar: list[str] = []
        boyutlar = (
            ("tip", "type", tip, urun.tipler if urun else []),
            ("sınıf", "class", sinif, urun.siniflar if urun else []),
        )
        for ad, kategori, deger, liste in boyutlar:
            if liste:
                if deger is None:
                    sorunlar.append(f"katalogda tip/sınıf tanımsız ({ad} yok); standart {ad} listesi tanımlıyor")
                elif deger not in [_liste_kodu(k.kod) for k in liste]:
                    sorunlar.append(
                        f"katalogdaki {ad} {deger!r} kabul dokümanının listesinde yok "
                        f"({', '.join(k.kod for k in liste)})"
                    )
            elif deger is None:
                if bagli := _boyuta_bagli_testler(dokuman, kategori):
                    sorunlar.append(
                        f"katalogda tip/sınıf tanımsız ({ad} yok); kabul testi {ad}a bağlı: {', '.join(bagli)}"
                    )
            else:
                bilinen = BILINEN_KODLAR.get(dokuman.standart.belge_no, {}).get(kategori)
                dokumandaki = _uygulanabilirlik_kodlari(dokuman, kategori)
                if bilinen is not None:
                    gecerli = bilinen | dokumandaki
                    if deger not in gecerli:
                        sorunlar.append(
                            f"katalogdaki {ad} {deger!r} standardın bilinen kodlarında yok "
                            f"({', '.join(sorted(gecerli))})"
                        )
                elif _boyuta_bagli_testler(dokuman, kategori) and deger not in dokumandaki:
                    sorunlar.append(
                        f"katalogdaki {ad} {deger!r} kabul dokümanının uygulanabilirlik kodlarında yok "
                        f"({', '.join(sorted(dokumandaki))})"
                    )
        if sorunlar:
            return satir("insan_incelemeli", "; ".join(sorunlar))

    celiski = [
        f"{ad} katalogda {beklenen}, sertifikada {okunan}"
        for ad, beklenen, okunan in (("tip", tip, atif.tip), ("sınıf", sinif, atif.sinif))
        if beklenen is not None and okunan is not None and beklenen != okunan
    ]
    if celiski:
        return satir("insan_incelemeli", "; ".join(celiski))
    return satir("uygun", f"katalog: Type {tip or '-'} Class {sinif or '-'}")


def uygulanan_testler(dokuman: KabulDokumani, tip: str | None, sinif: str | None) -> list[TestSarti]:
    """Tip/sınıfa uygulanan (ya da uygulanıp uygulanmadığı bilinmeyen) kabul testleri."""
    return [t for t in dokuman.kabul_testleri if uygulanir_mi(t.uygulanabilirlik, tip, sinif) is not False]


def aranan_testler(dokuman: KabulDokumani, tip: str | None, sinif: str | None) -> list[TestSarti]:
    """Sertifikada (CoC) aranan testler: uygulanan kabul testlerinden sonucu CoC'den gelenler.

    Sertifika satırları yalnız bu kümeye eşlenir (`kontrol_et` ve
    `okuma_karsilastirma` aynı kümeyi kullanır).
    """
    return [t for t in uygulanan_testler(dokuman, tip, sinif) if t.sonuc_kaynagi == "coc"]


def kontrol_et(
    dokuman: KabulDokumani,
    sertifika: Sertifika,
    ayar: KararAyarlari | None = None,
    tip: str | None = None,
    sinif: str | None = None,
    katalogdan: bool | None = None,
) -> KontrolSonucu:
    """Sertifikayı kabul dokümanının kabul testleriyle karşılaştırır.

    `tip` ve `sinif` katalogdan verilirse uygulanabilirlik onlara göre seçilir
    (docs/mimari.md madde 2); verilmezse sertifikadaki atıftan okunur.
    `katalogdan=True` tip/sınıfın katalogdan geldiğini bildirir: ikisi de None
    olsa bile sertifika atfına düşülmez (K5). Verilmezse tip ya da sınıftan
    biri verilmişse katalogdan sayılır.
    """
    ayar = ayar or KararAyarlari()
    atif = atfi_coz(sertifika.standart_atfi)
    revizyon = _revizyon_kontrolu(dokuman, atif, ayar)
    tip_sinif = None
    if katalogdan is None:
        katalogdan = tip is not None or sinif is not None
    if katalogdan:
        tip, sinif = _kod(tip), _kod(sinif)
        tip_sinif = _tip_sinif_kontrolu(atif, tip, sinif, dokuman)
        atif = Atif(atif.belge_no, atif.revizyon, tip, sinif)

    uygulanan = uygulanan_testler(dokuman, atif.tip, atif.sinif)
    aranan = aranan_testler(dokuman, atif.tip, atif.sinif)

    eslesmeler: dict[str, list[int]] = {t.id: [] for t in aranan}
    eslesmeyen: list[str] = []
    for i, satir in enumerate(sertifika.satirlar):
        test_id = eslestir(satir.test_adi, aranan)
        if test_id is not None:
            eslesmeler[test_id].append(i)
        elif eslestir(satir.test_adi, dokuman.testler) is None:
            eslesmeyen.append(satir.test_adi)
        # aranmayan bir teste (yeterlilik, başka tip ya da iç laboratuvar) eşleşen satır yok sayılır

    satirlar: list[KararSatiri] = []
    for test in uygulanan:
        ortak = {"test_id": test.id, "test_adi": test.test_adi, "madde": test.kaynak.etiket, "sayfa": test.kaynak.sayfa}
        if test.sonuc_kaynagi == "ic_laboratuvar":
            neden = "sonuç iç laboratuvardan gelir; CoC'de aranmadı, iç laboratuvar sonucu bekleniyor"
            satirlar.append(KararSatiri(karar="insan_incelemeli", gerekce=neden, **ortak))
            continue
        idx = eslesmeler[test.id]
        if not idx:
            neden = "sertifikada bu test yok"
            if uygulanir_mi(test.uygulanabilirlik, atif.tip, atif.sinif) is None:
                neden += " (tip/sınıf bilinmediği için uygulanıp uygulanmadığı belirsiz)"
            satirlar.append(KararSatiri(karar=ayar.eksik_test, gerekce=neden, **ortak))
            continue
        if len(idx) > 1:
            adlar = ", ".join(sertifika.satirlar[i].test_adi for i in idx)
            satirlar.append(KararSatiri(karar="insan_incelemeli", gerekce=f"test birden çok kez verilmiş: {adlar}", **ortak))
            continue
        ss = sertifika.satirlar[idx[0]]
        karar, gerekce, deger = _degerlendir(test, ss.sonuc, ss.birim)
        satirlar.append(
            KararSatiri(
                karar=karar,
                gerekce=gerekce,
                sertifikadaki_ad=ss.test_adi,
                okunan_sonuc=ss.sonuc,
                okunan_birim=ss.birim,
                cevrilmis_deger=deger,
                hedef_birim=test.sinir.birim,
                **ortak,
            )
        )

    if not uygulanan:
        satirlar.append(KararSatiri(
            test_id="kabul_testleri", test_adi="Uygulanan kabul testleri", karar="insan_incelemeli",
            gerekce="uygulanan kabul testi yok; sertifika hiçbir şarta karşı denetlenmedi",
        ))

    return KontrolSonucu(
        sertifika_no=sertifika.sertifika_no,
        belge_karari=parti_karari(
            [revizyon.karar] + ([tip_sinif.karar] if tip_sinif else []) + [s.karar for s in satirlar]
        ),
        revizyon=revizyon,
        satirlar=satirlar,
        tip_sinif=tip_sinif,
        eslesmeyen_satirlar=eslesmeyen,
    )


__all__ = [
    "Atif",
    "BIRIM_ESANLAMLILARI",
    "aranan_testler",
    "ESANLAMLILAR",
    "KararAyarlari",
    "KararSatiri",
    "KontrolSonucu",
    "Sonuc",
    "atfi_coz",
    "birimi_cevir",
    "kod_normallestir",
    "kontrol_et",
    "parti_karari",
    "SINIR_YAKINLIK_BAGIL",
    "SINIR_YAKINLIK_MUTLAK",
    "sonucu_ayristir",
    "uygulanan_testler",
    "eslestir",
    "uygulanir_mi",
]
