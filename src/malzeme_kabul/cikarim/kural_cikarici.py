"""Kural tabanlı çıkarıcı: askeri malzeme standardından kabul dokümanı çıkarır.

Dil modeli kullanmaz; yalnız düzenli ifadeler ve belge yapısına dayanır. Hibrit
yaklaşımla karşılaştırılacak "yalnız kural" taban çizgisidir.

Kullanılan yapı (MIL-PRF biçimi):
- Numaralı paragraflar: "3.6.3 Viscosity. ..." -> madde, başlık, metin, sayfa.
- Test tablosu (TABLE II "Test Methods"): test adı, şart maddesi, test maddesi,
  test metodu. Her satır bir `TestSarti` olur.
- 4.2 / 4.3: yeterlilik muayenesi bütün testleri, kabul (conformance) muayenesi
  "with the exception of ..." ile sayılanlar dışındakileri kapsar.
- Panel tablosu (TABLE I): kupon malzemesi ve yüzey hazırlığı.
- "Storage stability" paragrafı: raf ömrü ve depolama sıcaklığı.
- "Precaution sheet" maddeleri: kap ömrü ve bekleme (indüksiyon) süresi.

Sınırın birimi pint biçiminde yazılır; birim dönüşümü burada yapılmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from malzeme_kabul.belge.pdf_okuyucu import Belge, pdf_oku
from malzeme_kabul.sozlesme.sema import (
    KabulDokumani,
    Kaynak,
    Kosul,
    NumuneHazirlama,
    RafOmru,
    Sinir,
    StandartBilgisi,
    TestSarti,
)

# --- Metin temizliği ------------------------------------------------------------

_GLIFLER = {
    "(cid:113)": "°",
    "(cid:114)": "±",
    "(cid:80)": "µ",
    "(cid:3)": " ",
    "º": "°",
    " ": " ",
}


def metni_normallestir(metin: str) -> str:
    """PDF'ten gelen glif kodlarını ve benzer karakterleri düzeltir."""
    for eski, yeni in _GLIFLER.items():
        metin = metin.replace(eski, yeni)
    return re.sub(r"[ \t]+", " ", metin).strip()


# --- Paragraflar ----------------------------------------------------------------

_PARAGRAF = re.compile(r"^([1-6](?:\.\d+)+)\s+([A-Z][^.]*?)\.(?:\s+(.*)|$)")
_BOLUM = re.compile(r"^[1-6]\.\s+[A-Z][A-Z ,]+$")


@dataclass
class Paragraf:
    no: str
    baslik: str
    metin: str
    sayfa: int


def _atlanacak_satir(satir: str, belge_no: str) -> bool:
    return (
        satir.startswith("Downloaded from")
        or satir == belge_no
        or satir.isdigit()
    )


def paragraflara_bol(belge: Belge, belge_no: str) -> dict[str, Paragraf]:
    """Numaralı paragrafları {madde: Paragraf} olarak döner.

    `belge_no` her sayfanın üst bilgisidir (ör. "MIL-PRF-23377K") ve atlanır.
    """
    paragraflar: dict[str, Paragraf] = {}
    simdiki: Paragraf | None = None
    for sayfa_no, ham in belge.satirlar():
        satir = metni_normallestir(ham)
        if not satir or _atlanacak_satir(satir, belge_no):
            continue
        if _BOLUM.match(satir):
            simdiki = None
            continue
        m = _PARAGRAF.match(satir)
        if m and m.group(1) not in paragraflar:
            simdiki = Paragraf(m.group(1), m.group(2).strip(), (m.group(3) or "").strip(), sayfa_no)
            paragraflar[simdiki.no] = simdiki
        elif simdiki is not None:
            simdiki.metin = f"{simdiki.metin} {satir}".strip()
    return paragraflar


# --- Sayılar, birimler, süreler ------------------------------------------------

_KELIME_SAYILAR = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
}
_SAYI = r"(\d[\d,]*(?:\.\d+)?|" + "|".join(_KELIME_SAYILAR) + r")"

# (düzenli ifade, pint birimi). Uzun kalıplar önce gelir.
_BIRIMLER = [
    (r"g/L", "g/L"),
    (r"parts? per million", "ppm"),
    (r"ppm", "ppm"),
    (r"percent|%", "%"),
    (r"seconds?", "s"),
    (r"minutes?", "minute"),
    (r"hours?", "hour"),
    (r"days?", "day"),
    (r"months?", "month"),
    (r"years?", "year"),
    (r"microns|µm", "µm"),
    (r"millimeters|mm", "mm"),
    (r"nanometers|nm", "nm"),
    (r"mils?", "mil"),
    (r"°\s?C", "°C"),
]
_BIRIM = "(" + "|".join(k for k, _ in _BIRIMLER) + r")(?![A-Za-z])"
_BIRIM_OPS = "(?:" + _BIRIM + ")?"


def _sayi(metin: str) -> float:
    metin = metin.lower()
    if metin in _KELIME_SAYILAR:
        return float(_KELIME_SAYILAR[metin])
    return float(metin.replace(",", ""))


def _birim(metin: str | None) -> str | None:
    if not metin:
        return None
    for kalip, pint_birimi in _BIRIMLER:
        if re.fullmatch(kalip, metin, flags=re.I):
            return pint_birimi
    return None


def sure_cikar(metin: str) -> tuple[float, str] | None:
    """Metindeki ilk süreyi (sayı, pint zaman birimi) olarak döner."""
    m = re.search(_SAYI + r"\s+(days?|months?|years?|hours?)\b", metin, flags=re.I)
    if not m:
        return None
    return _sayi(m.group(1)), _birim(m.group(2))


# --- Sınır kuralları ------------------------------------------------------------

# Cümle içi karakter: nokta yalnızca ondalık ya da madde numarasının parçasıysa ("3.6.3").
_ICERI = r"(?:[^.]|\.(?=\d))"
_UST = r"(?:not greater than|not more than|no greater than|not to exceed|extending beyond)"
_ALT = r"(?:not less than|no less than|at least|a minimum of|minimum of)"
# Sınır kalıpları öncelik sırasıyla. Her biri (kalıp, tür) döner.
_SINIR_KALIPLARI = [
    (re.compile(_UST + r"\s+(?:a\s+)?" + _SAYI + r"[A-Z]?\s*" + _BIRIM_OPS, re.I), "ust"),
    (re.compile(_ALT + r"\s+(?:a\s+)?" + _SAYI + r"[A-Z]?\s*" + _BIRIM_OPS, re.I), "alt"),
    (re.compile(r"maximum" + _ICERI + r"*?shall be\s+" + _SAYI + r"\s*" + _BIRIM_OPS, re.I), "ust"),
    (re.compile(r"shall" + _ICERI + r"*?within\s+" + _SAYI + r"\s*" + _BIRIM, re.I), "ust"),
    (re.compile(_SAYI + r"\s+or greater", re.I), "alt"),
    (re.compile(_SAYI + r"\s+to\s+" + _SAYI + r"\s*" + _BIRIM, re.I), "aralik"),
]


def _cumle(metin: str, konum: int) -> str:
    bas = max(metin.rfind(". ", 0, konum) + 2, 0) if metin.rfind(". ", 0, konum) >= 0 else 0
    son = metin.find(". ", konum)
    return metin[bas: son + 1 if son >= 0 else len(metin)].strip()


def sinir_cikar(metin: str) -> Sinir:
    """Şart metninden kabul kriterini çıkarır; sayı bulamazsa metinsel kriter döner."""
    metin = metni_normallestir(metin)
    for kalip, tur in _SINIR_KALIPLARI:
        for m in kalip.finditer(metin):
            gruplar = m.groups()
            if tur == "aralik":
                birim = _birim(gruplar[2])
                if birim == "°C":  # sıcaklık aralıkları test koşuludur, kabul sınırı değil
                    continue
                alt, ust = _sayi(gruplar[0]), _sayi(gruplar[1])
            else:
                birim = _birim(gruplar[1]) if len(gruplar) > 1 else None
                deger = _sayi(gruplar[0])
                alt, ust = (deger, None) if tur == "alt" else (None, deger)
            return Sinir(
                kriter_turu="sayisal", alt=alt, ust=ust, birim=birim,
                orijinal_metin=_cumle(metin, m.start()),
            )
    return Sinir(kriter_turu="metinsel", orijinal_metin=_ilk_cumleler(metin) or "Bkz. standart maddesi")


def _ilk_cumleler(metin: str, adet: int = 2) -> str:
    parcalar = re.split(r"(?<=\.)\s+(?=[A-Z])", metin.strip())
    return " ".join(parcalar[:adet]).strip()


# --- Test adı ---------------------------------------------------------------------

# "Lead and cadmium content": iki bileşen ortak bir ada bağlanmış tablo satırı.
_BIRLESIK_AD = re.compile(r"(?P<a>[A-Za-z-]+) and (?P<b>[A-Za-z-]+) (?P<kuyruk>[A-Za-z][\w ()-]*)")


def test_adi_ayir(tablo_adi: str, sart_cumlesi: str) -> str:
    """Tablo satırı iki bileşeni birleştiriyorsa, şart cümlesinin kapsadığı bileşenin adını döner.

    "Lead and cadmium content" satırında ≤ 1 ppm şartının cümlesi yalnız
    kadmiyumdan söz ediyorsa ad "Cadmium content" olur. Cümle iki bileşeni de
    anıyorsa ya da hiçbirini anmıyorsa tablo adı değişmez.
    """
    m = _BIRLESIK_AD.fullmatch(tablo_adi.strip())
    if not m:
        return tablo_adi
    anilan = [b for b in (m["a"], m["b"]) if re.search(rf"\b{re.escape(b)}\b", sart_cumlesi, flags=re.I)]
    if len(anilan) != 1:
        return tablo_adi
    return f"{anilan[0].capitalize()} {m['kuyruk']}"


# --- Test tablosu ve test türleri ----------------------------------------------


def uygulanabilirlik_cikar(ad: str) -> list[str]:
    """Test adındaki tip/sınıf kısıtını döner: '(class N only)' -> ['Class N']."""
    m = re.search(r"\((type|class)\s+([A-Z0-9]+)(?:\s+\w+)*\s+only\)", ad, flags=re.I)
    if not m:
        m = re.search(r"[–-]\s*(type|class)\s+([A-Z0-9]+)\s*$", ad, flags=re.I)
    return [f"{m.group(1).capitalize()} {m.group(2).upper()}"] if m else []


def kabul_disi_testler(metin: str) -> list[str]:
    """Kabul muayenesi paragrafında 'with the exception of' ile sayılan testler."""
    m = re.search(r"with the exception of (.*?)\.(?:\s|$)", metni_normallestir(metin), flags=re.I)
    if not m:
        return []
    liste = re.sub(r"\(see [^)]*\)", "", m.group(1))
    parcalar = re.split(r",\s*(?:and\s+)?|\s+and\s+", liste)
    return [p.strip().lower() for p in parcalar if p.strip()]


def _test_tablosu(belge: Belge) -> list[tuple[int, list[str]]]:
    satirlar = []
    for sayfa_no, tablo in belge.tablolar():
        baslik = " ".join(tablo[0]).lower() if tablo else ""
        if "requirement" in baslik and "test method" in baslik:
            for satir in tablo[1:]:
                if len(satir) >= 4 and satir[0].strip():
                    satirlar.append((sayfa_no, [metni_normallestir(h.replace("\n", " ")) for h in satir]))
    return satirlar


def _panel_tablosu(belge: Belge) -> list[list[str]]:
    for _, tablo in belge.tablolar():
        if tablo and [h.lower() for h in tablo[0][:3]] == ["panel", "substrate", "pretreatment"]:
            return [[metni_normallestir(h.replace("\n", " ")) for h in s] for s in tablo[1:] if s[0].strip()]
    return []


def _kimlik(ad: str) -> str:
    ad = ad.lower().replace("–", "-")
    return re.sub(r"[^a-z0-9]+", "_", ad).strip("_")


def _bos(deger: str) -> str | None:
    deger = deger.strip()
    return None if deger in {"", "---", "--", "-"} else deger


# --- Ana çıkarım ----------------------------------------------------------------


def _standart_bilgisi(belge: Belge, belge_no: str, revizyon: str) -> StandartBilgisi:
    ilk = [metni_normallestir(s) for s in belge.sayfalar[0].metin.splitlines()] if belge.sayfalar else []
    baslik = tarih = None
    for i, satir in enumerate(ilk):
        if satir == "PERFORMANCE SPECIFICATION" and i + 1 < len(ilk):
            baslik = ilk[i + 1]
        if satir == f"{belge_no}{revizyon}" and i + 1 < len(ilk) and tarih is None:
            tarih = ilk[i + 1]
    return StandartBilgisi(belge_no=belge_no, revizyon=revizyon, baslik=baslik, tarih=tarih)


def cikar(pdf_yolu: str | Path, belge_no: str, revizyon: str, belge: Belge | None = None) -> KabulDokumani:
    """PDF'ten kural tabanlı olarak kabul dokümanı çıkarır.

    `belge` verilirse (ör. taranmış sayfaları OCR'dan geçmiş okuma) PDF yeniden
    okunmaz, verilen belgenin metni kullanılır.
    """
    if belge is None:
        belge = pdf_oku(pdf_yolu)
    paragraflar = paragraflara_bol(belge, belge_no=f"{belge_no}{revizyon}")

    def kaynak(madde: str, sayfa: int | None = None, alinti: str | None = None) -> Kaynak:
        p = paragraflar.get(madde)
        return Kaynak(
            belge_no=belge_no, revizyon=revizyon, madde=madde,
            sayfa=sayfa or (p.sayfa if p else None), alinti=alinti,
        )

    # Yeterlilik / kabul muayenesi kapsamı
    kabul_p = next((p for p in paragraflar.values() if p.baslik.lower() == "conformance inspection"), None)
    haric = kabul_disi_testler(kabul_p.metin) if kabul_p else []

    # Numune hazırlama (TABLE I + 4.4.1)
    uygulama_p = next((p for p in paragraflar.values() if p.baslik.lower().startswith("application of primer")), None)
    numuneler: list[NumuneHazirlama] = []
    if uygulama_p:
        sprey = re.search(_ICERI + r"*spray apply" + _ICERI + r"*\.", uygulama_p.metin, flags=re.I)
        kurlenme = re.search(_ICERI + r"*air dry for not less than" + _ICERI + r"*\.", uygulama_p.metin, flags=re.I)
        kft = sinir_cikar(sprey.group(0)) if sprey else None
        for panel, substrat, on_islem, *_ in _panel_tablosu(belge):
            numuneler.append(NumuneHazirlama(
                id=f"panel_{panel}",
                kupon_malzemesi=substrat,
                yuzey_hazirligi=re.sub(r"\s*\d/$", "", on_islem),
                uygulama_yontemi=sprey.group(0).strip() if sprey else None,
                kuru_film_kalinligi=kft if kft and kft.kriter_turu == "sayisal" else None,
                kurlenme=kurlenme.group(0).strip() if kurlenme else None,
                kaynak=kaynak("TABLE I", sayfa=uygulama_p.sayfa),
            ))
    numune_idleri = {n.id for n in numuneler}

    # Testler (TABLE II)
    testler: list[TestSarti] = []
    gorulen: set[str] = set()
    for sayfa_no, (ad, sart_maddesi, test_maddesi, metot, *_) in _test_tablosu(belge):
        ad = re.sub(r"\s+\d/$", "", ad)
        kimlik = _kimlik(ad)
        if kimlik in gorulen or not re.fullmatch(r"[1-6](\.\d+)+", sart_maddesi):
            continue
        gorulen.add(kimlik)
        sart_p = paragraflar.get(sart_maddesi)
        metin = sart_p.metin if sart_p else ad
        test_p = paragraflar.get(test_maddesi) if _bos(test_maddesi) else None

        turler = {"yeterlilik"}
        if not any(h in ad.lower() for h in haric):
            turler.add("kabul")

        panel = None
        if test_p:
            m = re.search(r"panels designated ([A-Z])\b", test_p.metin)
            if m and f"panel_{m.group(1)}" in numune_idleri:
                panel = f"panel_{m.group(1)}"

        sinir = sinir_cikar(metin)
        testler.append(TestSarti(
            id=kimlik,
            test_adi=test_adi_ayir(ad, sinir.orijinal_metin),
            kaynak_tablo_adi=ad,
            test_metodu=_bos(metot),
            metot_kaynagi=kaynak(test_maddesi) if test_p else None,
            sinir=sinir,
            kaynak=kaynak(sart_maddesi, sayfa=None if sart_p else sayfa_no),
            test_turleri=turler,
            uygulanabilirlik=uygulanabilirlik_cikar(ad) or uygulanabilirlik_cikar(sart_p.baslik if sart_p else ""),
            numune_hazirlama_id=panel,
        ))

    # Raf ömrü ve depolama
    raf_omurleri: list[RafOmru] = []
    kosullar: list[Kosul] = []
    depolama_p = next(
        (p for p in paragraflar.values()
         if re.fullmatch(r"(storage stability|shelf life)", p.baslik, flags=re.I) and sure_cikar(p.metin)),
        None,
    )
    if depolama_p:
        sure, birim = sure_cikar(depolama_p.metin)
        sicaklik = None
        m = re.search(_SAYI + r"\s+to\s+" + _SAYI + r"\s*°\s?C", depolama_p.metin)
        if m:
            sicaklik = Sinir(
                kriter_turu="sayisal", alt=_sayi(m.group(1)), ust=_sayi(m.group(2)), birim="°C",
                orijinal_metin=_cumle(depolama_p.metin, m.start()),
            )
        raf_omurleri.append(RafOmru(
            sure=sure, birim=birim, kosul=sicaklik,
            kaynak=kaynak(depolama_p.no, alinti=_ilk_cumleler(depolama_p.metin)),
        ))
        if sicaklik:
            kosullar.append(Kosul(kategori="depolama", ad="Depolama sıcaklığı", sinir=sicaklik,
                                  kaynak=kaynak(depolama_p.no)))

    onlem_p = next((p for p in paragraflar.values() if p.baslik.lower() == "precaution sheet"), None)
    if onlem_p:
        for madde_metni in re.split(r"\s(?=[a-z]\.\s)", onlem_p.metin):
            m = re.search(r"within\s+" + _SAYI + r"\s+(hours?|minutes?)", madde_metni, flags=re.I)
            if m:
                kosullar.append(Kosul(
                    kategori="kullanim", ad="Kap ömrü (karışımın kullanım süresi)",
                    sinir=Sinir(kriter_turu="sayisal", ust=_sayi(m.group(1)), birim=_birim(m.group(2)),
                                orijinal_metin=madde_metni.strip()),
                    kaynak=kaynak(onlem_p.no),
                ))
            m = re.search(r"stand undisturbed for\s+" + _SAYI + r"\s+(hours?|minutes?)", madde_metni, flags=re.I)
            if m:
                kosullar.append(Kosul(
                    kategori="kullanim", ad="Bekleme (indüksiyon) süresi",
                    sinir=Sinir(kriter_turu="sayisal", alt=_sayi(m.group(1)), birim=_birim(m.group(2)),
                                orijinal_metin=madde_metni.strip()),
                    kaynak=kaynak(onlem_p.no),
                ))

    return KabulDokumani(
        standart=_standart_bilgisi(belge, belge_no, revizyon),
        testler=testler,
        raf_omurleri=raf_omurleri,
        kosullar=kosullar,
        numune_hazirlama=numuneler,
    )
