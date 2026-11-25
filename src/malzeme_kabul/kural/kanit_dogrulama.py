"""Kanıt doğrulayıcı: dil modelinin okuduğu metin belgede, söylediği sayfada var mı?

Dil modeli bir hücreyi uydurabilir, değiştirebilir (ör. "0.4" yerine "0.04")
ya da başka sayfadan okuyabilir. Bu modül her okumayı belgenin metin
katmanıyla kesin kurallarla karşılaştırır:

- Karşılaştırma boşluk ve büyük/küçük harf farkını yok sayar; başka hiçbir
  değişikliğe izin vermez (sayı, birim, işaret aynen bulunmalıdır).
- Metin söylenen sayfada yoksa okuma **kanıtsız** sayılır. Hat kanıtsız
  okumayı karara sokmaz ve insan incelemesi ister.

Not: Kanıt, metnin belgede *bir yerde* geçtiğini gösterir; doğru satıra ait
olduğunu göstermez. Satır bütünlüğü için `satir_kaniti` hücrelerin aynı metin
satırında birlikte geçtiğini de arar (tablo satırları metin katmanında tek
satırdır).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from malzeme_kabul.sozlesme.okuma import HamOkuma, SertifikaSatirOkumasi


def _normal(metin: str) -> str:
    return " ".join(metin.split()).casefold()


def metin_sayfada_mi(metin: str, sayfa_metni: str) -> bool:
    """Metin (boşluk ve harf büyüklüğü dışında aynen) sayfada geçiyor mu?"""
    hedef = _normal(metin)
    return bool(hedef) and hedef in _normal(sayfa_metni)


@dataclass(frozen=True)
class KanitSonucu:
    kanitli: bool
    neden: str


def okuma_kaniti(okuma: HamOkuma, sayfalar: dict[int, str]) -> KanitSonucu:
    """Standart okumasının (`HamOkuma`) ham metni söylenen sayfada mı?"""
    sayfa = sayfalar.get(okuma.konum.sayfa)
    if sayfa is None:
        return KanitSonucu(False, f"sayfa {okuma.konum.sayfa} belgede yok")
    if not metin_sayfada_mi(okuma.ham_metin, sayfa):
        return KanitSonucu(False, f"{okuma.ham_metin!r} sayfa {okuma.konum.sayfa} metninde yok")
    return KanitSonucu(True, "metin sayfada bulundu")


def _kelime_sinirli(hucre: str) -> re.Pattern[str]:
    # "4" hücresi "4.1" ya da "14" içinde bulunmuş sayılmasın.
    return re.compile(rf"(?<![\w.,]){re.escape(_normal(hucre))}(?![\w]|[.,]\d)")


def satir_kaniti(okuma: SertifikaSatirOkumasi, sayfalar: dict[int, str]) -> KanitSonucu:
    """Sertifika satırının hücreleri söylenen sayfada, aynı metin satırında mı?"""
    sayfa = sayfalar.get(okuma.sayfa)
    if sayfa is None:
        return KanitSonucu(False, f"sayfa {okuma.sayfa} belgede yok")
    hucreler = [h for h in (okuma.test_adi, okuma.sonuc_hucresi, okuma.birim_hucresi) if h]
    eksik = [h for h in hucreler if not metin_sayfada_mi(h, sayfa)]
    if eksik:
        return KanitSonucu(False, f"sayfa {okuma.sayfa} metninde yok: {', '.join(repr(h) for h in eksik)}")
    satirlar = [_normal(s) for s in sayfa.splitlines()]
    ad = _normal(okuma.test_adi)
    sonuc = _kelime_sinirli(okuma.sonuc_hucresi)
    # Hücre içinde satır sonu olabilir: test adının geçtiği satır ve sonraki satır birlikte aranır.
    for i, s in enumerate(satirlar):
        if ad in s:
            pencere = " ".join(satirlar[i:i + 2])
            if sonuc.search(pencere.split(ad, 1)[1]):
                return KanitSonucu(True, "hücreler aynı satırda bulundu")
    return KanitSonucu(False, f"{okuma.sonuc_hucresi!r} sonucu {okuma.test_adi!r} satırında değil")


__all__ = ["KanitSonucu", "metin_sayfada_mi", "okuma_kaniti", "satir_kaniti"]
