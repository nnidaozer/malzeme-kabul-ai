"""Karar motoru: tedarikçi sertifikasını kabul dokümanıyla karşılaştırır.

Her kabul testi için "uygun / uygun_degil / insan_incelemeli" kararı verir ve
dayandığı standart maddesini gösterir. Bütün adımlar kesin kurallardır; dil
modeli kullanılmaz (CLAUDE.md, kural 1):

1. Atıf: sertifikadaki "MIL-PRF-23377K Type I Class C2" metninden belge no,
   revizyon, tip ve sınıf çıkarılır; revizyon kabul dokümanıyla karşılaştırılır.
2. Aranacak testler: yalnız kabul testleri (yeterlilik testleri aranmaz) ve
   yalnız sertifikadaki tip/sınıfa uygulananlar.
3. Eşleştirme: sertifikadaki test adı normalleştirilir; kabul dokümanındaki
   ad, kimlik ve `ESANLAMLILAR` tablosuyla birebir, olmazsa kelime
   benzerliğiyle (tek ve açık bir en iyi aday varsa) eşleştirilir.
4. Sonuç: "320", "1,5", "<1", "5A", "Conforms", "Fail" gibi metinler sayı
   aralığına ya da geçti/kaldı sonucuna çevrilir.
5. Birim: pint ile hedef birime çevrilir. "mil" pint'te açı birimi olduğu için
   önce "thou" (inç/1000) yapılır. Çevrilemeyen birim insana bırakılır.
6. Karşılaştırma: okunan değer aralığı sınırın tamamen içindeyse uygun,
   tamamen dışındaysa uygun değil, ikisi de değilse ("<8 saat" ile "en çok 5
   saat") insan incelemeli. Yuvarlama yapılmaz.

Emin olunmayan her durumda karar insana bırakılır; böylece belirsizlik yanlış
kabule dönüşmez.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .birimler import kayit
from .sema import KabulDokumani, Sinir, TestSarti
from .sertifika import Sertifika

Karar = Literal["uygun", "uygun_degil", "insan_incelemeli"]
BelgeKarari = Literal["kabul", "red", "inceleme"]


class KararAyarlari(BaseModel):
    """Politikaya bağlı kararlar. Varsayılanlar belge sorunlarını insana bırakır."""

    model_config = ConfigDict(extra="forbid")

    eksik_test: Karar = "insan_incelemeli"
    yanlis_revizyon: Karar = "insan_incelemeli"


class KararSatiri(BaseModel):
    """Bir kabul testi (ya da revizyon kontrolü) için verilen karar."""

    model_config = ConfigDict(extra="forbid")

    test_id: str
    test_adi: str
    karar: Karar
    gerekce: str
    madde: str | None = None
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


_BELGE = re.compile(r"\b(MIL)[-\s]?(PRF|DTL|C|P|S)[-\s]?(\d+)([A-Z])?(?![A-Z0-9])")
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
    birimdir ("4 h").
    """

    tur: Literal["sayi", "gecti", "kaldi", "belirsiz"]
    alt: float | None = None
    ust: float | None = None
    alt_dahil: bool = True
    ust_dahil: bool = True
    birim_ek: str | None = None


_SAYI = re.compile(
    r"^(?P<op><=|>=|≤|≥|<|>)?\s*(?P<sayi>[+-]?\d+(?:[.,]\d+)?)\s*(?P<ek>[A-Za-zµμ°%/][A-Za-z0-9µμ°%/.\- ]*)?$"
)
_DERECE_HARFI = re.compile(r"^[A-B]$")  # ASTM D3359 yapışma derecesi: 4A, 5B
_KALDI = ("does not conform", "not conform", "non conform", "nonconform", "uygun degil", "fail", "failed", "fails",
          "kaldi", "reject", "rejected", "reddedildi")
_GECTI = ("pass", "passed", "conforms", "conform", "complies", "comply", "satisfactory", "meets", "uygun", "gecti", "ok", "kabul")


def sonucu_ayristir(metin: str) -> Sonuc:
    """Sonuç hücresini sayı aralığına ya da geçti/kaldı sonucuna çevirir."""
    ham = (metin or "").strip()
    m = _SAYI.match(ham)
    if m:
        sayi = float(m.group("sayi").replace(",", "."))
        ek = (m.group("ek") or "").strip() or None
        if ek and _DERECE_HARFI.match(ek):
            ek = None
        op = m.group("op")
        if op in ("<", "≤", "<="):
            return Sonuc("sayi", None, sayi, True, op != "<", ek)
        if op in (">", "≥", ">="):
            return Sonuc("sayi", sayi, None, op != ">", True, ek)
        return Sonuc("sayi", sayi, sayi, True, True, ek)
    normal = _normal(ham)
    kelimeler = normal.split()
    if any(re.search(rf"\b{k}", normal) for k in _KALDI):
        return Sonuc("kaldi")
    if kelimeler and any(re.search(rf"\b{k}\b", normal) for k in _GECTI):
        return Sonuc("gecti")
    return Sonuc("belirsiz")


# --- birim dönüşümü -------------------------------------------------------

BIRIM_ESANLAMLILARI = {
    "mil": "thou", "mils": "thou", "thou": "thou",
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


def _sayilastir(x: float) -> float:
    """Kayan nokta artığını at (300 dk -> 5 saat tam çıksın); 12 anlamlı basamak."""
    return float(f"{x:.12g}")


def birimi_cevir(deger: float, kaynak: str | None, hedef: str | None) -> float:
    """Değeri kaynak birimden hedef birime pint ile çevirir; olmazsa ValueError."""
    if not kaynak and not hedef:
        return deger
    if not kaynak or not hedef:
        raise ValueError(f"birim eksik: {kaynak!r} -> {hedef!r}")
    try:
        q = kayit().Quantity(deger, _pint_birimi(kaynak))
        return _sayilastir(q.to(_pint_birimi(hedef)).magnitude)
    except Exception as hata:  # pint: tanımsız birim, boyut uyumsuzluğu, sözdizimi
        raise ValueError(f"birim çevrilemedi: {kaynak!r} -> {hedef!r}") from hata


# --- test eşleştirme ------------------------------------------------------

# Standartlardaki ve sertifikalardaki yaygın test adları (İngilizce ve Türkçe).
# Kabul dokümanındaki test kimliğine göre yazılmıştır; sertifika üreticisinden
# önce, standart terminolojisinden hazırlandı.
ESANLAMLILAR: dict[str, list[str]] = {
    "lead_and_cadmium_content": ["cadmium content", "lead and cadmium", "cadmium", "kursun ve kadmiyum", "kadmiyum"],
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
    adlar = {test.test_adi, test.id.replace("_", " ")}
    adlar |= {_EK_TEMIZLE.sub("", a) for a in list(adlar)}
    normal = {_normal(a) for a in adlar}
    normal |= {_TIP_EKI.sub("", a) for a in list(normal)}
    normal |= {_normal(a) for a in ESANLAMLILAR.get(test.id, [])}
    return {a for a in normal if a}


def _kelimeler(metin: str) -> set[str]:
    return {k for k in metin.split() if k not in _DOLGU}


def eslestir(ad: str, testler: list[TestSarti], esik: float = 0.6) -> str | None:
    """Sertifikadaki test adını kabul dokümanındaki bir teste eşler; yoksa None."""
    adaylar = {_normal(ad), _normal(_EK_TEMIZLE.sub("", ad))} - {""}
    birebir = [t.id for t in testler if adaylar & _taban_adlar(t)]
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
    cevrilmis = Sonuc("sayi", alt, ust, s.alt_dahil, s.ust_dahil)
    karar = _icinde_mi(cevrilmis, sinir)
    deger = alt if alt is not None else ust
    okunan = f"{sonuc_metni} {kaynak_birim or ''}".strip()
    if kaynak_birim and sinir.birim and _pint_birimi(kaynak_birim) != _pint_birimi(sinir.birim):
        okunan += f" (= {deger:g} {sinir.birim})"
    gerekce = {
        "uygun": f"{okunan}, şart {_sinir_metni(sinir)} içinde",
        "uygun_degil": f"{okunan}, şart {_sinir_metni(sinir)} dışında",
        "insan_incelemeli": f"{okunan} ile şart {_sinir_metni(sinir)} karşılaştırılamıyor",
    }[karar]
    return karar, gerekce, deger


# --- ana fonksiyon --------------------------------------------------------


def _belge_karari(kararlar: list[Karar]) -> BelgeKarari:
    if "uygun_degil" in kararlar:
        return "red"
    if "insan_incelemeli" in kararlar:
        return "inceleme"
    return "kabul"


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


def kontrol_et(dokuman: KabulDokumani, sertifika: Sertifika, ayar: KararAyarlari | None = None) -> KontrolSonucu:
    """Sertifikayı kabul dokümanının kabul testleriyle karşılaştırır."""
    ayar = ayar or KararAyarlari()
    atif = atfi_coz(sertifika.standart_atfi)
    revizyon = _revizyon_kontrolu(dokuman, atif, ayar)

    aranan = [t for t in dokuman.kabul_testleri if uygulanir_mi(t.uygulanabilirlik, atif.tip, atif.sinif) is not False]

    eslesmeler: dict[str, list[int]] = {t.id: [] for t in aranan}
    eslesmeyen: list[str] = []
    for i, satir in enumerate(sertifika.satirlar):
        test_id = eslestir(satir.test_adi, aranan)
        if test_id is not None:
            eslesmeler[test_id].append(i)
        elif eslestir(satir.test_adi, dokuman.testler) is None:
            eslesmeyen.append(satir.test_adi)
        # aranmayan bir teste (yeterlilik ya da başka tip) eşleşen satır yok sayılır

    satirlar: list[KararSatiri] = []
    for test in aranan:
        ortak = {"test_id": test.id, "test_adi": test.test_adi, "madde": test.kaynak.etiket}
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

    return KontrolSonucu(
        sertifika_no=sertifika.sertifika_no,
        belge_karari=_belge_karari([revizyon.karar] + [s.karar for s in satirlar]),
        revizyon=revizyon,
        satirlar=satirlar,
        eslesmeyen_satirlar=eslesmeyen,
    )


__all__ = [
    "Atif",
    "BIRIM_ESANLAMLILARI",
    "ESANLAMLILAR",
    "KararAyarlari",
    "KararSatiri",
    "KontrolSonucu",
    "Sonuc",
    "atfi_coz",
    "birimi_cevir",
    "kontrol_et",
    "sonucu_ayristir",
    "eslestir",
    "uygulanir_mi",
]
