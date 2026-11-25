"""Gerçek CoA'ları tedarikçinin ürün şartnamesiyle test test eşleştirir.

Ürün kodu değil, ölçüm hazırlığıdır: her CoA test satırı için şartnamedeki
karşılığını bulur ve sınırların aynı olup olmadığını yazar. Kabul / red kararı
vermez; karar kural motorunun işidir (CLAUDE.md kural 1). Thermo Fisher
sertifikaları için yapılan eşleştirmenin (PR #43) Alfa Aesar ve Spectrum
Chemical sertifikalarına genişletilmiş hâlidir; böylece ölçüm tek bir
tedarikçinin belge düzenine dayanmaz.

Okuma pdfplumber'ın kelime konumlarıyla yapılır (dil modeli yok). Desteklenen
düzenler:

- tablo: başlık satırı olan tablolar ("Test / Limits / Results",
  "Result Name / Units / Specification / Test Value", Spectrum'un
  "Test / Specification (min, max) / Result" tablosu). Çok satırlı hücreler
  dikeyde en yakın test satırına bağlanır.
- sinirsiz: başlıksız "ad  değer" listeleri (eski Alfa Aesar düzeni); sınır
  yoktur. Element ızgaraları ("Al <5  Ba <1 ...") ayrı satırlara açılır,
  ızgaranın altındaki "Values given in ppb" notu birim olarak yazılır.

Şartname tarafında Thermo Fisher / Alfa Aesar "Product Specification"
listesi ve Spectrum'un "Test / Specification (Min, Max)" tablosu okunur.

Durumlar (Thermo eşleştirmesindekiler ve bir yenisi): "var; sınır aynı",
"var; sınır farklı", "var; sertifikada sınır yok", "var; şartnamede sınır
yok" (şartname kalemi var ama sınırı yazılı değil), "şartnamede yok".
Sınırlar yalnız %, ppm ve ppb arasında, kesin oranlarla çevrilerek
karşılaştırılır (ör. "10 ppm max" ile "≤0.001%" aynı); başka birimler metin
olarak karşılaştırılır.

Kullanım:
  python deney/coa_eslestirme.py                    # Thermo Fisher, Alfa Aesar, Spectrum -> data/coa_eslesme/
  python deney/coa_eslestirme.py --tedarikci "Alfa Aesar" --tedarikci "Spectrum Chemical" --cikti eslesme/
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_KLASOR = KOK / "data" / "raw" / "gercek_coa"
VARSAYILAN_CIKTI = KOK / "data" / "coa_eslesme"
# Şartname düzeni okunabilen tedarikçiler (Sigma-Aldrich'in tek şartnamesi başka bir düzende, tek lot: eksik).
VARSAYILAN_TEDARIKCILER = ("Thermo Fisher Scientific", "Alfa Aesar", "Spectrum Chemical")

SINIR_AYNI = "var; sınır aynı"
SINIR_FARKLI = "var; sınır farklı"
SINIRSIZ = "var; sertifikada sınır yok"
SARTNAME_SINIRSIZ = "var; şartnamede sınır yok"
YOK = "şartnamede yok"

SATIR_ALANLARI = [
    "tedarikci", "urun", "katalog", "lot", "sertifika", "sartname", "duzen", "sayfa", "test", "birim",
    "sertifika_siniri", "deger", "sartname_kalemi", "sartname_siniri", "eslesme", "durum", "not",
]
OZET_ALANLARI = [
    "tedarikci", "sertifika", "urun", "katalog", "lot", "sartname", "olcum_kumesi", "duzen", "test",
    "karsilik_var", "sinir_ayni", "sinir_farkli", "sinirsiz", "sartname_sinirsiz", "yok", "elle", "sartname_kalem",
    "testsiz_sartname",
]


# --- PDF'ten satır ve hücreler ---------------------------------------------------------


@dataclass
class Hucre:
    x0: float
    x1: float
    metin: str

    @property
    def orta(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Satir:
    y: float
    hucreler: list[Hucre]
    sayfa: int = 1
    kelimeler: list[Hucre] = field(default_factory=list)
    yukseklik: float = 10.0

    @property
    def metin(self) -> str:
        return "  ".join(h.metin for h in self.hucreler)


def _hucrelere_bol(kelimeler: list[dict], bosluk: float) -> list[Hucre]:
    hucreler: list[Hucre] = []
    for k in sorted(kelimeler, key=lambda k: k["x0"]):
        if hucreler and k["x0"] - hucreler[-1].x1 < bosluk:
            son = hucreler[-1]
            ayrac = "" if k["x0"] - son.x1 <= 0.6 else " "
            son.metin += ayrac + k["text"]
            son.x1 = max(son.x1, k["x1"])
        else:
            hucreler.append(Hucre(k["x0"], k["x1"], k["text"]))
    return hucreler


def _yukseklik(k: dict) -> float:
    return k["bottom"] - k["top"]


def _orta(k: dict) -> float:
    return (k["top"] + k["bottom"]) / 2


def _simge_mi(k: dict, buyuk: dict) -> bool:
    """k, büyük kelimenin hemen yanındaki alt / üst simge mi (H₂O'daki 2, °C'deki o)?"""
    return (
        _yukseklik(k) < 0.8 * _yukseklik(buyuk)
        and abs(_orta(k) - _orta(buyuk)) < _yukseklik(buyuk)
        and (abs(k["x0"] - buyuk["x1"]) < 1.5 or abs(buyuk["x0"] - k["x1"]) < 1.5)
    )


def kelimelerden_satirlar(kelimeler: list[dict], sayfa: int = 1) -> list[Satir]:
    """pdfplumber kelimelerini (x0, x1, top, bottom, text) satırlara ve hücrelere ayırır.

    Alt / üst simgeler (ör. H₂SO₄'teki 2 ve 4, °C'deki o) yanındaki kelimenin
    satırına katılır. Aralarında yazı yüksekliğinden geniş boşluk olan kelimeler
    ayrı hücredir.
    """
    simgeler, digerleri = [], []
    for k in kelimeler:
        (simgeler if any(_simge_mi(k, b) for b in kelimeler if b is not k) else digerleri).append(k)
    gruplar: list[list[dict]] = []
    for k in sorted(digerleri, key=_orta):
        if gruplar and abs(_orta(k) - _orta(gruplar[-1][0])) <= 0.4 * max(_yukseklik(k), _yukseklik(gruplar[-1][0])):
            gruplar[-1].append(k)
        else:
            gruplar.append([k])
    for k in simgeler:
        buyuk = next(b for b in digerleri + simgeler if b is not k and _simge_mi(k, b))
        next((g for g in gruplar if any(x is buyuk for x in g)), gruplar[-1] if gruplar else []).append(k)
    satirlar = []
    for g in gruplar:
        yuk = sorted(_yukseklik(k) for k in g)[len(g) // 2]
        satirlar.append(Satir(min(k["top"] for k in g), _hucrelere_bol(g, 0.9 * yuk), sayfa,
                              _kelime_hucreleri(g), yuk))
    return satirlar


def _kelime_hucreleri(g: list[dict]) -> list[Hucre]:
    """Simgeleri yanındaki kelimeye yapıştırılmış kelime listesi."""
    return _hucrelere_bol(g, 0.61)


def pdf_satirlari(yol: str | Path) -> list[Satir]:
    import pdfplumber

    satirlar: list[Satir] = []
    with pdfplumber.open(str(yol)) as pdf:
        for no, sayfa in enumerate(pdf.pages, 1):
            satirlar += kelimelerden_satirlar(sayfa.extract_words(x_tolerance=1.5), no)
    return satirlar


# --- CoA test satırları ----------------------------------------------------------------


@dataclass
class TestSatiri:
    ad: str
    deger: str = ""
    sinir: str = ""
    birim: str = ""
    duzen: str = ""
    sayfa: int = 1
    izgara: bool = False  # element ızgarasından açıldı

    __test__ = False


AD_BASLIK = re.compile(r"^(Test|Result Name)$", re.I)
SINIR_BASLIK = re.compile(r"^(Limits?|Specifications?)$", re.I)
SONUC_BASLIK = re.compile(r"^(Results?|Test Value)$", re.I)
BIRIM_BASLIK = re.compile(r"^Units?$", re.I)
LOT_SATIRI = re.compile(r"\bLot (No\.?|Number)\b|\bLOT Number\b", re.I)
ALT_BILGI = re.compile(
    r"^(Retest [Dd]ate|Certified by|This document|Values (given )?in|All values given|ND: |Trace [Ii]mpurities|"
    r"Order our|Date printed|Additional Information|Thermo Fisher Scientific expressly|Quality Control|"
    r"Spectrum Chemical Mfg|Products are processed|Note: The data)",
)
IMZA = re.compile(r"Manager|Supervisor|Issued:")
BIRIM_NOTU = re.compile(r"values (?:given )?in (\w+)", re.I)
BOS_DEGER = {".", ""}
# Test olmayan, belge bilgisi satırları (Spectrum tablosunda test gibi yazılır)
BILGI_SATIRI = re.compile(
    r"^(RETEST DATE|DATE OF MANUFACTURE|EXPIRATION DATE|MONOGRAPH EDITION|CERTIFIED HALAL)$", re.I,
)


def _temiz_ad(ad: str) -> str:
    """"@ 25ooC", "at 20^oC" gibi derece yazımlarını "°C" yapar, sondaki ":" işaretini atar."""
    ad = re.sub(r"(\d)\s*\^?o+\s*C\b", r"\1°C", ad)
    return ad.rstrip(":").strip()


ELEMENTLER = {
    "Ag": "Silver", "Al": "Aluminum", "As": "Arsenic", "Au": "Gold", "B": "Boron", "Ba": "Barium",
    "Be": "Beryllium", "Bi": "Bismuth", "Ca": "Calcium", "Cd": "Cadmium", "Ce": "Cerium", "Co": "Cobalt",
    "Cr": "Chromium", "Cs": "Cesium", "Cu": "Copper", "Dy": "Dysprosium", "Er": "Erbium", "Eu": "Europium",
    "Fe": "Iron", "Ga": "Gallium", "Gd": "Gadolinium", "Ge": "Germanium", "Hf": "Hafnium", "Ho": "Holmium",
    "In": "Indium", "K": "Potassium", "La": "Lanthanum", "Li": "Lithium", "Mg": "Magnesium", "Mn": "Manganese",
    "Mo": "Molybdenum", "Na": "Sodium", "Nb": "Niobium", "Nd": "Neodymium", "Ni": "Nickel", "Pb": "Lead",
    "Pd": "Palladium", "Pr": "Praseodymium", "Pt": "Platinum", "Rb": "Rubidium", "Re": "Rhenium",
    "Rh": "Rhodium", "Ru": "Ruthenium", "Sb": "Antimony", "Sc": "Scandium", "Si": "Silicon", "Sm": "Samarium",
    "Sn": "Tin", "Sr": "Strontium", "Ta": "Tantalum", "Tb": "Terbium", "Te": "Tellurium", "Ti": "Titanium",
    "Tl": "Thallium", "Tm": "Thulium", "V": "Vanadium", "W": "Tungsten", "Y": "Yttrium", "Yb": "Ytterbium",
    "Zn": "Zinc", "Zr": "Zirconium",
}
ELEMENT_ADLARI = {ad.lower(): sembol for sembol, ad in ELEMENTLER.items()}


def element_sembolu(ad: str) -> str | None:
    ad = ad.strip()
    if ad in ELEMENTLER:
        return ad
    return ELEMENT_ADLARI.get(ad.lower())


def _alt_baslik_mi(ad: str) -> bool:
    """"195 nm", "+20 mesh" gibi bir bölüm başlığının altındaki satır adı mı?"""
    return bool(re.match(r"^[+-]?\d", ad))


def _baslik_bul(satirlar: list[Satir]) -> int | None:
    for i, s in enumerate(satirlar):
        metinler = [h.metin for h in s.hucreler]
        if metinler and AD_BASLIK.match(metinler[0]) and any(SONUC_BASLIK.match(m) for m in metinler[1:]):
            return i
    return None


def _govde(satirlar: list[Satir], bas: int) -> list[Satir]:
    govde = []
    for s in satirlar[bas:]:
        if govde and IMZA.search(s.metin):
            break  # imza satırı (Thermo / Acros: "C. Wygaerts, QA Manager")
        if s.hucreler and ALT_BILGI.match(s.hucreler[0].metin):
            if BIRIM_NOTU.search(s.metin) or s.hucreler[0].metin.startswith("ND:"):
                govde.append(s)  # birim notu ızgaraya uygulanır, sonra durulur
                continue
            if govde:
                break
            continue
        govde.append(s)
    return govde


def _bolum_basligi_mi(satirlar: list[Satir], i: int) -> bool:
    ad = satirlar[i].hucreler[0].metin
    if ad.endswith(":"):
        return True
    sonraki = satirlar[i + 1] if i + 1 < len(satirlar) else None
    if sonraki is None or not sonraki.hucreler:
        return False
    ilk = sonraki.hucreler[0].metin
    return _alt_baslik_mi(ilk) or (len(sonraki.hucreler) == 1 and ilk.endswith(":"))


def _parcalari_bagla(satirlar: list[tuple[float, object, dict]], parcalar: list[tuple[float, str, str]],
                     bosluk: float = 15.0, en_uzak: float = 30.0) -> None:
    """Ad hücresi olmayan satırlardaki parçaları (çok satırlı hücreler) test satırlarına bağlar.

    Aynı sütunda alt alta duran parçalar bir blok sayılır; blok dikey ortasına en
    yakın test satırına gider (eşitlikte alttaki). Çok satırlı hücreler satırına
    göre dikeyde ortalandığı için bu, hücreyi doğru satıra bağlar.
    """
    if not satirlar:
        return
    for sutun_adi in {p[1] for p in parcalar}:
        bloklar: list[list[tuple[float, str]]] = []
        for y, _, metin in sorted((p for p in parcalar if p[1] == sutun_adi), key=lambda p: p[0]):
            if metin.strip() in BOS_DEGER:
                continue
            if bloklar and y - bloklar[-1][-1][0] <= bosluk:
                bloklar[-1].append((y, metin))
            else:
                bloklar.append([(y, metin)])
        for blok in bloklar:
            orta = (blok[0][0] + blok[-1][0]) / 2
            hedef = min(satirlar, key=lambda r: (abs(r[0] - orta), -r[0]))
            if abs(hedef[0] - orta) <= en_uzak:
                hedef[2].setdefault(sutun_adi, []).extend(blok)


def _birlestir(parcalar: list[tuple[float, str]]) -> str:
    return " ".join(m for _, m in sorted(parcalar, key=lambda p: p[0]) if m not in BOS_DEGER).strip()


def _min_max(mn: str, mx: str) -> str:
    if mn and mx:
        return f"{mn} - {mx}"
    return f"min {mn}" if mn else (f"max {mx}" if mx else "")


def tablo_satirlari(satirlar: list[Satir]) -> list[TestSatiri]:
    """Başlık satırı olan CoA tablosunu okur."""
    bas = _baslik_bul(satirlar)
    assert bas is not None
    baslik = satirlar[bas]
    ad_x = baslik.hucreler[0].x0
    sutunlar: dict[str, float] = {}
    for h in baslik.hucreler[1:]:
        for ad, desen in (("sinir", SINIR_BASLIK), ("deger", SONUC_BASLIK), ("birim", BIRIM_BASLIK)):
            if desen.match(h.metin):
                sutunlar[ad] = h.orta
    govde = satirlar[bas + 1:]
    # Spectrum: "min  max" alt başlığı sınır sütununu ikiye böler.
    alt_hucreler: list[Hucre] = []
    if govde and [h.metin.lower() for h in govde[0].hucreler] in (["min", "max"], ["min max"]):
        alt = alt_hucreler = govde.pop(0).hucreler
        if len(alt) == 2:
            sutunlar.pop("sinir", None)
            sutunlar["min"], sutunlar["max"] = alt[0].orta, alt[1].orta
    govde = _govde(govde, 0)
    veri_basi = min([h.x0 for h in baslik.hucreler[1:]] + [h.x0 for h in alt_hucreler])

    def sutun(h: Hucre) -> str:
        ad = min(sutunlar, key=lambda ad: abs(sutunlar[ad] - h.orta))
        if ad in ("min", "max") and not TEK_SAYI.match(h.metin):
            return "sinir"  # yazılı sınır ya da aralık: min / max sütunlarına yayılır
        return ad

    satir_listesi: list[tuple[float, TestSatiri, dict[str, list[str]]]] = []
    parcalar: list[tuple[float, str, str]] = []
    bolum = ""
    for i, s in enumerate(govde):
        ilk = s.hucreler[0]
        if ALT_BILGI.match(ilk.metin):
            continue  # "ND: Not detected" gibi dipnotlar
        ad_hucresi = ilk.x0 < ad_x + 12 or (ilk.x0 < veri_basi - 50 and ilk.metin[:1].isalpha())
        if not ad_hucresi:
            parcalar += [(s.y, sutun(h), h.metin) for h in s.hucreler]
            continue
        digerleri = s.hucreler[1:]
        if ilk.x0 >= ad_x + 12 and len(digerleri) == 1:
            # tablonun altında girintili "ad  sonuç" satırı (ör. Alfa Aesar 033361): sınır yok
            hucreler = {"deger": [(s.y, digerleri[0].metin)]}
        else:
            hucreler = {}
            for h in digerleri:
                hucreler.setdefault(sutun(h), []).append((s.y, h.metin))
        doluluk = [v for k, v in hucreler.items() if any(x not in BOS_DEGER for _, x in v)]
        if not doluluk and hucreler:
            # Spectrum'un "." ile işaretli bölüm satırı (ör. "ABSORBANCE:  .  .", "VOLATILE IMPURITIES  .  .")
            if _bolum_basligi_mi(govde, i):
                bolum = ilk.metin.rstrip(":. ")
            continue
        if not doluluk and len(ilk.metin) > 80:
            break  # tablonun altındaki açıklama paragrafı
        if not doluluk:
            if _bolum_basligi_mi(govde, i):
                bolum = ilk.metin.rstrip(":. ")
                continue
            if satir_listesi and not ilk.metin.isupper():
                satir_listesi[-1][1].ad += " " + ilk.metin  # adın devamı
                continue
        ad = ilk.metin
        if bolum and _alt_baslik_mi(ad):
            ad = f"{bolum}: {ad}"
        elif bolum:
            bolum = ""
        t = TestSatiri(ad=_temiz_ad(ad), duzen="tablo", sayfa=s.sayfa)
        satir_listesi.append((s.y, t, hucreler))
    _parcalari_bagla(satir_listesi, parcalar, bosluk=1.25 * baslik.yukseklik)
    sonuc = []
    for y, t, hucreler in satir_listesi:
        temiz = {k: _birlestir(v) for k, v in hucreler.items()}
        t.deger = temiz.get("deger", "")
        t.birim = temiz.get("birim", "")
        if temiz.get("sinir"):
            t.sinir = temiz["sinir"]
        else:
            t.sinir = _min_max(temiz.get("min", ""), temiz.get("max", ""))
        sonuc.append(t)
    return sonuc


IZGARA_DEGERI = re.compile(r"^([<>≤-]|[<>≤]?\d[\d.,]*(-\d[\d.,]*)?|ND)$")


def _izgara_cifti(kelimeler: list[Hucre]) -> list[tuple[str, str]] | None:
    """Element ızgarası satırını ("Al <5  Ba <1 ...") (sembol, değer) çiftlerine açar; ızgara değilse None.

    Değeri olmayan element (ör. ana bileşen Na, altında "Metal" yazar) boş değerle döner.
    """
    parcalar = [k.metin for k in kelimeler]
    semboller = [p for p in parcalar if element_sembolu(p)]
    if len(semboller) < 2 or not all(element_sembolu(p) or IZGARA_DEGERI.match(p) for p in parcalar):
        return None
    if not element_sembolu(parcalar[0]):
        return None
    ciftler: list[list[str]] = []
    for p in parcalar:
        if element_sembolu(p) and (not ciftler or ciftler[-1][1][-1:] not in ("<", ">", "≤", "-")):
            ciftler.append([p, ""])
        else:
            ciftler[-1][1] = (ciftler[-1][1] + " " + p).strip()
    return [(a, b) for a, b in ciftler]


def sinirsiz_satirlar(satirlar: list[Satir]) -> list[TestSatiri]:
    """Başlıksız "ad  değer" listesini (sınır yok) okur."""
    bas = next((i + 1 for i, s in enumerate(satirlar) if LOT_SATIRI.search(s.metin)), 0)
    govde = [s for s in _govde(satirlar, bas) if s.metin.strip() != "Analysis"]
    sonuc: list[TestSatiri] = []
    deger_x: float | None = None
    bolum = ""
    bolum_devam = False
    izgara_birimi = ""
    for i, s in enumerate(govde):
        if BIRIM_NOTU.search(s.metin):
            izgara_birimi = BIRIM_NOTU.search(s.metin).group(1)
            continue
        if s.hucreler[0].metin.startswith("ND:"):
            continue
        ciftler = _izgara_cifti(s.kelimeler)
        if ciftler is not None:
            for ad, deger in ciftler:
                if ad == "Metal":
                    continue
                sonuc.append(TestSatiri(ad=ad, deger=deger or "matris (Metal)", duzen="sınırsız", sayfa=s.sayfa,
                                        izgara=True))
            continue
        if len(s.hucreler) == 1 and (m := re.fullmatch(r"(.+\?)\s+(\S+)", s.hucreler[0].metin)):
            sonuc.append(TestSatiri(ad=m.group(1), deger=m.group(2), duzen="sınırsız", sayfa=s.sayfa))
            continue
        if len(s.hucreler) == 1:
            h = s.hucreler[0]
            if h.metin == "Metal":
                continue
            if _bolum_basligi_mi(govde, i):
                bolum = (bolum + " " + h.metin).strip() if bolum and bolum_devam else h.metin
                bolum_devam = True
                continue
            if sonuc and deger_x is not None and h.x0 >= deger_x - 5:
                sonuc[-1].deger += " " + h.metin
            elif sonuc:
                sonuc[-1].ad += " " + h.metin
            continue
        bolum_devam = False
        ad, deger = s.hucreler[0].metin, " ".join(h.metin for h in s.hucreler[1:])
        deger_x = s.hucreler[1].x0
        if bolum and _alt_baslik_mi(ad):
            ad = f"{bolum.rstrip(':')}: {ad}"
        else:
            bolum = ""
        sonuc.append(TestSatiri(ad=_temiz_ad(ad), deger=deger, duzen="sınırsız", sayfa=s.sayfa))
    for t in sonuc:
        if t.izgara and izgara_birimi:
            t.birim = izgara_birimi
    return sonuc


def coa_satirlari(satirlar: list[Satir]) -> list[TestSatiri]:
    """CoA'nın test satırları; düzen başlık satırına göre seçilir. Tarih satırları atılır."""
    testler = tablo_satirlari(satirlar) if _baslik_bul(satirlar) is not None else sinirsiz_satirlar(satirlar)
    return [t for t in testler if not BILGI_SATIRI.match(t.ad)]


# --- Şartname kalemleri ----------------------------------------------------------------


@dataclass
class Kalem:
    ad: str
    sinir: str
    sayfa: int = 1


def _urun_sartnamesi(satirlar: list[Satir]) -> list[Kalem]:
    """Thermo Fisher / Alfa Aesar "Product Specification" listesi ("Ad:  sınır")."""
    bas = next(i for i, s in enumerate(satirlar)
               if s.metin.strip() == "Product Specification" and s.hucreler[0].x0 < 100)
    govde = []
    for s in satirlar[bas + 1:]:
        if s.metin.startswith("Date Of Print"):
            break
        if s.metin.strip() != "Product Specification":
            govde.append(s)
    # değer sütunu: ":" ile biten addan sonraki ilk kelimenin konumu
    xler = [s.hucreler[1].x0 for s in govde if len(s.hucreler) > 1 and s.hucreler[0].metin.endswith(":")]
    deger_x = min(xler, key=xler.count) if xler else 180
    kalemler: list[Kalem] = []
    eksik_ad = False
    for s in govde:
        sol_k = [k for k in s.kelimeler if k.x0 < deger_x - 2]
        sag_k = [k for k in s.kelimeler if k.x0 >= deger_x - 2]
        sol = " ".join(k.metin for k in sol_k).strip()
        sag = " ".join(k.metin for k in sag_k).strip()
        if sol and not sol.endswith(":") and ":" in f"{sol} {sag}".rstrip(":") and not eksik_ad:
            # "Assay from Supplier's CofA: ≥99.0% (GC)": ad değer sütununa taşmış
            ad, _, deger = (sol + " " + sag).partition(":")
            kalemler.append(Kalem(ad.strip(), deger.strip(), s.sayfa))
            continue
        if sol and eksik_ad:
            kalemler[-1].ad += " " + sol
            kalemler[-1].sinir = (kalemler[-1].sinir + " " + sag).strip()
            eksik_ad = not sol.endswith(":")
        elif sol:
            kalemler.append(Kalem(sol, sag, s.sayfa))
            eksik_ad = not sol.endswith(":")
        elif sag and kalemler:
            kalemler[-1].sinir += " " + sag
    for k in kalemler:
        k.ad = k.ad.rstrip(":").strip()
    return [k for k in kalemler if k.ad != "Comment"]


def _spectrum_sartnamesi(satirlar: list[Satir]) -> list[Kalem]:
    """Spectrum "Test / Specification (Min, Max)" tablosu; birden çok sayfa olabilir.

    Sayısal sınırlar Min / Max sütununa göre "min X", "max Y" ya da "X - Y" olur;
    yazılı sınırlar (ör. "SOLUTION IS CLEAR") olduğu gibi alınır.
    """
    kalemler: list[Kalem] = []
    i = 0
    while i < len(satirlar):
        s = satirlar[i]
        if not (s.hucreler and s.hucreler[0].metin == "Test" and any(h.metin == "Specification" for h in s.hucreler)):
            i += 1
            continue
        alt = satirlar[i + 1].hucreler
        mn, mx = alt[0].orta, alt[-1].orta
        ad_x = min(x.hucreler[0].x0 for x in satirlar[i + 2:i + 6])
        j = i + 2
        sayfa_satirlari: list[tuple[float, Kalem, dict]] = []
        parcalar: list[tuple[float, str, str]] = []
        bolum = ""
        while j < len(satirlar) and satirlar[j].sayfa == s.sayfa:
            t = satirlar[j]
            if ALT_BILGI.match(t.hucreler[0].metin) or "Spectrum Chemical Mfg" in t.metin:
                break
            ilk = t.hucreler[0]
            hucreler = t.hucreler
            if ilk.x0 <= ad_x + 12:
                ad = ilk.metin
                hucreler = t.hucreler[1:]
                if ad.endswith(":") and not hucreler:
                    bolum = ad.rstrip(":")
                    j += 1
                    continue
                if bolum and (_alt_baslik_mi(ad) or re.match(r"^(EACH|TOTAL|METHANOL)\b", ad)):
                    ad = f"{bolum}: {ad}"
                else:
                    bolum = ""
                sayfa_satirlari.append((t.y, Kalem(ad, "", t.sayfa), {}))
            for h in hucreler:
                if TEK_SAYI.match(h.metin) and abs(h.orta - mn) < abs(h.orta - mx) and abs(h.orta - mn) < 40:
                    sut = "min"
                elif TEK_SAYI.match(h.metin) and abs(h.orta - mx) < 40:
                    sut = "max"
                else:
                    sut = "metin"
                parcalar.append((t.y, sut, h.metin))
            j += 1
        _parcalari_bagla(sayfa_satirlari, parcalar, bosluk=1.25 * s.yukseklik)
        for _, k, d in sayfa_satirlari:
            m, x, metin = (_birlestir(d.get(a, [])) for a in ("min", "max", "metin"))
            if metin:
                k.sinir = " ".join(p for p in (m, metin, x) if p)
            else:
                k.sinir = _min_max(m, x)
            kalemler.append(k)
        i = j
    return kalemler


def sartname_kalemleri(satirlar: list[Satir]) -> list[Kalem]:
    if any(s.metin.strip() == "Product Specification" for s in satirlar):
        kalemler = _urun_sartnamesi(satirlar)
    else:
        kalemler = _spectrum_sartnamesi(satirlar)
    return [k for k in kalemler if not BILGI_SATIRI.match(k.ad)]


# --- Ad ve sınır normalleştirme ---------------------------------------------------------


def _ascii(s: str) -> str:
    s = s.replace("º", "°").replace("₂", "2").replace("₄", "4")
    return unicodedata.normalize("NFKC", s)


def ad_normal(s: str) -> str:
    s = _ascii(s).lower().replace("colour", "color").replace("supplier's", "suppliers")
    return re.sub(r"[^a-z0-9]", "", s)


def ad_kok(s: str) -> str:
    """Parantezli niteleyiciler ve "@ 25 C", "at 20°C" gibi koşullar atılmış ad."""
    s = _ascii(s)
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", s)
    s = re.sub(r"\s(@|at)\s.*$", " ", s, flags=re.I)
    s = re.sub(r",.*$", " ", s)
    return ad_normal(s)


SAYI = re.compile(r"\d+(?:[.,]\d+)?|\.\d+")
TEK_SAYI = re.compile(r"^[<>≤≥]?\s*(\d+(?:[.,]\d+)?|\.\d+)\s*[%a-zA-Zµ/°.]*$")


def sinir_normal(s: str) -> str:
    """Karşılaştırma için sınır metni: yön işareti, sayılar ve birim; boşluksuz, küçük harf."""
    s = _ascii(s).lower().strip()
    s = s.replace(">=", "≥").replace("<=", "≤").replace("=<", "≤").replace("–", "-").replace("—", "-")
    s = s.replace("colour", "color").replace("wt%", "%").replace("w/v%", "%")
    s = re.sub(r"(\d)\s*(\^?o|\?|°)\s*c\b", r"\1°c", s)
    s = re.sub(r"\s@\s?", " at ", s)
    s = re.sub(r"(\d)\s+to\s+(\d)", r"\1-\2", s)
    s = re.sub(r"\((non-)?u\.s\.\s*specification\)|\[(us|eu)\]", "", s)
    s = re.sub(r"\(\s*corrected for water\)|\(gc\)", "", s)
    if re.fullmatch(r"(to pass test|passes test|p\.?t\.?|passes|conforms)", s.strip(" .")):
        return "pt"
    m = re.fullmatch(r"(.*?)\s*\bmin\.?$", s) or re.fullmatch(r"min\.?\s*(.*)", s)
    if m and SAYI.search(m.group(1)):
        s = "≥" + m.group(1)
    m = re.fullmatch(r"(.*?)\s*\bmax\.?$", s) or re.fullmatch(r"max\.?\s*(.*)", s)
    if m and SAYI.search(m.group(1)):
        s = "≤" + m.group(1)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"(\d)\.0+(?=\D|$)", r"\1", s)  # 99.0% -> 99%
    s = re.sub(r"(\.\d*?[1-9])0+(?=\D|$)", r"\1", s)  # 0.50% -> 0.5%
    return s


ORAN = {"%": 1e-2, "ppm": 1e-6, "ppb": 1e-9}


ORANSAL_IFADE = re.compile(r"[≤≥]?\s*\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?\s*(?:%|ppm|ppb)")


def _deger_kismi(sinir: str) -> str:
    """Şartname sınırının değer kısmı.

    "Cl: ≤2.0 ppm" -> "≤2.0 ppm"; "... sulfuric acid P.T." -> "P.T.";
    "Within 94.0-96.0% (V/V) methanol ..." -> "94.0-96.0%".
    """
    if re.search(r"\bP\.\s?T\.?$|passes test$", sinir.strip(), re.I):
        return "P.T."
    if oransal_sinir(sinir):
        return sinir
    parca = re.split(r"[:;]\s*", sinir)
    son = parca[-1].strip()
    if len(parca) > 1:
        return son
    m = ORANSAL_IFADE.search(sinir)
    return m.group().strip() if m else sinir


def oransal_sinir(s: str) -> tuple[str, tuple[float, ...]] | None:
    """%, ppm, ppb sınırını (yön, kesir değerleri) olarak çözer; çözemezse None.

    Çevrim kesin oranlarla yapılır (1 ppm = 1e-6, 1 % = 1e-2); dil modeli yok.
    """
    n = sinir_normal(s)
    m = re.fullmatch(r"([≤≥]?)(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?(%|ppm|ppb)(?:\(.*\))?", n)
    if not m:
        return None
    yon, a, b, birim = m.groups()
    degerler = tuple(round(float(x) * ORAN[birim], 15) for x in (a, b) if x)
    return ("aralık" if b else yon), degerler


def sinir_karsilastir(sertifika: str, sartname: str) -> str:
    """"aynı", "aynı (birim çevrilerek)", "aynı (yön yazılmamış)" ya da "farklı"."""
    a, b = sinir_normal(sertifika), sinir_normal(sartname)
    if a == b or a == sinir_normal(_deger_kismi(sartname)):
        return "aynı"
    oa, ob = oransal_sinir(sertifika), oransal_sinir(_deger_kismi(sartname))
    if oa and ob and oa[1] == ob[1] and (oa[0] == ob[0] or not oa[0]):
        return "aynı (yön yazılmamış)" if not oa[0] and ob[0] else "aynı (birim çevrilerek)"
    # Spectrum CoA'ları yönü bazen yazmaz ("0.50%" = en çok 0.50%)
    if a.lstrip("≤≥") == b.lstrip("≤≥") and a[:1] not in "≤≥" and b[:1] in "≤≥":
        return "aynı (yön yazılmamış)"
    return "farklı"


def sikilik(sertifika: str, sartname: str) -> str:
    """İki tek yönlü oransal sınırdan hangisi sıkı: "sertifika daha sıkı" / "sertifika daha gevşek" / ""."""
    oa, ob = oransal_sinir(sertifika), oransal_sinir(_deger_kismi(sartname))
    if not (oa and ob) or oa[0] != ob[0] or oa[0] not in ("≤", "≥") or oa[1] == ob[1]:
        return ""
    siki = oa[1][0] < ob[1][0] if oa[0] == "≤" else oa[1][0] > ob[1][0]
    return "sertifika daha sıkı" if siki else "sertifika daha gevşek"


def sinirlar_ayni(sertifika: str, sartname: str) -> bool:
    return sinir_karsilastir(sertifika, sartname) != "farklı"


SICAKLIK = re.compile(r"(\d+(?:\.\d+)?)\s*(?:°|º|\?|\^?o)\s*C\b|(\d+)\s*C\b")


def _sicakliklar(s: str) -> set[str]:
    return {a or b for a, b in SICAKLIK.findall(s)}


# --- Eşleştirme -------------------------------------------------------------------------

# Adı farklı ama aynı ölçümü gösteren satırlar: CoA adı (ad_normal) -> şartname adları (ad_normal).
# Bütün tedarikçiler için geçerli olanlar; ürüne özgü olanlar ELLE_URUN'de.
ELLE: dict[str, list[str]] = {
    "water": ["watercontentkarlfischertitration", "watercontent", "residualwater", "wateruspwater"],
    "waterkf": ["watercontentkarlfischertitration"],
    "waterkfcoulometric": ["residualwater"],
    "watervolumetrickf": ["watercontentkarlfischertitration"],
    "evaporationresidue": ["residueonevaporation"],
    "residueafterevaporation": ["residueonevaporation"],
    "appearance": ["appearancecolor"],
    "assay": ["assaygc", "assayfromsupplierscofa"],
    "assaygc": ["assayfromsupplierscofa"],
    "assaygcfid": ["assaygc"],
    "identificationbyir": ["identificationftir"],
    "irspectrum": ["identificationftir"],
    "acidity": ["freeacidtitration"],
    "titrableacid": ["freeacidtitration"],
    "colorapha": ["colorapha"],
    "colorahpa": ["colorapha"],
    "colorptco": ["colorapha"],
    "refractiveindexn20d": ["refractiveindex"],
    "refractiveindexat20c": ["refractiveindex"],
    "refractiveindexat25c": ["refractiveindex"],
    "specificgravityat20c": ["specificgravity"],
    "chloride": ["chloridecontent", "impuritycontent"],
    "phosphate": ["impuritycontent"],
    "substancesdarkenedbyh2so4": ["impuritycontent"],
    "sulfurcompoundsass": ["impuritycontent"],
    "sulfurcompounds": ["impuritycontent"],
    "particlecount10umandgreater": ["particlesize"],
    "particles10umandgreater": ["particlesize"],
    "particles05umandgreater": ["particlesize"],
    "arsenicandantimonyasas": ["tracemetal", "elementalanalysis"],
    "purity": ["totalmetalimpurities"],
    "assaynitrite": ["assayspecial"],
    "assayna": ["assayspecial"],
    "concentration": ["concentration"],
    "puritygc": ["assaygc"],
    "totalalkalinity": ["alkalinityasnaoh"],
}
ELLE["water"] = ELLE["water"] + ["waterbydifference"]
# (katalog, CoA adı) -> şartname adları
ELLE_URUN: dict[tuple[str, str], list[str]] = {
    ("223230025", "assay"): ["titrationiodometric"],
    ("014103", "sio2"): ["assay", "assayunspecified"],
    ("014103", "na2o"): ["assay"],
    ("014106", "sio2"): ["assayunspecified"],
    ("014106", "na2o"): ["assayunspecified"],
    ("014106", "assay"): ["assayunspecified"],
    ("019353", "assaygcasnhexane"): ["assaygc"],
    ("019353", "assaygcassaturatedc6hydrocarbons"): ["assaygc"],
    ("019353", "assaygcasc6hydrocarbons"): ["assaygc"],
    ("019402", "totalofpmoxylenetolueneandethylbenzenegc"): ["assaygc"],
    ("033361", "methanolandethanolspeciallydenaturedalcoholformula3a200proof"): ["assaygc"],
    ("033361", "methanolandethylalcoholsda3a200proof"): ["assaygc"],
    ("033361", "isopropylalcohol"): ["assaygc"],
    ("IS115", "assayc3h8o"): ["assayusp"],
    ("IS115", "acidity"): ["acidityusp", "acidityjp"],
    ("IS115", "nonvolatileresidue"): ["limitofnonvolatileimpuritiesusp"],
    ("IS115", "individualimpurity"): [
        "limitofvolatileimpuritiesuspeachotherindividualknownimpurity",
        "limitofvolatileimpuritiesuspeachindividualunspecifiedimpurity",
    ],
    ("IS115", "totalimpurities"): ["limitofvolatileimpuritiesusptotalimpurities"],
    ("IS115", "identificationa"): ["identificationauspa"],
    ("IS115", "identificationb"): ["identificationbuspb"],
    ("IS115", "identification"): ["identificationauspa", "identificationbuspb", "identificationcuspc",
                                  "identificationdjp1", "identificationejp2"],
    ("IS115", "absorbance"): ["curve"] + [f"ultravioletabsorptionusp{n}nm" for n in (230, 250, 270, 290, 310)],
    ("IS115", "residualsolvents"): ["residualsolvents"],
}
# Şartnamede tek kalemle sınırlanan toplam (ör. "Total Metal Impurities"): ızgaradaki her element ona bağlanır.
TOPLAM_KALEM = {"044227": "totalmetalimpurities"}


def _bilesen(sinir: str) -> str | None:
    m = re.match(r"^([A-Za-z][A-Za-z0-9 ()₂₄]+?)[:;]", sinir)
    return ad_normal(m.group(1)) if m else None


def _elementi_icerir(kalem: Kalem, sembol: str) -> bool:
    metin = _ascii(kalem.sinir)
    ad = ELEMENTLER[sembol]
    return bool(re.search(rf"(?<![A-Za-z]){sembol}(?![a-z])", metin)) or ad.lower() in metin.lower()


ES_ANLAMLI = {"cl": "chloride", "po4": "phosphate", "sulfuric": "sulfur", "h2so4": "sulfur", "hexane": "hexane",
              "nhexane": "hexane", "c6": "c6", "na2o": "na2o", "sio2": "sio2"}


def _kelimeler(s: str) -> set[str]:
    """Aday seçimi için anlamlı kelimeler: sayılar ve kısa bağlaçlar atılır, element adları sembole çevrilir."""
    kelimeler = {k for k in re.findall(r"[a-z0-9]+", _ascii(s).lower())
                 if not k.isdigit() and k not in ("and", "of", "the", "for", "all", "as", "at")}
    return {ES_ANLAMLI.get(k, ELEMENT_ADLARI.get(k, k).lower()) for k in kelimeler}


def _alt_ad_esler(t_ad: str, k_ad: str) -> bool:
    """"UV absorbance vs H2O: 195 nm" ile "Optical Absorbance at: 195 nm" gibi alt satırlar."""
    a = re.search(r":\s*([+-]?\d+\s*nm)\b", t_ad, re.I)
    return bool(a) and bool(re.search(rf"\b{re.escape(a.group(1).replace(' ', ''))}", k_ad.replace(" ", ""), re.I))


@dataclass
class Eslesme:
    kalemler: list[int] = field(default_factory=list)
    tur: str = ""


def adaylar(t: TestSatiri, kalemler: list[Kalem], katalog: str) -> Eslesme:
    """Bir CoA satırının şartnamedeki aday kalemleri ve eşleşme türü."""
    ad = ad_normal(t.ad)
    kok = ad_kok(t.ad)
    sembol = element_sembolu(t.ad) if t.izgara or element_sembolu(t.ad) else None
    if sembol:
        bulunan = [i for i, k in enumerate(kalemler) if _elementi_icerir(k, sembol)]
        if bulunan:
            return Eslesme(bulunan, "element")
        if katalog in TOPLAM_KALEM:
            return Eslesme([i for i, k in enumerate(kalemler) if ad_normal(k.ad) == TOPLAM_KALEM[katalog]], "toplam")
        return Eslesme()
    # bileşen satırı: "Assay | Sodium Chloride: Report" <-> "Impurity content: Sodium Chloride ..."
    b = _bilesen(t.sinir)
    if b:
        bulunan = [i for i, k in enumerate(kalemler) if _bilesen(k.sinir) == b]
        tur = "ad" if bulunan and all(ad_normal(kalemler[i].ad) == ad for i in bulunan) else "bileşen"
        if not bulunan:
            hedef = ELLE.get(b, [])
            bulunan = [i for i, k in enumerate(kalemler) if _bilesen(k.sinir) in hedef or ad_normal(k.ad) in hedef]
            tur = "elle"
        if bulunan:
            return Eslesme(bulunan, tur)
    # bölüm altı satırlar (dalga boyu): "UV absorbance: 195 nm" <-> "Optical Absorbance at: 195 nm ≤1.000"
    if re.search(r":\s*\d+\s*nm", t.ad):
        bulunan = [i for i, k in enumerate(kalemler) if _alt_ad_esler(t.ad, k.ad + ": " + k.sinir)]
        if bulunan:
            return Eslesme(bulunan, "ad")
    bulunan = [i for i, k in enumerate(kalemler) if ad_normal(k.ad) == ad]
    if bulunan:
        return Eslesme(bulunan, "ad")
    # bileşen: "Impurity content: Cl: ≤2.0 ppm" <-> "Chloride"
    bulunan = [i for i, k in enumerate(kalemler) if _bilesen(k.sinir) in (ad, kok)]
    if bulunan:
        return Eslesme(bulunan, "bileşen")
    bulunan = [i for i, k in enumerate(kalemler) if ad_kok(k.ad) == kok and kok]
    if bulunan:
        return Eslesme(bulunan, "ad")
    hedef = ELLE_URUN.get((katalog, ad)) or ELLE_URUN.get((katalog, kok)) or ELLE.get(ad) or ELLE.get(kok) or []
    bulunan = [i for i, k in enumerate(kalemler) if ad_normal(k.ad) in hedef or ad_kok(k.ad) in hedef]
    if bulunan:
        return Eslesme(bulunan, "elle")
    return Eslesme()


def _daralt(t: TestSatiri, kalemler: list[Kalem], secilen: list[int]) -> list[int]:
    """Birden çok aday varsa sınırı aynı olanı, yoksa en çok ortak kelimesi olanı seçer."""
    if len(secilen) < 2:
        return secilen
    if t.sinir:
        ayni = [i for i in secilen if sinirlar_ayni(t.sinir, kalemler[i].sinir)]
        if ayni:
            return ayni
    tk = _kelimeler(t.ad + " " + t.sinir + " " + t.deger)
    puanlar = {i: len(tk & _kelimeler(kalemler[i].ad + " " + kalemler[i].sinir)) for i in secilen}
    en = max(puanlar.values())
    enler = [i for i in secilen if puanlar[i] == en]
    return enler if len(enler) < len(secilen) else secilen


def _birimli(sinir: str, birim: str) -> str:
    """Birim ayrı sütundaysa (Thermo "Units") sınırdaki son sayının arkasına ekler.

    "98.5 to 101.5 (on dry substance)" + "%" -> "98.5 to 101.5 % (on dry substance)".
    """
    sayilar = list(re.finditer(r"(?<![A-Za-z\d.])\d+(?:[.,]\d+)?", sinir))
    if not birim or birim in sinir or not sayilar:
        return sinir
    son = sayilar[-1].end()
    return f"{sinir[:son]} {birim}{sinir[son:]}"


def eslestir(testler: list[TestSatiri], kalemler: list[Kalem], katalog: str) -> list[dict]:
    """Her CoA satırı için şartname karşılığı, eşleşme türü ve durum."""
    sonuc = []
    for t in testler:
        e = adaylar(t, kalemler, katalog)
        secilen = _daralt(t, kalemler, e.kalemler) if e.tur != "toplam" else e.kalemler
        notlar: list[str] = []
        sinir = _birimli(t.sinir, t.birim)
        sinir_yalin = re.sub(r"^[A-Za-z ]+:\s*", "", t.sinir).strip().lower()
        karsilastirmalar = [sinir_karsilastir(sinir, kalemler[i].sinir) for i in secilen] if t.sinir else []
        if not secilen:
            durum = YOK
        elif not t.sinir or re.fullmatch(r"(report|as reported|per lot)", sinir_yalin):
            durum = SINIRSIZ
        elif all(not kalemler[i].sinir for i in secilen):
            durum = SARTNAME_SINIRSIZ
        elif any(k != "farklı" for k in karsilastirmalar):
            durum = SINIR_AYNI
            notlar += sorted({k[6:-1] for k in karsilastirmalar if k.startswith("aynı (")})
        else:
            durum = SINIR_FARKLI
            notlar += sorted({n for i in secilen if (n := sikilik(sinir, kalemler[i].sinir))})
        sc = _sicakliklar(t.ad + " " + t.sinir)
        sk = set().union(set(), *(_sicakliklar(kalemler[i].ad + " " + kalemler[i].sinir) for i in secilen))
        if sc and sk and not sc & sk:
            fark = f"{'/'.join(sorted(sc))} °C ↔ {'/'.join(sorted(sk))} °C"
            notlar.append(f"ölçüm sıcaklığı farklı ({fark})")
        not_ = "; ".join(notlar)
        if len(secilen) > 1 and e.tur != "toplam":
            not_ = (not_ + "; " if not_ else "") + f"{len(secilen)} şartname kalemi aday"
        if e.tur == "toplam":
            not_ = "şartname yalnız toplamı sınırlıyor"
        sonuc.append({
            "test": t.ad, "birim": t.birim, "sertifika_siniri": t.sinir, "deger": t.deger, "duzen": t.duzen,
            "sayfa": t.sayfa,
            "sartname_kalemi": " | ".join(kalemler[i].ad for i in secilen),
            "sartname_siniri": " | ".join(kalemler[i].sinir for i in secilen),
            "eslesme": e.tur if secilen else "", "durum": durum, "not": not_, "_kalemler": secilen,
        })
    return sonuc


# --- Betik ------------------------------------------------------------------------------


def _liste(klasor: Path) -> list[dict]:
    with (klasor / "liste.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def eslestirme_yap(klasor: str | Path = VARSAYILAN_KLASOR,
                   tedarikciler: tuple[str, ...] = VARSAYILAN_TEDARIKCILER) -> tuple[list[dict], list[dict]]:
    """Verilen tedarikçilerin şartnamesi olan sertifikalarını eşleştirir; (test satırları, sertifika özeti) döner."""
    from deney.coa_kumesi import coa_durumlari

    klasor = Path(klasor)
    durumlar = {d["sertifika"]: d for d in coa_durumlari(klasor)}
    satirlar, ozet = [], []
    sartname_onbellek: dict[str, list[Kalem]] = {}
    for r in _liste(klasor):
        sart = r["sartname_dosya_adi"].strip()
        if r["tedarikci"] not in tedarikciler or not sart or not (klasor / sart).is_file():
            continue
        if sart == r["sertifika_dosya_adi"]:
            continue
        if sart not in sartname_onbellek:
            sartname_onbellek[sart] = sartname_kalemleri(pdf_satirlari(klasor / sart))
        kalemler = sartname_onbellek[sart]
        testler = coa_satirlari(pdf_satirlari(klasor / r["sertifika_dosya_adi"]))
        bu = eslestir(testler, kalemler, r["katalog_numarasi"])
        ortak = {"tedarikci": r["tedarikci"], "urun": r["urun"], "katalog": r["katalog_numarasi"],
                 "lot": r["lot_numarasi"], "sertifika": r["sertifika_dosya_adi"], "sartname": sart}
        kullanilan = {i for b in bu for i in b["_kalemler"]}
        for b in bu:
            satirlar.append(ortak | {k: v for k, v in b.items() if k != "_kalemler"})
        ozet.append(ortak | {
            "olcum_kumesi": durumlar.get(r["sertifika_dosya_adi"], {}).get("durum", ""),
            "duzen": testler[0].duzen if testler else "",
            "test": len(bu),
            "karsilik_var": sum(b["durum"] != YOK for b in bu),
            "sinir_ayni": sum(b["durum"] == SINIR_AYNI for b in bu),
            "sinir_farkli": sum(b["durum"] == SINIR_FARKLI for b in bu),
            "sinirsiz": sum(b["durum"] == SINIRSIZ for b in bu),
            "sartname_sinirsiz": sum(b["durum"] == SARTNAME_SINIRSIZ for b in bu),
            "yok": sum(b["durum"] == YOK for b in bu),
            "elle": sum(b["eslesme"] == "elle" for b in bu),
            "sartname_kalem": len(kalemler),
            "testsiz_sartname": "; ".join(f"{k.ad}: {k.sinir}" for i, k in enumerate(kalemler) if i not in kullanilan),
        })
    return satirlar, ozet


def _yaz(yol: Path, alanlar: list[str], satirlar: list[dict]) -> None:
    with yol.open("w", encoding="utf-8", newline="") as f:
        yazici = csv.DictWriter(f, fieldnames=alanlar)
        yazici.writeheader()
        yazici.writerows(satirlar)


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description="Gerçek CoA'ları ürün şartnameleriyle test test eşleştirir.")
    ayr.add_argument("klasor", nargs="?", default=str(VARSAYILAN_KLASOR))
    ayr.add_argument("--tedarikci", action="append", help="Tedarikçi (birden çok verilebilir)")
    ayr.add_argument("--cikti", default=str(VARSAYILAN_CIKTI),
                     help="test_satirlari.csv ve sertifika_ozeti.csv'nin yazılacağı klasör")
    args = ayr.parse_args(argv)
    satirlar, ozet = eslestirme_yap(args.klasor, tuple(args.tedarikci or VARSAYILAN_TEDARIKCILER))
    cikti = Path(args.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    _yaz(cikti / "test_satirlari.csv", SATIR_ALANLARI, satirlar)
    _yaz(cikti / "sertifika_ozeti.csv", OZET_ALANLARI, ozet)
    durumlar = (SINIR_AYNI, SINIR_FARKLI, SINIRSIZ, SARTNAME_SINIRSIZ, YOK)
    say = {d: sum(s["durum"] == d for s in satirlar) for d in durumlar}
    print(f"{len(ozet)} sertifika, {len(satirlar)} test satırı: " + ", ".join(f"{k}: {v}" for k, v in say.items()))
    return 0


if __name__ == "__main__":
    if __package__ in (None, ""):
        sys.path.insert(0, str(KOK))
    sys.exit(main())
