"""Birim doğrulaması (pint).

Şemadaki birimler pint'in tanıdığı biçimde yazılır ("°C", "g/L", "mil",
"month"). Birim dönüşümü de ileride bu kayıt (registry) üzerinden kesin
kurallarla yapılır; dil modeli birim çevirmez (CLAUDE.md, kural 1).
"""

from __future__ import annotations

from functools import lru_cache

import pint


@lru_cache(maxsize=1)
def kayit() -> pint.UnitRegistry:
    return pint.UnitRegistry()


def birimi_coz(birim: str) -> pint.Unit:
    """Birim metnini pint birimine çevirir; tanınmazsa ValueError verir."""
    if not birim or not birim.strip():
        raise ValueError("birim boş")
    try:
        return kayit().parse_units(birim)
    except (pint.errors.UndefinedUnitError, pint.errors.DefinitionSyntaxError, AttributeError, TypeError) as hata:
        raise ValueError(f"pint bu birimi tanımıyor: {birim!r}") from hata
    except Exception as hata:  # pint ayrıştırıcısı bozuk ifadelerde farklı hatalar verebilir
        raise ValueError(f"birim ayrıştırılamadı: {birim!r}") from hata


def birim_gecerli_mi(birim: str) -> bool:
    try:
        birimi_coz(birim)
    except ValueError:
        return False
    return True


def zaman_birimi_mi(birim: str) -> bool:
    """Birim bir zaman birimi mi (gün, ay, yıl, saat...)?"""
    try:
        return birimi_coz(birim).dimensionality == kayit().second.dimensionality
    except ValueError:
        return False
