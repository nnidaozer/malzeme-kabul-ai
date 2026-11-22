"""Doğru cevap dosyasındaki sayısal değerlerin PDF'te kanıtını arar.

Her sayısal değer (test sınırları, raf ömrü süresi ve koşulu, koşul sınırları,
kuru film kalınlığı), kaydın kaynak sayfasındaki PDF metninde aranır. Kaynak
sayfa verilmemişse madde numarasının geçtiği sayfalar kullanılır. Böylece
elle ya da bir modelle hazırlanmış taslakta uydurulmuş, yanlış sayfaya
bağlanmış ya da yanlış okunmuş değerler yakalanır.

Durumlar:
- `bulundu`: değer o sayfada rakamla, kesirle (ör. "1/8") ya da sözle (ör.
  "one") geçiyor.
- `turetildi`: değer sayfada geçmiyor ama bir `X ± Y` toleransından
  hesaplanıyor (X − Y ya da X + Y). Hesap doğru mu, elle bakılmalı.
- `sonraki_sayfada`: değer yalnızca bir sonraki sayfada geçiyor (madde sayfa
  sonunda devam ediyor olabilir ya da sayfa numarası yanlış).
- `bulunamadi`: değer ne o sayfada ne sonrakinde geçiyor.
- `sayfa_yok`: sayfa PDF'te yok ya da sayfa verilmemiş ve madde numarası
  hiçbir sayfada bulunamadı.

Kontrol yalnızca sayının varlığına bakar; birimi ve hangi cümlede geçtiğini
denetlemez. Değerler çevrilmez (CLAUDE.md, kural 1).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from .pdf_okuyucu import Belge
from .sema import KabulDokumani, Kaynak, Sinir

Durum = Literal["bulundu", "turetildi", "sonraki_sayfada", "bulunamadi", "sayfa_yok"]

_SAYI = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+(?!\d)|\d+(?:\.\d+)?|\.\d+)")
_EKSI = "-−–"
_TOLERANS = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?:±|\+/-|\+/−)\s*(\d+(?:\.\d+)?)")
_SOZCUKLER = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
}
_KESIR = re.compile(r"(?<![\w./])(\d+)/(\d+)(?![\w/])")
_SOZCUK = re.compile(r"\b(" + "|".join(_SOZCUKLER) + r")\b", re.IGNORECASE)


def _sayi(metin: str) -> float:
    return float(metin.replace(",", ""))


def metindeki_sayilar(metin: str, turetilmis: bool = False) -> set[float]:
    """Metinde geçen sayılar. `turetilmis` ise `X ± Y` toleranslarının uçları da eklenir."""
    sayilar: set[float] = set()
    for m in _SAYI.finditer(metin):
        deger = _sayi(m.group(1))
        sayilar.add(deger)
        bas = m.start()
        if bas and metin[bas - 1] in _EKSI and (bas == 1 or not metin[bas - 2].isalnum()):
            sayilar.add(-deger)
    sayilar |= {float(_SOZCUKLER[m.group(1).casefold()]) for m in _SOZCUK.finditer(metin)}
    sayilar |= {int(m.group(1)) / int(m.group(2)) for m in _KESIR.finditer(metin) if int(m.group(2))}
    if turetilmis:
        for m in _TOLERANS.finditer(metin):
            x, y = _sayi(m.group(1)), _sayi(m.group(2))
            sayilar |= {round(x - y, 9), round(x + y, 9)}
    return sayilar


def _icinde(deger: float, sayilar: set[float]) -> bool:
    return any(math.isclose(deger, s, rel_tol=1e-9, abs_tol=1e-9) for s in sayilar)


def _madde_kalibi(madde: str) -> re.Pattern[str]:
    if madde.upper().startswith("TABLE "):
        roma = madde.split(None, 1)[1]
        return re.compile(rf"\bTABLE\s+{roma}(?![IVXLC])", re.IGNORECASE)
    return re.compile(rf"(?<![\d.]){re.escape(madde)}(?!\d|\.\d)")


@dataclass(frozen=True)
class KanitSonucu:
    kayit: str
    alan: str
    deger: float
    madde: str
    sayfa: int | None
    durum: Durum
    madde_sayfada: bool | None = None


def _degerler(d: KabulDokumani) -> list[tuple[str, str, float, Kaynak]]:
    """(kayıt, alan, değer, kaynak) dörtlüleri; alan adları değerlendirmedeki gibi."""
    sonuc: list[tuple[str, str, float, Kaynak]] = []

    def sinir(kayit: str, onek: str, s: Sinir | None, k: Kaynak) -> None:
        if s is None or s.kriter_turu != "sayisal":
            return
        for ad in ("alt", "ust"):
            deger = getattr(s, ad)
            if deger is not None:
                sonuc.append((kayit, f"{onek}.{ad}", float(deger), k))

    for t in d.testler:
        sinir(t.id, "test.sinir", t.sinir, t.kaynak)
    for r in d.raf_omurleri:
        kayit = r.kap_turu or "genel"
        sonuc.append((kayit, "raf_omru.sure", float(r.sure), r.kaynak))
        sinir(kayit, "raf_omru.kosul", r.kosul, r.kaynak)
    for k in d.kosullar:
        sinir(f"{k.kategori}:{k.ad}", "kosul.sinir", k.sinir, k.kaynak)
    for n in d.numune_hazirlama:
        sinir(n.id, "numune.kuru_film_kalinligi", n.kuru_film_kalinligi, n.kaynak)
    return sonuc


def _degeri_ara(
    deger: float, madde: str, sayfalar: list[int], belge: Belge,
) -> tuple[Durum, int | None, bool | None]:
    metinler = {s.no: s.metin for s in belge.sayfalar}
    kalip = _madde_kalibi(madde)
    if not sayfalar:
        return "sayfa_yok", None, None
    for durum, kosul in (
        ("bulundu", lambda m: _icinde(deger, metindeki_sayilar(m))),
        ("turetildi", lambda m: _icinde(deger, metindeki_sayilar(m, turetilmis=True))),
    ):
        for no in sayfalar:
            if kosul(metinler[no]):
                return durum, no, bool(kalip.search(metinler[no]))
    ilk = sayfalar[0]
    sonraki = ilk + 1
    if sonraki in metinler and _icinde(deger, metindeki_sayilar(metinler[sonraki], turetilmis=True)):
        return "sonraki_sayfada", ilk, bool(kalip.search(metinler[ilk]))
    return "bulunamadi", ilk, bool(kalip.search(metinler[ilk]))


def kanit_kontrol(dokuman: KabulDokumani, belge: Belge) -> list[KanitSonucu]:
    """Belgedeki her sayısal değeri PDF'in ilgili sayfasında arar."""
    mevcut = {s.no for s in belge.sayfalar}
    sonuclar = []
    for kayit, alan, deger, kaynak in _degerler(dokuman):
        if kaynak.sayfa is not None:
            sayfalar = [kaynak.sayfa] if kaynak.sayfa in mevcut else []
        else:
            kalip = _madde_kalibi(kaynak.madde)
            sayfalar = [s.no for s in belge.sayfalar if kalip.search(s.metin)]
        durum, sayfa, madde_var = _degeri_ara(deger, kaynak.madde, sayfalar, belge)
        if durum == "sayfa_yok":
            sayfa = kaynak.sayfa
        sonuclar.append(KanitSonucu(kayit, alan, deger, kaynak.madde, sayfa, durum, madde_var))
    return sonuclar
