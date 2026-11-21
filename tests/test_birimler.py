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


@pytest.mark.parametrize("birim", ["mil", "mils"])
def test_mil_uzunluk_birimidir_thou(birim):
    # pint "mil" birimini açı sayar; kaplamada mil = inç/1000 = 25,4 µm
    from malzeme_kabul.birimler import kayit

    assert birimi_coz(birim).dimensionality == kayit().meter.dimensionality
    assert kayit().Quantity(1, birimi_coz(birim)).to("µm").magnitude == pytest.approx(25.4)


def test_milin_gectigi_bilesik_birimler_bozulmaz():
    assert str(birimi_coz("mL")) == "milliliter"
    assert str(birimi_coz("mile")) == "mile"


def test_semada_mil_birimli_sinir_mikrometreye_cevrilir():
    from malzeme_kabul.birimler import kayit
    from malzeme_kabul.sema import Sinir

    s = Sinir(kriter_turu="sayisal", alt=0.6, ust=0.9, birim="mil", orijinal_metin="0.6 to 0.9 mil")
    assert kayit().Quantity(s.ust, birimi_coz(s.birim)).to("µm").magnitude == pytest.approx(22.86)
