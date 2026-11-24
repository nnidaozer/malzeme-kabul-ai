"""Karar motoru: yönü belirsiz şartlar ve iç laboratuvar testleri insan incelemesine gider (docs/mimari.md)."""

from __future__ import annotations

from malzeme_kabul.kural.karar_motoru import kontrol_et
from malzeme_kabul.sozlesme.sema import KabulDokumani
from malzeme_kabul.sozlesme.sertifika import Sertifika, SertifikaSatiri


def _test(id_, ad, sinir, **k):
    return {
        "id": id_, "test_adi": ad, "sinir": sinir, "test_turleri": ["kabul"],
        "kaynak": {"belge_no": "MIL-PRF-23377", "revizyon": "K", "madde": "3.11"}, **k,
    }


def _dokuman(*testler) -> KabulDokumani:
    return KabulDokumani.model_validate({"standart": {"belge_no": "MIL-PRF-23377", "revizyon": "K"}, "testler": list(testler)})


def _sertifika(*satirlar) -> Sertifika:
    return Sertifika(
        sertifika_no="S-1", standart_atfi="MIL-PRF-23377K Type I Class C2",
        satirlar=[SertifikaSatiri(test_adi=a, sonuc=s, birim=b) for a, s, b in satirlar],
    )


SURE = {"kriter_turu": "sayisal", "alt": 4, "birim": "hour", "orijinal_metin": "shall have a pot life of 4 hours"}


def test_yonu_belirsiz_sart_karsilastirilmaz_insana_gider():
    d = _dokuman(_test("pot_life", "Pot life", dict(SURE, yon="belirsiz")))
    sonuc = kontrol_et(d, _sertifika(("Pot life", "6", "hour")))
    satir = sonuc.satirlar[0]
    assert satir.karar == "insan_incelemeli"
    assert "yönü belirsiz" in satir.gerekce
    assert satir.okunan_sonuc == "6"  # okunan değer yine kayda geçer
    assert sonuc.belge_karari == "inceleme"


def test_ayni_sart_yonu_belliyse_karar_verilir():
    d = _dokuman(_test("pot_life", "Pot life", SURE))
    assert kontrol_et(d, _sertifika(("Pot life", "6", "hour"))).satirlar[0].karar == "uygun"


def test_ic_laboratuvar_testi_cocde_aranmaz_ve_parti_bekletilir():
    d = _dokuman(
        _test("pot_life", "Pot life", SURE),
        _test("adhesion", "Adhesion", {"kriter_turu": "sayisal", "alt": 4, "orijinal_metin": "4A"}, sonuc_kaynagi="ic_laboratuvar"),
    )
    # CoC'de yapışma değeri olsa bile kullanılmaz; eşleşmeyen satır da sayılmaz.
    sonuc = kontrol_et(d, _sertifika(("Pot life", "6", "hour"), ("Adhesion", "5A", None)))
    kararlar = {s.test_id: s for s in sonuc.satirlar}
    assert [s.test_id for s in sonuc.satirlar] == ["pot_life", "adhesion"]  # doküman sırası korunur
    assert kararlar["pot_life"].karar == "uygun"
    assert kararlar["adhesion"].karar == "insan_incelemeli"
    assert "iç laboratuvar" in kararlar["adhesion"].gerekce
    assert kararlar["adhesion"].okunan_sonuc is None
    assert sonuc.eslesmeyen_satirlar == []
    assert sonuc.belge_karari == "inceleme"


def test_uygun_degil_varsa_parti_ic_laboratuvari_beklemeden_reddedilir():
    d = _dokuman(
        _test("pot_life", "Pot life", SURE),
        _test("adhesion", "Adhesion", {"kriter_turu": "sayisal", "alt": 4, "orijinal_metin": "4A"}, sonuc_kaynagi="ic_laboratuvar"),
    )
    assert kontrol_et(d, _sertifika(("Pot life", "2", "hour"))).belge_karari == "red"
