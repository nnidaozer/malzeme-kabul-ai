"""Kural okuması ile dil modeli okuması arasındaki anlaşmazlık (proje sahibinin kuralı).

Hibrit hatta karara modelin (kanıtlı) okuması girer. Kural okuyucu ile dil
modeli aynı test için farklı değer, birim, sınır, yön ya da standart atfı
bulursa hiçbir okuma sessizce karara girmez: o şart insan incelemesine gider
(iki okuma da sınır dışındaysa uygun değil kalır, bkz. `anlasmazlik_karari`)
ve anlaşmazlık kaydı tutulur (ileride güven skorunun girdisi).

Karşılaştırma tamamen kesin kurallarla yapılır (CLAUDE.md kural 1); dil
modeline hangi okumanın doğru olduğu sorulmaz. Bu modül `cikarim`, `hat` ve
`arayuz` katmanlarını içe aktarmaz.

Sertifika tarafı (`sertifika_okumalarini_karsilastir`):

- Satırlar `karar_motoru.eslestir` ile, `kontrol_et`'in kullandığı kümeye
  (`karar_motoru.aranan_testler`: tip/sınıfa uygulanan, sonucu CoC'den gelen
  kabul testleri) eşlenir; eşlenmeyen satır yok sayılır (karara da girmez).
  Tip/sınıf verilmezse `kontrol_et` gibi kural okumasının atfından alınır.
- Standart atfı: belge no, revizyon, tip ve sınıf (`atfi_coz`) farklıysa
  `test_id="revizyon"`, `alan="deger"` anlaşmazlığı yazılır; yalnız yazım
  farkı ("23377K" / "23377 K," / "Rev. K") anlaşmazlık değildir.
- Değer: sayısal sonuçta sayı, karşılaştırma işareti ve dahil/hariç
  (`sonucu_ayristir`) ile sayının arkasındaki ek aynı olmalı ("320" = "320.0",
  "<1" = "< 1"; "<1" ≠ "<=1" ≠ "1"; "4A" ≠ "4B"). Sayısal olmayan sonuçta
  boşluk ve büyük/küçük harf normalleştirilmiş metin karşılaştırılır.
- Birim: önce karar motorunun eş anlamlı tablosu (yalnız birebir anahtar;
  harf duyarlı) ve pint (`birimler.birimi_coz`, "mil" = inçin binde biri) ile
  çözülür; aynı birime çözülenler eşittir ("g/L" = "g / L" = "g/l"; "mg" ≠
  "Mg", "G/L" gauss/litre). pint çözemezse iç boşlukları tekleştirilmiş metin
  harf duyarlı karşılaştırılır ("KU" ≠ "Ku"). Bir tarafta boş, ötekinde dolu
  ise farklıdır. Değer çevrilmez: "h" ile "min" farklı okumadır.
- Satır yalnız bir tarafta varsa `alan="satir"`.

Standart tarafı (`standart_okumalarini_karsilastir`): modelin `sinir`
okumaları kural dokümanındaki sınırla karşılaştırılır. Yön: modelin
`sinir_yonu` (boş ya da `belirsiz` ise karşılaştırılmaz) ile sınırın yönü
(açık `yon` ya da alt/üstten çıkan). Sınır: ham metindeki sayılar ile alt/üst
sınır kümesi. İşaretler yok sayılır ("15-30" metnindeki tire eksi sayılmasın).
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Literal

from pint.errors import PintError
from pydantic import BaseModel, ConfigDict

from malzeme_kabul.kural.birimler import birimi_coz, kayit
from malzeme_kabul.kural.karar_motoru import (
    BIRIM_ESANLAMLILARI,
    Karar,
    aranan_testler,
    atfi_coz,
    eslestir,
    kod_normallestir,
    sonucu_ayristir,
)
from malzeme_kabul.sozlesme.okuma import HamOkuma
from malzeme_kabul.sozlesme.sema import KabulDokumani, TestSarti
from malzeme_kabul.sozlesme.sertifika import Sertifika, SertifikaSatiri

Taraf = Literal["sertifika", "standart"]
AnlasmazlikAlani = Literal["deger", "birim", "sinir", "yon", "satir"]


class Anlasmazlik(BaseModel):
    """Kural ve modelin aynı test için farklı okuduğu tek bir alan."""

    model_config = ConfigDict(extra="forbid")

    taraf: Taraf
    test_id: str
    test_adi: str
    alan: AnlasmazlikAlani
    kural: str | None  # kuralın okuduğu ham metin; okumadıysa None
    model: str | None  # modelin okuduğu ham metin; okumadıysa None
    aciklama: str


# --- normalleştirme --------------------------------------------------------------------

_SAYI_EKI = re.compile(r"^\s*(?:<=|>=|≤|≥|<|>)?\s*[+-]?\d+(?:[.,]\d+)?\s*(?P<ek>.*)$", re.DOTALL)


def _metin(deger: str | None) -> str | None:
    """Boşluğu tekleştirilmiş, küçük harfli metin; boşsa None."""
    if deger is None:
        return None
    normal = " ".join(deger.split()).casefold()
    return normal or None


def _sayi_eki(sonuc: str) -> str:
    """Sayısal sonucun sayıdan sonraki eki, normalleştirilmiş ("4A" → "a", "320" → "").

    `sonucu_ayristir` yapışma derecesi harflerini ("4A", "5B") atar; bu ek, iki
    okumanın yalnız harfte ayrıldığı durumu yakalamak için ayrıca karşılaştırılır.
    Sonuç sayıyla başlamıyorsa ("ND (<0.5 ppm)") bütün metin döner.
    """
    m = _SAYI_EKI.match(sonuc or "")
    return _metin(m.group("ek") if m else sonuc) or ""


def _deger_anahtari(sonuc: str) -> tuple:
    s = sonucu_ayristir(sonuc)
    if s.tur == "sayi":
        return ("sayi", s.alt, s.ust, s.alt_dahil, s.ust_dahil, _sayi_eki(sonuc))
    return ("metin", _metin(sonuc))


def _birim_anahtari(birim: str | None) -> tuple | None:
    """Birimin karşılaştırma anahtarı: pint'in çözdüğü birimin taban birimdeki karşılığı, yoksa metin."""
    if birim is None or not birim.strip():
        return None
    ham = birim.strip()
    try:
        birim_ = birimi_coz(BIRIM_ESANLAMLILARI.get(ham, ham))
    except ValueError:
        return ("metin", " ".join(ham.split()))
    try:
        taban = kayit().Quantity(1, birim_).to_base_units()
        return ("pint", f"{taban.magnitude:.9g}", str(taban.units))
    except (PintError, TypeError, ValueError):  # pint: taban birime indirilemeyen ifade
        return ("pint", str(birim_))


def _satir_anahtari(satir: SertifikaSatiri) -> tuple:
    return (_deger_anahtari(satir.sonuc), _birim_anahtari(satir.birim))


def anlasmazlik_karari(model_karari: Karar, kural_karari: Karar | None) -> Karar:
    """Anlaşmazlığı olan şartın kararı: iki okuma da uygun değilse uygun değil, değilse insan incelemeli.

    Kararlar iki okumanın her biri için kural motoruyla (`kontrol_et`) verilir;
    burada yalnız birleştirilir. Okumalardan biri sınırın içindeyse hiçbiri
    sessizce karara girmez.
    """
    if model_karari == "uygun_degil" and kural_karari == "uygun_degil":
        return "uygun_degil"
    return "insan_incelemeli"


# --- sertifika tarafı ------------------------------------------------------------------


def _eslenmis(testler: list[TestSarti], sertifika: Sertifika) -> dict[str, list[SertifikaSatiri]]:
    gruplar: dict[str, list[SertifikaSatiri]] = defaultdict(list)
    for satir in sertifika.satirlar:
        test_id = eslestir(satir.test_adi, testler)
        if test_id is not None:
            gruplar[test_id].append(satir)
    return gruplar


def _hucreler(satirlar: list[SertifikaSatiri]) -> str:
    return "; ".join(f"{s.sonuc} {s.birim}" if s.birim else s.sonuc for s in satirlar)


def _atif_anahtari(atif: str | None) -> tuple:
    a = atfi_coz(atif or "")
    return (a.belge_no, a.revizyon, a.tip, a.sinif)


def sertifika_okumalarini_karsilastir(
    dokuman: KabulDokumani,
    kural: Sertifika,
    model: Sertifika,
    tip: str | None = None,
    sinif: str | None = None,
) -> list[Anlasmazlik]:
    """Kuralın ve modelin aynı sertifikadan okuduğu standart atfını ve satırları karşılaştırır.

    `tip` ve `sinif` (katalogdaki malzemenin) `kontrol_et`'teki gibi aranan
    testleri seçer; verilmezse kural okumasının atfından alınır. Dönen liste
    `test_id`, sonra alana göre sıralıdır; satır sırası sonucu değiştirmez.
    Aynı teste birden çok satır eşlenmişse satır kümeleri karşılaştırılır;
    farklıysa tek bir değer anlaşmazlığı yazılır.
    """
    if tip is not None or sinif is not None:
        tip, sinif = kod_normallestir(tip), kod_normallestir(sinif)
    else:
        atif = atfi_coz(kural.standart_atfi or "")
        tip, sinif = atif.tip, atif.sinif
    testler = aranan_testler(dokuman, tip, sinif)
    adlar = {t.id: t.test_adi for t in testler}
    k_gruplar, m_gruplar = _eslenmis(testler, kural), _eslenmis(testler, model)
    sonuc: list[Anlasmazlik] = []
    if _atif_anahtari(kural.standart_atfi) != _atif_anahtari(model.standart_atfi):
        sonuc.append(Anlasmazlik(
            taraf="sertifika", test_id="revizyon", test_adi="Standart ve revizyon atfı", alan="deger",
            kural=kural.standart_atfi, model=model.standart_atfi,
            aciklama=f"standart atfı: kural {kural.standart_atfi!r}, model {model.standart_atfi!r}",
        ))
    for test_id in sorted(set(k_gruplar) | set(m_gruplar)):
        k, m = k_gruplar.get(test_id, []), m_gruplar.get(test_id, [])
        ortak = {"taraf": "sertifika", "test_id": test_id, "test_adi": adlar[test_id]}
        if not k or not m:
            sonuc.append(Anlasmazlik(
                alan="satir", kural=k[0].sonuc if k else None, model=m[0].sonuc if m else None,
                aciklama="satırı yalnız " + ("kural" if k else "model") + " okudu", **ortak,
            ))
            continue
        if len(k) > 1 or len(m) > 1:
            if sorted(map(_satir_anahtari, k), key=repr) != sorted(map(_satir_anahtari, m), key=repr):
                sonuc.append(Anlasmazlik(
                    alan="deger", kural=_hucreler(k), model=_hucreler(m),
                    aciklama=f"test birden çok satırda; kural {_hucreler(k)!r}, model {_hucreler(m)!r}", **ortak,
                ))
            continue
        ks, ms = k[0], m[0]
        if _deger_anahtari(ks.sonuc) != _deger_anahtari(ms.sonuc):
            sonuc.append(Anlasmazlik(
                alan="deger", kural=ks.sonuc, model=ms.sonuc,
                aciklama=f"değer: kural {ks.sonuc!r}, model {ms.sonuc!r}", **ortak,
            ))
        if _birim_anahtari(ks.birim) != _birim_anahtari(ms.birim):
            sonuc.append(Anlasmazlik(
                alan="birim", kural=ks.birim, model=ms.birim,
                aciklama=f"birim: kural {ks.birim!r}, model {ms.birim!r}", **ortak,
            ))
    return sorted(sonuc, key=lambda a: (a.test_id, a.alan))


# --- standart tarafı -------------------------------------------------------------------

# Madde numaralarının ("4.6.13") parçaları sayı sayılmaz (yon_dogrulama ile aynı kalıp, işaretsiz).
_STANDART_SAYI = re.compile(r"(?<![\d.])\d+(?:,\d{3})*(?:\.\d+)?(?![\d,]*\.\d)")


def _metindeki_sayilar(metin: str) -> set[float]:
    """Ham sınır metnindeki sayılar (işaretsiz; binlik virgülü atılır)."""
    return {float(s.replace(",", "")) for s in _STANDART_SAYI.findall(metin)}


def _sayi_metni(x: float) -> str:
    return f"{x:g}"


def _standart_okuma_anlasmazliklari(okuma: HamOkuma, test: TestSarti) -> list[Anlasmazlik]:
    sinir = test.sinir
    if okuma.alan != "sinir" or sinir.kriter_turu != "sayisal":
        return []
    ortak = {"taraf": "standart", "test_id": test.id, "test_adi": test.test_adi}
    sonuc: list[Anlasmazlik] = []
    kural_sayilari = {abs(x) for x in (sinir.alt, sinir.ust) if x is not None}
    model_sayilari = _metindeki_sayilar(okuma.ham_metin)
    if model_sayilari != kural_sayilari:
        kural_metni = " / ".join(_sayi_metni(x) for x in sorted(kural_sayilari))
        sonuc.append(Anlasmazlik(
            alan="sinir", kural=kural_metni, model=okuma.ham_metin,
            aciklama=f"sınır: kural {kural_metni}, model {okuma.ham_metin!r}", **ortak,
        ))
    kural_yonu = sinir.yonu
    if okuma.sinir_yonu not in (None, "belirsiz") and kural_yonu not in (None, "belirsiz") and okuma.sinir_yonu != kural_yonu:
        sonuc.append(Anlasmazlik(
            alan="yon", kural=kural_yonu, model=okuma.sinir_yonu,
            aciklama=f"sınır yönü: kural {kural_yonu}, model {okuma.sinir_yonu}", **ortak,
        ))
    return sonuc


def standart_okumalarini_karsilastir(okumalar: list[HamOkuma], dokuman: KabulDokumani) -> list[Anlasmazlik]:
    """Modelin standarttan okuduğu sınırları kural dokümanındaki sınırlarla karşılaştırır.

    Yalnız `sinir` alanındaki okumalar ve sayısal kriterler karşılaştırılır;
    dokümanda olmayan `sart_id` atlanır. Sonuç `test_id`, sonra alana göre sıralıdır.
    """
    testler = {t.id: t for t in dokuman.testler}
    sonuc: list[Anlasmazlik] = []
    for okuma in okumalar:
        test = testler.get(okuma.sart_id)
        if test is not None:
            sonuc.extend(_standart_okuma_anlasmazliklari(okuma, test))
    return sorted(sonuc, key=lambda a: (a.test_id, a.alan))


__all__ = [
    "Anlasmazlik",
    "AnlasmazlikAlani",
    "Taraf",
    "anlasmazlik_karari",
    "sertifika_okumalarini_karsilastir",
    "standart_okumalarini_karsilastir",
]
