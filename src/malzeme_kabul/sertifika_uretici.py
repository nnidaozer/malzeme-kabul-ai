"""Sentetik tedarikçi sertifikası (CoC/TR) üreticisi.

Bir kabul dokümanındaki kabul testleri için, gerçek CoC/TR düzenine benzeyen
sertifikalar üretir ve her sertifikanın doğru kararını ayrı tutar. Karar
motorunu ölçmek için kullanılır.

Doğru kararlar karar motoru çağrılmadan, üreticinin kendi bildiği gerçek
değerden hesaplanır: her değer önce şartın biriminde seçilir, sonra (birim
değişikliği hatasında) sabit çarpanlarla başka birime yazılır. Böylece ölçüm,
motorun kendi çıktısıyla kendini doğrulaması olmaz.

Hata türleri (Nida'nın onayladığı liste):
- sinir_disi: sınırın açıkça dışında değer ya da metinsel testte "Fail".
- birim: değer başka birimde; çevrilince uygun, çevrilince sınır dışı ya da
  çevrilemeyen birim.
- eksik_test: uygulanan bir kabul testi tabloda yok (insan incelemeli).
- ad_farki: test adı farklı yazılmış, değer doğru.
- revizyon: yanlış revizyon atfı (belge düzeyinde insan incelemeli).
- sinira_yakin: tam sınırda, hemen içinde ya da hemen dışında.
- algilama_siniri: "<1 ppm", "ND (<0.5 ppm)" (uygun) ve sınırsız "ND"
  (insan incelemeli).

Tedarikçi adları kurgusaldır; belgeler "sentetik" olarak işaretlenir.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .karar_olcumu import DogruKarar
from .sema import KabulDokumani, TestSarti
from .sertifika import Sertifika, SertifikaSatiri

# Hata türü -> sertifika adedi (toplam 150; 70 temiz, 80 hatalı)
DAGILIM: dict[str | None, int] = {
    None: 70,
    "sinir_disi": 14,
    "birim": 12,
    "eksik_test": 10,
    "ad_farki": 10,
    "revizyon": 10,
    "sinira_yakin": 14,
    "algilama_siniri": 10,
}

TIPLER = ("I", "II")
SINIFLAR = ("C1", "C2", "N")


@dataclass(frozen=True)
class Sablon:
    """Bir tedarikçinin sertifika düzeni."""

    kod: str
    tedarikci: str
    adres: str
    dil: str  # "en" ya da "tr"
    atif_bicimi: str  # {rev}, {tip}, {sinif}
    gecti: str
    ondalik_virgul: bool
    birimler: dict[str, str]  # şart birimi -> sertifikada yazılışı
    sutunlar: tuple[str, ...]  # PDF tablo sırası: ad, metot, sart, sonuc, birim


SABLONLAR = (
    Sablon(
        kod="A",
        tedarikci="Kurgu Coatings Inc. (kurgusal)",
        adres="100 Example Rd., Testville",
        dil="en",
        atif_bicimi="MIL-PRF-23377{rev} Type {tip} Class {sinif}",
        gecti="Conforms",
        ondalik_virgul=False,
        birimler={"g/L": "g/L", "hour": "h", "s": "s", "µm": "µm", "%": "%", "ppm": "ppm"},
        sutunlar=("ad", "metot", "sart", "sonuc", "birim"),
    ),
    Sablon(
        kod="B",
        tedarikci="Ornek Aerospace Finishes Ltd. (kurgusal)",
        adres="Unit 7, Sample Park",
        dil="en",
        atif_bicimi="MIL-PRF-23377 Rev. {rev}, Type {tip}, Class {sinif}",
        gecti="Pass",
        ondalik_virgul=False,
        birimler={"g/L": "g/l", "hour": "hrs", "s": "sec", "µm": "microns", "%": "%", "ppm": "ppm"},
        sutunlar=("ad", "sonuc", "birim", "sart", "metot"),
    ),
    Sablon(
        kod="C",
        tedarikci="Deneme Kimya San. A.Ş. (kurgusal)",
        adres="Örnek OSB, 1. Cadde No: 1",
        dil="tr",
        atif_bicimi="Şartname: MIL-PRF-23377{rev}, Tip {tip}, Sınıf {sinif}",
        gecti="Uygun",
        ondalik_virgul=True,
        birimler={"g/L": "g/L", "hour": "saat", "s": "sn", "µm": "µm", "%": "%", "ppm": "ppm"},
        sutunlar=("ad", "metot", "sart", "sonuc", "birim"),
    ),
)

# Temiz sertifikada değer aralığı (şart biriminde) ve ondalık basamak.
TEMIZ_ARALIK: dict[str, tuple[float, float, int]] = {
    "lead_and_cadmium_content": (0.1, 0.6, 1),
    "chromium_content_class_n_only": (0.5, 3.0, 1),
    "voc_solvent_content": (250, 330, 0),
    "fineness_of_grind": (6, 7, 0),
    "viscosity": (20, 35, 0),
    "pot_life": (40, 65, 0),
    "drying_time": (2, 4.5, 1),
    "adhesion": (4, 5, 0),
    "flexibility": (12, 30, 0),
    "infrared_reflectance_type_ii_only": (3, 8, 1),
    "application": (17, 21, 0),
}

# Test adlarının sertifikalarda görülebilecek farklı yazılışları. Karar
# motorundan bağımsız, sertifika ve standart terminolojisinden yazıldı.
AD_VARYANTLARI: dict[str, list[str]] = {
    "drying_time": ["Tack-free time", "Dry to touch", "Kuruma süresi"],
    "voc_solvent_content": ["VOC content", "Volatile Organic Content (VOC)", "VOC (g/L)"],
    "fineness_of_grind": ["Hegman grind", "Grind fineness"],
    "viscosity": ["Viscosity, initial (Zahn #2)", "Viskozite"],
    "pot_life": ["Pot-life", "Viscosity after 4 hours"],
    "adhesion": ["Wet tape adhesion", "Cross-cut adhesion"],
    "flexibility": ["GE impact elongation", "Esneklik"],
    "application": ["Dry film thickness", "DFT"],
    "condition_in_container": ["Condition in can", "Kap içi durum"],
    "odor": ["Odour"],
    "surface_appearance": ["Appearance", "Film appearance"],
    "solvent_resistance_cure": ["MEK rub resistance", "Solvent rub (cure)"],
    "fluid_resistance": ["Hydraulic fluid resistance"],
    "water_resistance": ["Water immersion"],
    "mixing_and_dilution": ["Mixing", "Mixing / thinning"],
    "lifting": ["Lifting resistance"],
    "lead_and_cadmium_content": ["Cadmium", "Pb/Cd content"],
}

# Birim değişikliği senaryoları: (test, sertifikadaki değer, birim, doğru karar, açıklama)
# Çarpanlar: 1 h = 60 min = 1/24 day; 1 mil = 25,4 µm; 1 lb/gal = 119,826 g/L; 1 min = 60 s.
BIRIM_SENARYOLARI: list[tuple[str, str, str, str, str]] = [
    ("drying_time", "270", "min", "uygun", "4,5 saat dakika olarak"),
    ("drying_time", "180", "min", "uygun", "3 saat dakika olarak"),
    ("application", "0.8", "mil", "uygun", "20,3 µm mil olarak"),
    ("application", "0.7", "mils", "uygun", "17,8 µm mil olarak"),
    ("voc_solvent_content", "2.6", "lb/gal", "uygun", "311,5 g/L lb/gal olarak"),
    ("viscosity", "0.5", "min", "uygun", "30 s dakika olarak"),
    ("drying_time", "0.25", "day", "uygun_degil", "6 saat gün olarak; sayı sınırdan küçük görünüyor"),
    ("drying_time", "0.3", "day", "uygun_degil", "7,2 saat gün olarak; sayı sınırdan küçük görünüyor"),
    ("voc_solvent_content", "2.9", "lb/gal", "uygun_degil", "347,5 g/L lb/gal olarak"),
    ("application", "1.0", "mil", "uygun_degil", "25,4 µm mil olarak"),
    ("viscosity", "45", "cP", "insan_incelemeli", "akış kabı saniyesi yerine dinamik viskozite (cP)"),
    ("pot_life", "120", "cP", "insan_incelemeli", "akış kabı saniyesi yerine dinamik viskozite (cP)"),
]

# Sınıra yakın senaryolar: (test, değer şart biriminde, doğru karar)
SINIRA_YAKIN: list[tuple[str, str, str]] = [
    ("voc_solvent_content", "340", "uygun"),
    ("drying_time", "5", "uygun"),
    ("viscosity", "40", "uygun"),
    ("application", "23", "uygun"),
    ("flexibility", "10", "uygun"),
    ("fineness_of_grind", "5", "uygun"),
    ("voc_solvent_content", "339.8", "uygun"),
    ("drying_time", "4.9", "uygun"),
    ("viscosity", "39.5", "uygun"),
    ("application", "15.1", "uygun"),
    ("voc_solvent_content", "340.2", "uygun_degil"),
    ("drying_time", "5.1", "uygun_degil"),
    ("viscosity", "40.5", "uygun_degil"),
    ("flexibility", "9.8", "uygun_degil"),
]

# Algılama sınırı ifadeleri (kadmiyum, ≤ 1 ppm): (sonuç, birim, doğru karar)
ALGILAMA: list[tuple[str, str | None, str]] = [
    ("<1", "ppm", "uygun"),
    ("< 1 ppm", None, "uygun"),
    ("<0.5", "ppm", "uygun"),
    ("ND (<0.5 ppm)", None, "uygun"),
    ("ND (<1 ppm)", None, "uygun"),
    ("≤ 1", "ppm", "uygun"),
    ("ND", "ppm", "insan_incelemeli"),
    ("ND", None, "insan_incelemeli"),
    ("Not detected", "ppm", "insan_incelemeli"),
    ("ND", "ppm", "insan_incelemeli"),
]

YANLIS_REVIZYONLAR = ("J", "H")


@dataclass
class UretilenSertifika:
    sertifika: Sertifika
    dogru: DogruKarar
    sablon: Sablon
    sart_metinleri: dict[str, str] = field(default_factory=dict)  # test adı -> şart sütunu


def uygulanir(test: TestSarti, tip: str, sinif: str) -> bool:
    """Üreticinin kendi uygulanabilirlik kuralı: listede 'Type X' / 'Class Y'."""
    if not test.uygulanabilirlik:
        return True
    tipler = {u.split()[1] for u in test.uygulanabilirlik if u.startswith("Type ")}
    siniflar = {u.split()[1] for u in test.uygulanabilirlik if u.startswith("Class ")}
    return (not tipler or tip in tipler) and (not siniflar or sinif in siniflar)


def _yaz(deger: float | str, basamak: int, sablon: Sablon) -> str:
    metin = deger if isinstance(deger, str) else f"{deger:.{basamak}f}"
    return metin.replace(".", ",") if sablon.ondalik_virgul else metin


def _sart_metni(test: TestSarti) -> str:
    s = test.sinir
    if s.kriter_turu != "sayisal":
        return "See spec"
    b = f" {s.birim}" if s.birim else ""
    if s.alt is not None and s.ust is not None:
        return f"{s.alt:g}-{s.ust:g}{b}"
    if s.ust is not None:
        return f"{s.ust:g}{b} max"
    return f"{s.alt:g}{b} min"


def _temiz_satir(test: TestSarti, sablon: Sablon, rng: random.Random) -> SertifikaSatiri:
    if test.sinir.kriter_turu != "sayisal":
        sonuc = sablon.gecti
        birim = None
    else:
        alt, ust, basamak = TEMIZ_ARALIK[test.id]
        deger = round(rng.uniform(alt, ust), basamak)
        sonuc = _yaz(deger, basamak, sablon)
        if test.id == "adhesion":
            sonuc = f"{int(deger)}A"
        birim = sablon.birimler.get(test.sinir.birim) if test.sinir.birim else None
    return SertifikaSatiri(test_adi=test.test_adi, sonuc=sonuc, birim=birim, metot=test.test_metodu, sart=_sart_metni(test))


def _sinir_disi(test: TestSarti, sablon: Sablon, rng: random.Random) -> str:
    s = test.sinir
    if s.kriter_turu != "sayisal":
        return "Fail" if sablon.dil == "en" else "Uygun değil"
    if test.id == "adhesion":
        return rng.choice(["2A", "3A"])
    if s.ust is not None:
        deger = s.ust * rng.uniform(1.08, 1.3)
    else:
        deger = s.alt * rng.uniform(0.5, 0.85)
    basamak = TEMIZ_ARALIK[test.id][2]
    if basamak == 0:
        deger = round(deger)
        if s.ust is not None and deger <= s.ust:
            deger = s.ust + 1
        if s.ust is None and deger >= s.alt:
            deger = s.alt - 1
    return _yaz(round(deger, basamak), basamak, sablon)


def _sec(rng: random.Random, uygun: list[TestSarti], kosul) -> TestSarti:
    adaylar = [t for t in uygun if kosul(t)]
    return rng.choice(adaylar)


def _belge_karari(kararlar: list[str]) -> str:
    if "uygun_degil" in kararlar:
        return "red"
    if "insan_incelemeli" in kararlar:
        return "inceleme"
    return "kabul"


def uret(dokuman: KabulDokumani, tohum: int = 23377, dagilim: dict[str | None, int] | None = None) -> list[UretilenSertifika]:
    """Dağılıma göre sertifikaları üretir; aynı tohumla her zaman aynı sonucu verir."""
    dagilim = dagilim or DAGILIM
    rng = random.Random(tohum)
    turler: list[str | None] = [t for t, n in dagilim.items() for _ in range(n)]
    rng.shuffle(turler)
    sayac = {t: 0 for t in dagilim}  # senaryo listelerinde sıra
    cikti: list[UretilenSertifika] = []

    for i, tur in enumerate(turler, start=1):
        sablon = SABLONLAR[(i - 1) % len(SABLONLAR)]
        tip, sinif = rng.choice(TIPLER), rng.choice(SINIFLAR)
        uygun = [t for t in dokuman.kabul_testleri if uygulanir(t, tip, sinif)]
        satirlar = {t.id: _temiz_satir(t, sablon, rng) for t in uygun}
        dogru = {t.id: "uygun" for t in uygun}
        revizyon_karari = "uygun"
        rev = dokuman.standart.revizyon
        aciklama = None
        sira = sayac[tur]
        sayac[tur] += 1

        if tur == "sinir_disi":
            sayisal = sira % 3 != 2  # üçte ikisi sayısal, üçte biri metinsel
            test = _sec(rng, uygun, lambda t: (t.sinir.kriter_turu == "sayisal") == sayisal)
            satirlar[test.id] = satirlar[test.id].model_copy(update={"sonuc": _sinir_disi(test, sablon, rng)})
            dogru[test.id] = "uygun_degil"
            aciklama = f"{test.id}: {satirlar[test.id].sonuc}"
        elif tur == "birim":
            test_id, deger, birim, karar, aciklama = BIRIM_SENARYOLARI[sira % len(BIRIM_SENARYOLARI)]
            satirlar[test_id] = satirlar[test_id].model_copy(update={"sonuc": _yaz(deger, 0, sablon), "birim": birim})
            dogru[test_id] = karar
            aciklama = f"{test_id}: {deger} {birim} ({aciklama})"
        elif tur == "eksik_test":
            test = rng.choice(uygun)
            del satirlar[test.id]
            dogru[test.id] = "insan_incelemeli"
            aciklama = f"{test.id} tabloda yok"
        elif tur == "ad_farki":
            test = _sec(rng, uygun, lambda t: t.id in AD_VARYANTLARI)
            yeni = rng.choice(AD_VARYANTLARI[test.id])
            satirlar[test.id] = satirlar[test.id].model_copy(update={"test_adi": yeni})
            aciklama = f"{test.id} -> {yeni!r}"
        elif tur == "revizyon":
            rev = YANLIS_REVIZYONLAR[sira % len(YANLIS_REVIZYONLAR)]
            revizyon_karari = "insan_incelemeli"
            aciklama = f"atıf MIL-PRF-23377{rev}"
        elif tur == "sinira_yakin":
            test_id, deger, karar = SINIRA_YAKIN[sira % len(SINIRA_YAKIN)]
            satirlar[test_id] = satirlar[test_id].model_copy(update={"sonuc": _yaz(deger, 0, sablon)})
            dogru[test_id] = karar
            aciklama = f"{test_id}: {deger}"
        elif tur == "algilama_siniri":
            sonuc, birim, karar = ALGILAMA[sira % len(ALGILAMA)]
            test_id = "lead_and_cadmium_content"
            satirlar[test_id] = satirlar[test_id].model_copy(update={"sonuc": _yaz(sonuc, 0, sablon), "birim": birim})
            dogru[test_id] = karar
            aciklama = f"{test_id}: {sonuc!r} {birim or ''}".strip()

        no = f"S-{i:03d}"
        sertifika = Sertifika(
            sertifika_no=no,
            standart_atfi=sablon.atif_bicimi.format(rev=rev, tip=tip, sinif=sinif),
            tedarikci=sablon.tedarikci,
            urun=f"Epoxy primer, Type {tip}, Class {sinif}",
            parti_no=f"{sablon.kod}{rng.randint(10000, 99999)}",
            uretim_tarihi=f"2026-{rng.randint(1, 10):02d}-{rng.randint(1, 28):02d}",
            siparis_no=f"PO-{rng.randint(1000, 9999)}",
            satirlar=list(satirlar.values()),
        )
        sertifika.son_kullanma_tarihi = f"{int(sertifika.uretim_tarihi[:4]) + 1}{sertifika.uretim_tarihi[4:]}"
        cikti.append(
            UretilenSertifika(
                sertifika=sertifika,
                sablon=sablon,
                dogru=DogruKarar(
                    sertifika_no=no,
                    belge_karari=_belge_karari([revizyon_karari, *dogru.values()]),
                    hata_turu=tur,
                    hata_aciklamasi=aciklama,
                    revizyon=revizyon_karari,
                    satirlar=dogru,
                ),
            )
        )
    return cikti
