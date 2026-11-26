"""Kanıt doğrulayıcı: dil modelinin okuduğu metin belgede, söylediği sayfada var mı?

Dil modeli bir hücreyi uydurabilir, değiştirebilir (ör. "0.4" yerine "0.04")
ya da başka sayfadan, başka satırdan, başka sütundan okuyabilir. Bu modül her
okumayı belgenin metin katmanıyla kesin kurallarla karşılaştırır:

- Karşılaştırma boşluk ve büyük/küçük harf farkını yok sayar; başka hiçbir
  değişikliğe izin vermez (sayı, birim, işaret aynen bulunmalıdır).
- Metin söylenen sayfada yoksa okuma **kanıtsız** sayılır. Hat kanıtsız
  okumayı karara sokmaz ve insan incelemesi ister.

Sertifika satırı (`satir_kaniti`, retro H1-H4, H7): tablo satırları metin
katmanında tek satırdır ve test adıyla başlar. Kanıt için

- test adıyla başlayan satır sayfada **tam bir** olmalıdır (iki satır varsa
  biri gizli metin olabilir; hangisinin gerçek olduğu anlaşılmaz),
- sonuç hücresi o satırda, test adından sonra, bütün sözcükler olarak
  geçmelidir; birim hücresi verilmişse aynı satırda, ardından şart sözcüğü
  gelmeyen bir yerde geçmelidir (birim sayfanın başka yerinde aranmaz;
  "70 min max 47 s" satırında "min" sonucun birimi sayılmaz),
- sonuçtan önce işaret ya da olumsuzluk ("<", ">=", "-", "Not") olmamalıdır
  ("<1" hücresi "1" diye okunamaz),
- sonuçtan (ve birimden) sonra şart sözcüğü ("max", "min") gelmemelidir:
  "1 ppm max" şart sütunudur, sonuç değildir.

Standart okuması ve üst bilgiler (`okuma_kaniti`, `deger_kaniti`, H11, H5):
metin sayı ve sözcük sınırıyla aranır ("1 ppm" "0.1 ppm" içinde, "5 min" "5
minutes" içinde, "5 °C" "-5 °C" içinde bulunmuş sayılmaz). Standart atfı
(`atif_kaniti`, H6) belgedeki atfın tamamı olmalıdır; bir parçası
("MIL-PRF-23377K", belgede "... Type II") kanıt değildir.

`metin_sayfada_mi` sınırsız alt dize aramasıdır; yalnız deney/ tarafı
(standart hibrit deneyi) kullanır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from malzeme_kabul.sozlesme.okuma import HamOkuma, SertifikaSatirOkumasi


def _normal(metin: str) -> str:
    return " ".join(metin.split()).casefold()


def metin_sayfada_mi(metin: str, sayfa_metni: str) -> bool:
    """Metin (boşluk ve harf büyüklüğü dışında aynen) sayfada geçiyor mu? Sınır aranmaz."""
    hedef = _normal(metin)
    return bool(hedef) and hedef in _normal(sayfa_metni)


@dataclass(frozen=True)
class KanitSonucu:
    kanitli: bool
    neden: str


# Sayının önünde kalırsa anlamı değiştiren işaretler (eksi, karşılaştırma, artı-eksi, yaklaşık).
_ISARETLER = "<>≤≥=±~+\\-−–"


def _sinirli(metin: str) -> re.Pattern[str]:
    """Normalleştirilmiş metni sayı ve sözcük sınırıyla arayan desen.

    Rakamla başlayan metnin önünde rakam, ondalık ayırıcı ya da işaret
    olamaz; harfle başlayanın önünde harf ya da rakam olamaz. Rakamla biten
    metnin ardında rakam ya da ondalık kısım, harfle bitenin ardında harf ya
    da rakam olamaz. Noktalama (".", ",", ")") sınır sayılır.
    """
    hedef = _normal(metin)
    bas = son = ""
    if hedef[:1].isdigit():
        bas = rf"(?<![\d.,{_ISARETLER}])"
    elif hedef[:1].isalnum():
        bas = r"(?<![^\W_])"
    if hedef[-1:].isdigit():
        son = r"(?![\d]|[.,]\d)"
    elif hedef[-1:].isalnum():
        son = r"(?![^\W_])"
    return re.compile(bas + re.escape(hedef) + son)


def okuma_kaniti(okuma: HamOkuma, sayfalar: dict[int, str]) -> KanitSonucu:
    """Standart okumasının (`HamOkuma`) ham metni, sayı ve sözcük sınırıyla, söylenen sayfada mı?"""
    sayfa = sayfalar.get(okuma.konum.sayfa)
    if sayfa is None:
        return KanitSonucu(False, f"sayfa {okuma.konum.sayfa} belgede yok")
    if not _normal(okuma.ham_metin):  # şemaya güvenilmez: model_copy doğrulamayı atlar
        return KanitSonucu(False, "ham metin boş")
    if not _sinirli(okuma.ham_metin).search(_normal(sayfa)):
        return KanitSonucu(False, f"{okuma.ham_metin!r} sayfa {okuma.konum.sayfa} metninde (sözcük sınırıyla) yok")
    return KanitSonucu(True, "metin sayfada bulundu")


# Numara alanları: değerin iki yanında harf, rakam ya da "-" olamaz ("94009" ⊄ "A94009", "A-2512-01" ⊄ "A-2512-01-2").
_NUMARA_ALANLARI = {"parti_no", "sertifika_no"}


def deger_kaniti(deger: str, sayfalar: dict[int, str], alan: str | None = None) -> KanitSonucu:
    """Üst bilgi değeri (tedarikçi, lot, tarih...) belgenin herhangi bir sayfasında, sayı ve sözcük sınırıyla var mı?

    `alan` "parti_no" ya da "sertifika_no" ise değerin iki yanında harf, rakam
    ya da "-" olamaz. Etikete yapışık değer ("manufacture2026-08-21") yalnız
    rakamla başlayan değerde ve numara alanı dışında kabul edilir (üretim
    tarihi). `alan` verilmezse genel sınır kuralı uygulanır.
    """
    if not _normal(deger):
        return KanitSonucu(False, "boş değer")
    if alan in _NUMARA_ALANLARI:
        desen = re.compile(r"(?<![\w-])" + re.escape(_normal(deger)) + r"(?![\w-])")
    else:
        desen = _sinirli(deger)
    if any(desen.search(_normal(m)) for m in sayfalar.values()):
        return KanitSonucu(True, "değer belgede bulundu")
    return KanitSonucu(False, f"{deger!r} belgede yok")


_STANDART_NO = re.compile(r"mil[-\s]?[a-z]+[-\s]?\d+")
# Atıftan önce gelen bilinen etiketler (normalleştirilmiş metinde); başka etiket atılmaz ("Supersedes:").
_ATIF_ETIKETI = re.compile(r"^(?:standart\s+şartname\s*:|şartname\s*:|specification\s*:?|spec\.)\s*")
_ATIF_SONU = re.compile(r"\s*(?:date of manufacture|[üu]retim tarihi|$)")


def atif_kaniti(atif: str, sayfalar: dict[int, str]) -> KanitSonucu:
    """Standart atfı belgedeki atfın tamamı mı?

    Bilinen etiketler ("Standart Şartname:", "Şartname:", "Specification:",
    "Specification", "Spec.") hem atıftan hem belge satırından atılır. Atıf
    (etiketsiz) standart numarasıyla başlamalı ve belgede bir satırda, sınırla
    geçmeli; ardından satır bitmeli ya da üretim tarihi alanı gelmelidir.
    Böylece "MIL-PRF-23377K" ya da "MIL-PRF-23377K Type I", belgede
    "MIL-PRF-23377K Type II Class N" yazarken kanıt sayılmaz.
    """
    hedef = _ATIF_ETIKETI.sub("", _normal(atif), count=1)
    if not _STANDART_NO.match(hedef):
        return KanitSonucu(False, f"{atif!r} standart numarasıyla başlamıyor")
    desen = _sinirli(hedef)
    for metin in sayfalar.values():
        for satir in metin.splitlines():
            s = _ATIF_ETIKETI.sub("", _normal(satir), count=1)
            if any(_ATIF_SONU.match(s, m.end()) for m in desen.finditer(s)):
                return KanitSonucu(True, "atıf belgede tam olarak bulundu")
    return KanitSonucu(False, f"{atif!r} belgede tam atıf olarak yok")


_ONEK = re.compile(rf"^(?:[{_ISARETLER}]+|not|non|no)$")
_SINIR_SOZCUKLERI = {"max", "max.", "maximum", "min", "min.", "minimum", "maks", "maks."}
_SART_SOZCUKLERI = _SINIR_SOZCUKLERI | {"to"}
# Değerin önünde her zaman şart anlamı taşıyan sözcükler ("15 to 23", "NMT 40", "NLT 10").
_SART_ONEKLERI = {"to", "nmt", "nlt"}
_SAYI = re.compile(r"^[<>≤≥]?\d[\d.,]*$")
_ARALIK = re.compile(r"^\d[\d.,]*\s*[-–]\s*\d[\d.,]*$")


def _sart_disi_deger_gelir(sozcukler: list[str], j: int) -> bool:
    """j'de, ardından şart sözcüğü gelmeyen bir sayı mı var?

    "5 min 6": "6" sonuçtur, "5 min" şarttır. "0.5 min 40 s max": "40 s max"
    şarttır, "0.5 min" sonuçtur.
    """
    if j >= len(sozcukler) or not _SAYI.match(sozcukler[j]):
        return False
    return not any(k < len(sozcukler) and sozcukler[k] in _SART_SOZCUKLERI for k in (j + 1, j + 2))


def _sart_oneki_mi(sozcukler: list[str], i: int) -> bool:
    """i'deki değerin önündeki sözcük onu şart yapıyor mu (K2)?

    "to", "NMT", "NLT" her zaman şarttır. "max"/"min" önceki sayının (ya da
    sayı + birimin) eki olabilir ("5 min 6", "1 ppm max 0.4"); öyle değilse
    değerin önekidir ("Max 1 ppm", "min 5").
    """
    if i == 0:
        return False
    onceki = sozcukler[i - 1]
    if onceki in _SART_ONEKLERI:
        return True
    if onceki not in _SINIR_SOZCUKLERI:
        return False
    return not any(j >= 0 and _SAYI.match(sozcukler[j]) for j in (i - 2, i - 3))


def _sozcukler(metin: str) -> list[str]:
    return _normal(metin).split()


def _sonuc_konumlari(satir: list[str], aranan: list[str]) -> list[int]:
    n = len(aranan)
    return [i for i in range(len(satir) - n + 1) if satir[i:i + n] == aranan]


def satir_kaniti(okuma: SertifikaSatirOkumasi, sayfalar: dict[int, str]) -> KanitSonucu:
    """Sertifika satırının hücreleri söylenen sayfada, test adıyla başlayan tek satırda, yerli yerinde mi?"""
    sayfa = sayfalar.get(okuma.sayfa)
    if sayfa is None:
        return KanitSonucu(False, f"sayfa {okuma.sayfa} belgede yok")
    hucreler = [h for h in (okuma.test_adi, okuma.sonuc_hucresi, okuma.birim_hucresi) if h]
    eksik = [h for h in hucreler if not metin_sayfada_mi(h, sayfa)]
    if eksik:
        return KanitSonucu(False, f"sayfa {okuma.sayfa} metninde yok: {', '.join(repr(h) for h in eksik)}")
    ad = _sozcukler(okuma.test_adi)
    satirlar = [_sozcukler(x) for x in sayfa.splitlines()]
    adaylar = [i for i, s in enumerate(satirlar) if s[:len(ad)] == ad]
    if not adaylar:
        return KanitSonucu(False, f"{okuma.test_adi!r} ile başlayan satır yok")
    if len(adaylar) > 1:
        return KanitSonucu(False, f"{okuma.test_adi!r} ile başlayan {len(adaylar)} satır var; hangisinin okunduğu belli değil")
    satir = satirlar[adaylar[0]][len(ad):]
    sonuc = _sozcukler(okuma.sonuc_hucresi)
    birim = _sozcukler(okuma.birim_hucresi) if okuma.birim_hucresi else []
    if _ARALIK.match(_normal(okuma.sonuc_hucresi)):
        return KanitSonucu(False, f"{okuma.sonuc_hucresi!r} bir aralık; aralık şarttır, sonuç değil")
    # Birim bir şart sözcüğüyse ("min") sonuca bitişik olmalı ve ardından şart olmayan başka değer
    # gelmemeli (K1): "5 min 6" satırında "5 min" şart sütunudur; "0.5 min 40 s max" satırında sonuçtur.
    birim_sart_sozcugu = len(birim) == 1 and birim[0] in _SINIR_SOZCUKLERI
    # Hücre içinde satır sonu olabilir ("ND (<0,5" / "ppm)"): eşleşme test adının satırında başlamalı,
    # yalnız o satırın sonundan sonraki satırların başına taşabilir. Sonraki satırın ortasındaki
    # değer (başka testin sonucu) bu yüzden kanıt olamaz.
    devam = [w for s in satirlar[adaylar[0] + 1:adaylar[0] + 1 + len(sonuc) + len(birim)] for w in s]
    uzun = satir + devam

    def sart_degil(j: int) -> bool:  # j'deki sözcük yoksa ya da şart sözcüğü değilse
        return j >= len(uzun) or uzun[j] not in _SART_SOZCUKLERI

    # Birim hücresi test satırında, ardından şart sözcüğü gelmeyen bir yerde geçmelidir
    # ("70 min max 47 s" satırında "min" şartın birimidir, sonucun değil).
    birim_yerleri = [j for j in _sonuc_konumlari(uzun, birim) if j < len(satir) and sart_degil(j + len(birim))] if birim else []
    for i in _sonuc_konumlari(uzun, sonuc):
        if i >= len(satir):
            break
        if i and _ONEK.match(uzun[i - 1]):
            continue  # "< 0.4", "Not Pass": önek atılmış
        if _sart_oneki_mi(uzun, i):
            continue  # "Max 1 ppm", "15 to 23", "NMT 40": şart sütunu
        son = i + len(sonuc)
        bitisik = bool(birim) and uzun[son:son + len(birim)] == birim
        if bitisik:
            son += len(birim)  # bitişik birim: şart sözcüğü birimden sonra aranır ("1 ppm max")
        if not sart_degil(son):
            continue  # "1 ppm max", "5 min": şart sütunu
        if birim_sart_sozcugu and (not bitisik or _sart_disi_deger_gelir(uzun, son)):
            continue  # "70 min 47 s" → "47 min", "5 min 6" → "5 min"
        if birim and not any(j + len(birim) <= i or j >= i + len(sonuc) for j in birim_yerleri):
            continue  # birim satırda yok ya da yalnız şartın birimi olarak var
        return KanitSonucu(True, "hücreler aynı satırda bulundu")
    birim = f" {okuma.birim_hucresi!r}" if okuma.birim_hucresi else ""
    return KanitSonucu(False, f"{okuma.sonuc_hucresi!r}{birim} sonucu {okuma.test_adi!r} satırında sonuç olarak yok")


__all__ = ["KanitSonucu", "atif_kaniti", "deger_kaniti", "metin_sayfada_mi", "okuma_kaniti", "satir_kaniti"]
