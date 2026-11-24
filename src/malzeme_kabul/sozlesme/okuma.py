"""Dil modelinin ham okuması: ürünün içinde dil modelinin döndürebileceği tek şey.

docs/mimari.md madde 6: dil modeli yalnızca ham metin, kaynak konum ve sınır
yönü döndürür. Sayı, birim ya da karar alanı yoktur; okunan metnin sayıya ve
pint birimine çevrilmesi (normalleştirme), birim dönüşümü ve sınırla
karşılaştırma `malzeme_kabul.kural` içinde kesin kurallarla yapılır
(CLAUDE.md, kural 1).

Model emin değilse yönü "belirsiz" yazar; kural bunu değiştirmez, karar
motoru o şartı insan incelemesine gönderir.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from malzeme_kabul.sozlesme.sema import MADDE_KALIBI, SinirYonu

OkunanAlan = Literal["test_adi", "test_metodu", "sinir", "birim", "raf_omru", "kosul", "uygulanabilirlik"]
"""Okumanın kabul dokümanında hangi alana gideceği."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class KaynakKonum(_Model):
    """Okunan metnin belgedeki yeri: sayfa (zorunlu), madde ve tablo satırı."""

    sayfa: int = Field(ge=1)
    madde: str | None = Field(default=None, examples=["3.11", "TABLE I"])
    tablo_satiri: int | None = Field(default=None, ge=1, description="Tablodaysa 1'den başlayan satır sırası.")

    @field_validator("madde")
    @classmethod
    def _madde_bicimi(cls, deger: str | None) -> str | None:
        if deger is not None and not MADDE_KALIBI.match(deger):
            raise ValueError(f"madde numarası '3.5.1' ya da 'TABLE I' biçiminde olmalı: {deger!r}")
        return deger


class HamOkuma(_Model):
    """Belgeden okunan tek bir parça, sayfada yazdığı gibi."""

    sart_id: str = Field(min_length=1, description="Okumanın ait olduğu şart, ör. 'viscosity'.")
    alan: OkunanAlan
    ham_metin: str = Field(min_length=1, description="Belgede yazan metin, değiştirilmeden. Ör. '15 to 30 seconds'.")
    konum: KaynakKonum
    sinir_yonu: SinirYonu | None = Field(
        default=None, description="Yalnız alan 'sinir' iken. Emin değilsen 'belirsiz'."
    )

    @field_validator("sinir_yonu")
    @classmethod
    def _yon_yalniz_sinirda(cls, deger, bilgi):
        if deger is not None and bilgi.data.get("alan") != "sinir":
            raise ValueError("sınır yönü yalnız 'sinir' alanındaki okumada verilir")
        return deger


class OkumaYaniti(_Model):
    """Modelin bir sayfa için döndüğü yanıt."""

    okumalar: list[HamOkuma] = Field(default_factory=list)
