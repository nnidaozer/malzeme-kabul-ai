"""Plan adım 1: alan düzleştirme üründe tek kaynaktır (malzeme_kabul.sozlesme.alanlar).

deney/degerlendirme.py aynı adları oradan yeniden dışa verir; iki ayrı kopya olmaz.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
ADLAR = ("alanlari_duzlestir", "degerler_esit", "kayit_bolumleri", "_Birim", "_normal_metin")


def test_alan_fonksiyonlari_urun_modulunden_ice_aktarilir():
    from malzeme_kabul.sozlesme.alanlar import alanlari_duzlestir, degerler_esit, kayit_bolumleri  # noqa: F401


@pytest.mark.parametrize("ad", ADLAR)
def test_deney_degerlendirme_ayni_nesneyi_yeniden_disa_verir(ad):
    import deney.degerlendirme as deney_mod
    from malzeme_kabul.sozlesme import alanlar

    assert getattr(deney_mod, ad) is getattr(alanlar, ad)


def test_deney_degerlendirme_alan_fonksiyonlarini_kendisi_tanimlamaz():
    agac = ast.parse((KOK / "deney" / "degerlendirme.py").read_text(encoding="utf-8"))
    tanimli = {d.name for d in agac.body if isinstance(d, (ast.FunctionDef, ast.ClassDef))}
    assert not tanimli & set(ADLAR), tanimli & set(ADLAR)


def test_urun_alanlar_modulu_birim_esitligini_pint_ile_karsilastirir():
    from malzeme_kabul.sozlesme.alanlar import _Birim, degerler_esit

    assert degerler_esit(_Birim("s"), _Birim("second"))
    assert not degerler_esit(_Birim("s"), _Birim("min"))
