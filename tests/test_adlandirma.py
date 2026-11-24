"""Dosya adından belge no ve revizyon."""

import pytest

from malzeme_kabul.belge.adlandirma import belge_no_ve_revizyon


def test_dosya_adindan_belge_no_ve_revizyon():
    assert belge_no_ve_revizyon("data/raw/MIL-PRF-23377K.pdf") == ("MIL-PRF-23377", "K")
    assert belge_no_ve_revizyon("MIL-PRF-85285E.pdf") == ("MIL-PRF-85285", "E")
    with pytest.raises(ValueError):
        belge_no_ve_revizyon("rapor.pdf")
