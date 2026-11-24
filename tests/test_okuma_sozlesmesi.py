"""Dil modelinin ham okuma sözleşmesinin testleri (docs/mimari.md madde 6)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from malzeme_kabul.sozlesme.okuma import HamOkuma, KaynakKonum, OkumaYaniti


def okuma(**k):
    temel = {"sart_id": "viscosity", "alan": "sinir", "ham_metin": "15 to 30 seconds", "konum": {"sayfa": 7, "madde": "3.6.3"}}
    temel.update(k)
    return HamOkuma.model_validate(temel)


def test_ham_okuma_metni_degistirmeden_tasir():
    o = okuma(sinir_yonu="aralik")
    assert o.ham_metin == "15 to 30 seconds"
    assert o.konum == KaynakKonum(sayfa=7, madde="3.6.3")


def test_okumada_sayi_birim_ya_da_karar_alani_yoktur():
    for alan in ("alt", "ust", "birim", "deger", "karar"):
        with pytest.raises(ValidationError):
            okuma(**{alan: 15})
    sema = json.dumps(OkumaYaniti.model_json_schema())
    assert '"number"' not in sema  # modelin üretebildiği tek sayı sayfa/satır sırasıdır (integer)


def test_yon_yalniz_sinir_okumasinda():
    assert okuma(sinir_yonu="belirsiz").sinir_yonu == "belirsiz"
    with pytest.raises(ValidationError, match="yalnız 'sinir'"):
        okuma(alan="test_metodu", ham_metin="ASTM D 1200", sinir_yonu="en_az")


@pytest.mark.parametrize("konum", [{"sayfa": 0}, {"sayfa": 3, "madde": "üçüncü madde"}, {"sayfa": 3, "tablo_satiri": 0}])
def test_gecersiz_konum_reddedilir(konum):
    with pytest.raises(ValidationError):
        okuma(konum=konum)


def test_bos_metin_reddedilir():
    with pytest.raises(ValidationError):
        okuma(ham_metin="   ")
