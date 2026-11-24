"""Karar motoru ölçümünün (yakalama, yanlış kabul) testleri."""

from __future__ import annotations

import pytest

from malzeme_kabul.kural.karar_motoru import KararSatiri, KontrolSonucu
from deney.karar_olcumu import DogruKarar, olc


def _tahmin(no, belge, satirlar=None):
    satirlar = satirlar or {}
    return KontrolSonucu(
        sertifika_no=no,
        belge_karari=belge,
        revizyon=KararSatiri(test_id="revizyon", test_adi="Revizyon", karar="uygun", gerekce=""),
        satirlar=[KararSatiri(test_id=t, test_adi=t, karar=k, gerekce="") for t, k in satirlar.items()],
    )


def _dogru(no, belge, tur=None, satirlar=None):
    return DogruKarar(sertifika_no=no, belge_karari=belge, hata_turu=tur, satirlar=satirlar or {})


def test_yanlis_kabul_ve_yakalama_orani():
    dogrular = [
        _dogru("1", "kabul"),
        _dogru("2", "red", "sinir_disi"),
        _dogru("3", "red", "sinir_disi"),
        _dogru("4", "inceleme", "eksik_test"),
        _dogru("5", "red", "birim"),
    ]
    tahminler = [
        _tahmin("1", "kabul"),
        _tahmin("2", "red"),
        _tahmin("3", "kabul"),  # yanlış kabul
        _tahmin("4", "red"),
        _tahmin("5", "inceleme"),
    ]
    o = olc(tahminler, dogrular)
    assert o.belge.yanlis_kabul_orani == pytest.approx(1 / 4)
    assert o.belge.yakalama_orani == pytest.approx(1 / 3)  # red olması gereken 3'ten 1'i red
    assert o.belge.dogruluk == pytest.approx(2 / 5)
    assert o.belge.otomasyon_orani == pytest.approx(4 / 5)  # incelemeye gitmeyen
    assert o.belge.karisiklik["red"]["kabul"] == 1


def test_hata_turune_gore_dokum():
    dogrular = [_dogru("1", "red", "sinir_disi"), _dogru("2", "red", "sinir_disi"), _dogru("3", "kabul", None)]
    tahminler = [_tahmin("1", "red"), _tahmin("2", "kabul"), _tahmin("3", "kabul")]
    o = olc(tahminler, dogrular)
    tur = o.hata_turune_gore["sinir_disi"]
    assert (tur.adet, tur.dogru, tur.yanlis_kabul) == (2, 1, 1)
    assert o.hata_turune_gore["temiz"].adet == 1


def test_satir_duzeyi_olcum():
    dogrular = [_dogru("1", "red", "sinir_disi", {"a": "uygun", "b": "uygun_degil", "c": "insan_incelemeli"})]
    tahminler = [_tahmin("1", "red", {"a": "uygun", "b": "uygun", "c": "insan_incelemeli"})]
    o = olc(tahminler, dogrular)
    assert o.satir.adet == 3
    assert o.satir.yanlis_kabul_orani == pytest.approx(1 / 2)
    assert o.satir.dogruluk == pytest.approx(2 / 3)


def test_tahmin_edilmeyen_satir_insan_incelemeli_sayilir():
    dogrular = [_dogru("1", "kabul", None, {"a": "uygun"})]
    tahminler = [_tahmin("1", "kabul", {})]
    o = olc(tahminler, dogrular)
    assert o.satir.karisiklik["uygun"]["insan_incelemeli"] == 1


def test_eksik_tahmin_hata_verir():
    with pytest.raises(ValueError):
        olc([], [_dogru("1", "kabul")])


def test_payda_sifirsa_oran_none():
    o = olc([_tahmin("1", "kabul")], [_dogru("1", "kabul")])
    assert o.belge.yanlis_kabul_orani is None
    assert o.belge.yakalama_orani is None
