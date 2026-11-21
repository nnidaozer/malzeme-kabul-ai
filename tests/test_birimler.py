"""pint tabanlı birim doğrulamasının testleri."""

from __future__ import annotations

import pytest

from malzeme_kabul.birimler import birim_gecerli_mi, birimi_coz, zaman_birimi_mi


@pytest.mark.parametrize("birim", ["°C", "degF", "°F", "g/L", "s", "mil", "hour", "%", "psi", "lb/gal", "µm"])
def test_pintin_tanidigi_birimler_gecerli(birim):
    assert birim_gecerli_mi(birim)


@pytest.mark.parametrize("birim", ["ay", "saniyeler", "xyz/L", ""])
def test_tanimsiz_ya_da_bos_birim_gecersiz(birim):
    assert not birim_gecerli_mi(birim)


def test_birimi_coz_pint_birimi_doner():
    assert str(birimi_coz("g/L")) == "gram / liter"


def test_birimi_coz_tanimsiz_birimde_valueerror_verir():
    with pytest.raises(ValueError):
        birimi_coz("ay")


@pytest.mark.parametrize("birim, beklenen", [("month", True), ("day", True), ("year", True), ("hour", True), ("°C", False), ("g/L", False)])
def test_zaman_birimi_mi(birim, beklenen):
    assert zaman_birimi_mi(birim) is beklenen
