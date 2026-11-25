"""Sınır yönü doğrulaması (docs/mimari.md madde 6, kör nokta 6).

Dil modeli bir sınırın yönünü (en az / en çok / aralık) yanlış okuyabilir:
"≤ 1 ppm" metni alt sınır olarak yazılırsa kural motoru 100 ppm'i de kabul
eder. Bu modül yönü modelden bağımsız olarak, standarttaki özgün metnin
ipuçlarından ("not greater than", "minimum", "≤", "15 to 30") kesin kurallarla
çıkarır ve modelin yönüyle karşılaştırır.

- Metin bir yön söylüyor ve model farklı yazmışsa: **çelişki**. Sınır
  `yon="belirsiz"` yapılır; karar motoru böyle şartları karşılaştırmaz,
  insan incelemesine gönderir. Sayılar korunur, kayda geçer.
- Metinde ipucu yoksa ya da ipuçları karışıksa kural karar vermez; model
  yönü olduğu gibi kalır (başka denetimler, ör. kanıt kontrolü, devam eder).

Kural yalnız insan incelemesine göndererek hata yapabilir (yanlış alarm);
kendi başına bir şartı kabul ettirmez.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from malzeme_kabul.sozlesme.okuma import HamOkuma
from malzeme_kabul.sozlesme.sema import Sinir, SinirYonu

Durum = Literal["uyumlu", "celiski", "metinde_ipucu_yok", "belirsiz", "sayisal_degil"]

# Madde numaralarının ("4.6.13 through 4.6.13.5") parçaları sayı sayılmaz.
_SAYI = r"(?<![\d.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?![\d,]*\.\d)"

# Aralık kalıpları: "15 to 30", "between 1.0 and 1.5", "0.6 – 0.9", "1.0 ± 0.2".
_ARALIK = [
    re.compile(rf"{_SAYI}\s*(?:to|through|[-–—])\s*{_SAYI}", re.IGNORECASE),
    re.compile(rf"\bbetween\s+{_SAYI}\b.*?\band\s+{_SAYI}", re.IGNORECASE),
    re.compile(rf"{_SAYI}\s*(?:±|\+/-|\+-)\s*{_SAYI}"),
]
# Bu birimlerle yazılan aralık test koşuludur (dalga boyu, sıcaklık), kabul sınırı
# değil; yön için sayılmaz (kural_cikarici de °C aralıklarını atlar).
_KOSUL_BIRIMI = re.compile(r"\s*(?:nanomet|nm\b|°\s*[CF]\b|deg|º)", re.IGNORECASE)

# Tek yönlü ipuçları. Uzun (olumsuz) kalıplar önce aranır ve metinden silinir;
# böylece "not less than" içindeki "less than" ikinci kez sayılmaz.
_IPUCLARI: list[tuple[str, SinirYonu]] = [
    (r"\bnot\s+(?:be\s+)?(?:greater|more|higher)\s+than\b", "en_cok"),
    (r"\bno\s+(?:greater|more|higher)\s+than\b", "en_cok"),
    (r"\bnot\s+(?:be\s+)?(?:less|lower|fewer)\s+than\b", "en_az"),
    (r"\bno\s+(?:less|lower|fewer)\s+than\b", "en_az"),
    (r"\b(?:shall\s+)?not\s+(?:to\s+)?exceed(?:ing)?\b", "en_cok"),
    # Olumsuzluk aynı cümlede daha önce gelmişse: "no component shall contain ... more
    # than 0.05 percent", "do not add thinner if ... greater than 340 g/L". Alıntıdaki
    # "..." cümle sonu sayılmaz.
    (r"\b(?:no|not)\b(?:\.\.\.|[^.;]){0,100}?\b(?:greater|more|higher)\s+than\b", "en_cok"),
    (r"\b(?:no|not)\b(?:\.\.\.|[^.;]){0,100}?\b(?:less|lower|fewer)\s+than\b", "en_az"),
    (r"\bat\s+least\b", "en_az"),
    (r"\bat\s+most\b", "en_cok"),
    (r"\bup\s+to\b", "en_cok"),
    (r"\bor\s+(?:less|lower|below)\b", "en_cok"),
    (r"\bor\s+(?:more|greater|higher|above)\b", "en_az"),
    (r"\bmaximum\b|\bmax\b\.?", "en_cok"),
    (r"\bminimum\b|\bmin\b\.?", "en_az"),
    (r"\bwithin\b", "en_cok"),
    (r"\b(?:less|lower|fewer)\s+than\b|\bbelow\b|\bunder\b", "en_cok"),
    (r"\b(?:greater|more|higher)\s+than\b|\babove\b|\bexceeds?\b", "en_az"),
    (r"≤|<=|=<|⩽|<", "en_cok"),
    (r"≥|>=|=>|⩾|>", "en_az"),
]
_IPUCU_KALIPLARI = [(re.compile(k, re.IGNORECASE), y) for k, y in _IPUCLARI]


_ARALIK_IFADESI = re.compile(r"\b(?:with)?in\s+the\s+range\s+of\b|\bthroughout\s+the\s+range\s+of\b", re.IGNORECASE)


def metinden_yon(metin: str) -> SinirYonu | None:
    """Özgün sınır metninden yönü kuralla çıkarır; ipucu yoksa ya da karışıksa None.

    Hem aralık hem tek yönlü ipucu varsa ("no less than 0.95 ... cast to 1.9 to 2.1
    mils") hangisinin kabul sınırı olduğu metinden kesin çıkmaz; kural karar vermez.
    """
    kalan = _ARALIK_IFADESI.sub(" ", metin)
    aralik_var = False
    for kalip in _ARALIK:
        for m in kalip.finditer(kalan):
            if not _KOSUL_BIRIMI.match(kalan, m.end()):
                aralik_var = True
            kalan = kalan.replace(m.group(0), " ")  # aralık sayıları "<"/">" gibi okunmasın
    yonler: set[SinirYonu] = set()
    for kalip, yon in _IPUCU_KALIPLARI:
        if kalip.search(kalan):
            yonler.add(yon)
            kalan = kalip.sub(" ", kalan)
    if aralik_var:
        return "aralik" if not yonler else None
    return yonler.pop() if len(yonler) == 1 else None


@dataclass(frozen=True)
class YonDenetimi:
    durum: Durum
    metin_yonu: SinirYonu | None = None
    model_yonu: SinirYonu | None = None

    @property
    def aciklama(self) -> str:
        if self.durum == "celiski":
            return (f"sınır yönü metinle çelişiyor: metin '{self.metin_yonu}', model '{self.model_yonu}'; "
                    "insan incelemesi gerekli")
        return {
            "uyumlu": "sınır yönü metinle uyumlu",
            "metinde_ipucu_yok": "metinde yön ipucu yok; yön kuralla doğrulanamadı",
            "belirsiz": "yön zaten belirsiz",
            "sayisal_degil": "sayısal kriter değil",
        }[self.durum]


def _karsilastir(model_yonu: SinirYonu | None, metin: str) -> YonDenetimi:
    if model_yonu is None:
        return YonDenetimi("sayisal_degil")
    if model_yonu == "belirsiz":
        return YonDenetimi("belirsiz", model_yonu=model_yonu)
    metin_yonu = metinden_yon(metin)
    if metin_yonu is None:
        return YonDenetimi("metinde_ipucu_yok", model_yonu=model_yonu)
    durum: Durum = "uyumlu" if metin_yonu == model_yonu else "celiski"
    return YonDenetimi(durum, metin_yonu, model_yonu)


def yon_dogrula(sinir: Sinir) -> YonDenetimi:
    """Sınırın yönünü (açık `yon` ya da alt/üstten çıkan) özgün metinle karşılaştırır."""
    return _karsilastir(sinir.yonu, sinir.orijinal_metin)


def yonu_guvenli_yap(sinir: Sinir) -> tuple[Sinir, YonDenetimi]:
    """Çelişki varsa sınırın kopyasını `yon="belirsiz"` yapar (sayılar korunur); yoksa aynen döner."""
    denetim = yon_dogrula(sinir)
    if denetim.durum == "celiski":
        return sinir.model_copy(update={"yon": "belirsiz"}), denetim
    return sinir, denetim


def okuma_yonu_dogrula(okuma: HamOkuma) -> YonDenetimi:
    """Ürün sözleşmesi: modelin `sinir_yonu`'nu okuduğu ham metinle karşılaştırır."""
    if okuma.alan != "sinir":
        return YonDenetimi("sayisal_degil")
    return _karsilastir(okuma.sinir_yonu, okuma.ham_metin)
