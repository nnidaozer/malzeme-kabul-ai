"""Tedarikçi sertifikası (CoC / test raporu) şeması.

Sertifika tablosundaki her hücre okunduğu gibi, ham metin olarak tutulur:
test adı, sonuç ve birim. Adın kabul dokümanındaki testle eşleştirilmesi,
sonucun sayıya çevrilmesi, birim dönüşümü ve sınır karşılaştırması karar
motorunda kesin kurallarla yapılır (CLAUDE.md, kural 1). Belgeyi okuyan
taraf (ileride yerel dil modeli) yalnızca bu ham metinleri doldurur.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SertifikaSatiri(_Model):
    """Sertifikadaki test tablosunun bir satırı (ham metin)."""

    test_adi: str = Field(min_length=1)
    sonuc: str = Field(description="Sonuç hücresi, ör. '320', '<1', '5A', 'Conforms'.")
    birim: str | None = Field(default=None, description="Birim hücresi, ör. 'g/L', 'min', 'mil'.")
    metot: str | None = None
    sart: str | None = Field(default=None, description="Tedarikçinin yazdığı şart, ör. '340 max'. Karar için kullanılmaz.")


class Sertifika(_Model):
    """Bir partiye ait uygunluk sertifikası ve test raporu."""

    sertifika_no: str = Field(min_length=1)
    standart_atfi: str = Field(description="Sertifikadaki atıf, ör. 'MIL-PRF-23377K Type I Class C2'.")
    tedarikci: str | None = None
    urun: str | None = None
    parti_no: str | None = None
    uretim_tarihi: str | None = None
    son_kullanma_tarihi: str | None = None
    siparis_no: str | None = None
    satirlar: list[SertifikaSatiri] = Field(default_factory=list)
