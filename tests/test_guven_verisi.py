"""Güven skoru verisi (deney): üç mod çıktısından girdi ve etiket (docs/guven_skoru.md).

Bütün veri burada elle kurulur ya da tmp_path altına yazılır. Gold yalnız
okunur; gerçek depodaki data/gold/ değişmez.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from deney.bolunme import OcrGerekli, TestKumesiKilitli
from guven_ornekleri import (
    TARANMIS, anlasmazlik, belge_ornegi, bolunme_dosyasi, dok, gold_yaz, klasor_snapshot, metinsel, rapor, sart, sayisal,
    uc_mod_yaz,
)

KOK = Path(__file__).resolve().parents[1]


def gv():
    from deney import guven_verisi

    return guven_verisi


def Girdi(**kw):
    from malzeme_kabul.kural.guven_skoru import GuvenGirdileri

    return GuvenGirdileri(**kw)


# Ortak küçük belge: viskozite (sayfa 1), kurşun (sayfa 2), koku (sayfa 2).
def viskozite(id="viscosity", ust=40, madde="3.6.3", sayfa=1, ad="Viscosity", **kw):
    return sart(id, ad, sayisal(ust=ust, birim="s", **kw), madde, sayfa)


def kursun(id="lead_content", ust=1, sayfa=2, madde="3.6.9"):
    return sart(id, "Lead content", sayisal(ust=ust, birim="ppm"), madde, sayfa)


def koku(id="odor", sayfa=2, madde="3.6.10"):
    return sart(id, "Odor", metinsel(), madde, sayfa)


def cikar(kural, dil, hibrit=None, r=None):
    return gv().girdileri_cikar(kural, dil, hibrit if hibrit is not None else kural, r if r is not None else rapor())


# --- girdileri_cikar -------------------------------------------------------------------


def test_girdiler_hibritin_butun_test_kimlikleri_icin_uretilir():
    kural = dok([viskozite(), kursun()])
    dil = dok([viskozite(), kursun(), koku()])
    hibrit = dok([viskozite(), kursun(), koku()])
    sonuc = cikar(kural, dil, hibrit, rapor(eklenen=["odor"]))
    assert set(sonuc) == {"viscosity", "lead_content", "odor"}


def test_kanitli_ve_anlasmazliksiz_eslesmede_butun_girdiler_sifirdir():
    kural = dok([viskozite()])
    sonuc = cikar(kural, dok([viskozite()]))
    assert sonuc["viscosity"] == Girdi()


def test_anlasmazlik_sayisi_teste_ait_kayitlari_sayar():
    kural = dok([viskozite(), kursun()])
    dil = dok([viskozite(ust=60), kursun()])
    r = rapor(anlasmazliklar=[anlasmazlik("viscosity", "ust"), anlasmazlik("viscosity", "birim"),
                              anlasmazlik("baska_test", "ust")])
    sonuc = cikar(kural, dil, r=r)
    assert sonuc["viscosity"].anlasmazlik_sayisi == 2
    assert sonuc["lead_content"].anlasmazlik_sayisi == 0


def test_eklenen_listesindeki_test_yalniz_modeldir():
    kural = dok([viskozite()])
    dil = dok([viskozite(), koku()])
    hibrit = dok([viskozite(), koku()])
    sonuc = cikar(kural, dil, hibrit, rapor(eklenen=["odor"]))
    assert sonuc["odor"].yalniz_model is True
    assert sonuc["viscosity"].yalniz_model is False


def test_yalniz_model_testte_kanit_yok_yanlistir():
    kural = dok([viskozite()])
    dil = dok([viskozite(), koku()])
    hibrit = dok([viskozite(), koku()])
    assert cikar(kural, dil, hibrit, rapor(eklenen=["odor"]))["odor"].kanit_yok is False


def test_dil_modelinde_karsiligi_olmayan_kural_testinde_kanit_yoktur():
    kural = dok([viskozite(), kursun()])
    dil = dok([viskozite()])
    sonuc = cikar(kural, dil)
    assert sonuc["lead_content"].kanit_yok is True
    assert sonuc["viscosity"].kanit_yok is False


def test_eslesen_dil_modeli_testi_kanitsizsa_kanit_yoktur():
    kural = dok([viskozite(), kursun()])
    dil = dok([viskozite(), kursun()])
    sonuc = cikar(kural, dil, r=rapor(kanitsiz=["lead_content"]))
    assert sonuc["lead_content"].kanit_yok is True
    assert sonuc["viscosity"].kanit_yok is False


def test_eslesen_dil_modeli_testinin_maddesi_farkliysa_kanit_yoktur():
    kural = dok([kursun(madde="3.6.9")])
    dil = dok([kursun(madde="3.6.19")])
    assert cikar(kural, dil)["lead_content"].kanit_yok is True


def test_madde_karsilastirmasi_bosluk_ve_harf_buyuklugunu_gozetmez():
    """Maddeler "TABLE I" ve "table  i" gibi yalnız boşluk ve harf büyüklüğüyle ayrışıyorsa aynı sayılır."""
    kural = dok([kursun(madde="TABLE I")])
    t = kursun(madde="TABLE I")
    t = t.model_copy(update={"kaynak": t.kaynak.model_copy(update={"madde": "table  i"})})  # doğrulamasız
    dil = dok([t])
    assert dil.testler[0].kaynak.madde == "table  i"
    assert cikar(kural, dil)["lead_content"].kanit_yok is False


def test_ad_benzerligiyle_eslesen_kanitli_dil_modeli_testi_kaniti_saglar():
    kural = dok([viskozite()])
    dil = dok([viskozite(id="viscosity_ford_cup")])
    assert cikar(kural, dil)["viscosity"].kanit_yok is False


def test_sayfa_kanitsiz_sayisi_ayni_sayfadaki_kanitsiz_dil_modeli_testlerini_sayar():
    kural = dok([viskozite(sayfa=1), kursun(sayfa=2)])
    dil = dok([viskozite(sayfa=1), kursun(sayfa=2), koku(sayfa=2),
               sart("gloss", "Gloss", sayisal(alt=80, birim="percent"), "3.6.15", 2),
               sart("color", "Color", metinsel("Color shall match."), "3.6.16", 3)])
    r = rapor(kanitsiz=["odor", "gloss", "color"])
    sonuc = cikar(kural, dil, r=r)
    assert sonuc["lead_content"].sayfa_kanitsiz_sayisi == 2
    assert sonuc["viscosity"].sayfa_kanitsiz_sayisi == 0


def test_kaynak_sayfasi_olmayan_testte_sayfa_kanitsiz_sayisi_sifirdir():
    kural = dok([kursun(sayfa=None)])
    dil = dok([kursun(sayfa=None), koku(sayfa=None)])
    sonuc = cikar(kural, dil, r=rapor(kanitsiz=["odor"]))
    assert sonuc["lead_content"].sayfa_kanitsiz_sayisi == 0


def test_yon_anlasmazligi_yon_celiskisidir():
    kural = dok([viskozite(), kursun()])
    dil = dok([viskozite(), kursun()])
    sonuc = cikar(kural, dil, r=rapor(anlasmazliklar=[anlasmazlik("viscosity", "yon")]))
    assert sonuc["viscosity"].yon_celiskisi is True
    assert sonuc["lead_content"].yon_celiskisi is False


def test_yon_disindaki_anlasmazlik_yon_celiskisi_degildir():
    kural = dok([viskozite()])
    sonuc = cikar(kural, dok([viskozite()]), r=rapor(anlasmazliklar=[anlasmazlik("viscosity", "ust")]))
    assert sonuc["viscosity"].yon_celiskisi is False


def test_eslesen_dil_modeli_kimligi_yon_celiskilerindeyse_yon_celiskisidir():
    """Eşleşme ad benzerliğiyle; çelişki dil modelinin kimliğiyle kayıtlı."""
    kural = dok([viskozite(), kursun()])
    dil = dok([viskozite(id="viscosity_ford_cup"), kursun()])
    sonuc = cikar(kural, dil, r=rapor(yon_celiskileri=["viscosity_ford_cup"]))
    assert sonuc["viscosity"].yon_celiskisi is True
    assert sonuc["lead_content"].yon_celiskisi is False


def test_yalniz_model_testte_dm_eki_atilmis_kimlik_yon_celiskilerindeyse_yon_celiskisidir():
    kural = dok([koku(id="odor")])
    dil = dok([koku(id="odor", madde="3.6.11")])
    hibrit = dok([koku(id="odor"), koku(id="odor_dm", madde="3.6.11")])
    sonuc = cikar(kural, dil, hibrit, rapor(eklenen=["odor_dm"], yon_celiskileri=["odor"]))
    assert sonuc["odor_dm"].yon_celiskisi is True
    assert sonuc["odor_dm"].yalniz_model is True


def test_yalniz_model_testte_ilgisiz_yon_celiskisi_sayilmaz():
    kural = dok([viskozite()])
    dil = dok([viskozite(), koku()])
    hibrit = dok([viskozite(), koku()])
    sonuc = cikar(kural, dil, hibrit, rapor(eklenen=["odor"], yon_celiskileri=["viscosity_x"]))
    assert sonuc["odor"].yon_celiskisi is False


def test_sayfa_sema_hatasi_testin_sayfasindaki_hata_sayisidir():
    kural = dok([viskozite(sayfa=1), kursun(sayfa=2)])
    sonuc = cikar(kural, dok([viskozite(sayfa=1), kursun(sayfa=2)]), r=rapor(sayfalar={1: 0, 2: 3}))
    assert sonuc["lead_content"].sayfa_sema_hatasi == 3
    assert sonuc["viscosity"].sayfa_sema_hatasi == 0


def test_raporda_sayfasi_olmayan_testte_sayfa_sema_hatasi_sifirdir():
    kural = dok([viskozite(sayfa=4)])
    sonuc = cikar(kural, dok([viskozite(sayfa=4)]), r=rapor(sayfalar={1: 5}))
    assert sonuc["viscosity"].sayfa_sema_hatasi == 0


# --- etiketle ------------------------------------------------------------------------


def test_gold_ile_ayni_hibrit_testi_hatali_degildir():
    hibrit = dok([viskozite(), kursun(), koku()])
    assert gv().etiketle(hibrit, dok([viskozite(), kursun(), koku()])) == {
        "viscosity": False, "lead_content": False, "odor": False,
    }


def test_goldda_karsiligi_olmayan_test_hatalidir():
    hibrit = dok([viskozite(), koku()])
    assert gv().etiketle(hibrit, dok([viskozite()])) == {"viscosity": False, "odor": True}


def test_ust_siniri_farkli_test_hatalidir():
    assert gv().etiketle(dok([viskozite(ust=40)]), dok([viskozite(ust=41)])) == {"viscosity": True}


def test_alt_siniri_farkli_test_hatalidir():
    hibrit = dok([sart("flash", "Flash point", sayisal(alt=20, birim="°C"), "3.6.14", 3)])
    gold = dok([sart("flash", "Flash point", sayisal(alt=21, birim="°C"), "3.6.14", 3)])
    assert gv().etiketle(hibrit, gold) == {"flash": True}


def test_kucuk_kayan_nokta_farki_hata_sayilmaz():
    assert gv().etiketle(dok([viskozite(ust=0.1 + 0.2)]), dok([viskozite(ust=0.3)])) == {"viscosity": False}


def test_kriter_turu_farkli_test_hatalidir():
    hibrit = dok([sart("odor", "Odor", sayisal(ust=1, birim="ppm"), "3.6.10", 2)])
    assert gv().etiketle(hibrit, dok([koku()])) == {"odor": True}


def test_birim_farkli_test_hatalidir():
    hibrit = dok([sart("sure", "Drying time", sayisal(ust=40, birim="s"), "3.6.12", 1)])
    gold = dok([sart("sure", "Drying time", sayisal(ust=40, birim="min"), "3.6.12", 1)])
    assert gv().etiketle(hibrit, gold) == {"sure": True}


@pytest.mark.parametrize("a,b", [("s", "second"), ("°C", "degC"), ("ppm", "ppm")])
def test_ayni_birimin_farkli_yazimi_hata_sayilmaz(a, b):
    hibrit = dok([sart("t", "Test", sayisal(ust=40, birim=a), "3.6.12", 1)])
    gold = dok([sart("t", "Test", sayisal(ust=40, birim=b), "3.6.12", 1)])
    assert gv().etiketle(hibrit, gold) == {"t": False}


def test_yalniz_alt_varken_alt_dahil_farki_hatadir():
    hibrit = dok([sart("t", "Test", sayisal(alt=5, birim="s", alt_dahil=True), "3.6.12", 1)])
    gold = dok([sart("t", "Test", sayisal(alt=5, birim="s", alt_dahil=False), "3.6.12", 1)])
    assert gv().etiketle(hibrit, gold) == {"t": True}


def test_yalniz_ust_varken_alt_dahil_farki_hata_sayilmaz():
    hibrit = dok([sart("t", "Test", sayisal(ust=5, birim="s", alt_dahil=True), "3.6.12", 1)])
    gold = dok([sart("t", "Test", sayisal(ust=5, birim="s", alt_dahil=False), "3.6.12", 1)])
    assert gv().etiketle(hibrit, gold) == {"t": False}


def test_yalniz_ust_varken_ust_dahil_farki_hatadir():
    hibrit = dok([sart("t", "Test", sayisal(ust=5, birim="s", ust_dahil=True), "3.6.12", 1)])
    gold = dok([sart("t", "Test", sayisal(ust=5, birim="s", ust_dahil=False), "3.6.12", 1)])
    assert gv().etiketle(hibrit, gold) == {"t": True}


def test_yalniz_alt_varken_ust_dahil_farki_hata_sayilmaz():
    hibrit = dok([sart("t", "Test", sayisal(alt=5, birim="s", ust_dahil=True), "3.6.12", 1)])
    gold = dok([sart("t", "Test", sayisal(alt=5, birim="s", ust_dahil=False), "3.6.12", 1)])
    assert gv().etiketle(hibrit, gold) == {"t": False}


def test_sinir_disindaki_alan_farki_hata_sayilmaz():
    hibrit = dok([sart("t", "Test", sayisal(ust=5, birim="s"), "3.6.12", 1, metot="ASTM D1200")])
    gold = dok([sart("t", "Test", sayisal(ust=5, birim="s"), "3.6.12", 1, metot="ASTM D 4212")])
    assert gv().etiketle(hibrit, gold) == {"t": False}


def test_yon_belirsiz_isareti_tek_basina_hata_sayilmaz():
    """Anlaşmazlıkta hibrit yönü "belirsiz" yapar; sınır sayıları aynıysa okuma doğrudur."""
    assert gv().etiketle(dok([viskozite(yon="belirsiz")]), dok([viskozite()])) == {"viscosity": False}


def test_ad_benzerligiyle_hizalanan_test_hibritin_ozgun_kimligiyle_doner():
    hibrit = dok([viskozite(id="viscosity_ford_cup")])
    gold = dok([viskozite(id="viscosity")])
    assert gv().etiketle(hibrit, gold) == {"viscosity_ford_cup": False}


def test_ad_benzerligiyle_hizalanan_testte_sinir_farki_hatadir():
    hibrit = dok([viskozite(id="viscosity_ford_cup", ust=60)])
    gold = dok([viskozite(id="viscosity", ust=40)])
    assert gv().etiketle(hibrit, gold) == {"viscosity_ford_cup": True}


# --- zorunlu_inceleme ----------------------------------------------------------------


def test_yonu_belirsiz_sayisal_sinir_zorunlu_incelemededir():
    assert gv().zorunlu_inceleme(viskozite(yon="belirsiz")) is True


def test_yonu_belli_sayisal_sinir_zorunlu_incelemede_degildir():
    assert gv().zorunlu_inceleme(viskozite()) is False
    assert gv().zorunlu_inceleme(viskozite(yon="en_cok")) is False


def test_sayisal_olmayan_sinir_zorunlu_incelemede_degildir():
    assert gv().zorunlu_inceleme(koku()) is False


# --- GuvenOrnegi ---------------------------------------------------------------------


def test_guven_ornegi_alanlari_plandaki_sirayladir():
    adlar = tuple(f.name for f in dataclasses.fields(gv().GuvenOrnegi))
    assert adlar == ("belge", "test_id", "girdiler", "hatali", "zorunlu_inceleme")


# --- klasorden_oku -------------------------------------------------------------------


@pytest.fixture
def ortam(tmp_path):
    """tmp_path altında: bölünme, üç mod klasörü ve kök (gold_taslak)."""
    bolunme, test_etiketi = bolunme_dosyasi(tmp_path)
    klasor = tmp_path / "uc_mod"
    kok = tmp_path / "kok"
    return {"bolunme": bolunme, "test_etiketi": test_etiketi, "klasor": klasor, "kok": kok}


def _belge_yaz(ortam, etiket="MIL-PRF-23377K", gold_klasoru="gold_taslak", hatali_ust=True):
    belge_no, rev = etiket[:-1], etiket[-1]
    kural, dil, hibrit, r, gold = belge_ornegi(belge_no, rev, hatali_ust=hatali_ust)
    uc_mod_yaz(ortam["klasor"], etiket, kural, dil, hibrit, r)
    if gold_klasoru:
        gold_yaz(ortam["kok"], gold_klasoru, etiket, gold)
    return gold


def _oku(ortam):
    return gv().klasorden_oku(ortam["klasor"], bolunme=ortam["bolunme"], kok=ortam["kok"])


def test_klasorden_oku_her_hibrit_testi_icin_ornek_uretir(ortam):
    _belge_yaz(ortam)
    ornekler, atlanan = _oku(ortam)
    assert atlanan == []
    assert {(o.belge, o.test_id) for o in ornekler} == {
        ("MIL-PRF-23377K", "viscosity"), ("MIL-PRF-23377K", "lead_content"), ("MIL-PRF-23377K", "flash_point"),
    }


def test_klasorden_oku_etiketleri_gold_ile_uretir(ortam):
    _belge_yaz(ortam)
    ornekler, _ = _oku(ortam)
    hatali = {o.test_id: o.hatali for o in ornekler}
    assert hatali == {"viscosity": True, "lead_content": False, "flash_point": True}


def test_klasorden_oku_girdileri_rapordan_uretir(ortam):
    _belge_yaz(ortam)
    ornekler, _ = _oku(ortam)
    g = {o.test_id: o.girdiler for o in ornekler}
    assert g["viscosity"].anlasmazlik_sayisi == 1
    assert g["flash_point"].yalniz_model is True
    assert g["flash_point"].sayfa_sema_hatasi == 1
    assert g["lead_content"] == Girdi()


def test_klasorden_oku_zorunlu_incelemeyi_hibrit_sinirindan_isaretler(ortam):
    _belge_yaz(ortam)
    ornekler, _ = _oku(ortam)
    assert {o.test_id: o.zorunlu_inceleme for o in ornekler} == {
        "viscosity": True, "lead_content": False, "flash_point": False,
    }


def test_klasorden_oku_birden_cok_belgeyi_okur(ortam):
    _belge_yaz(ortam, "MIL-PRF-23377K")
    _belge_yaz(ortam, "MIL-PRF-81733D")
    ornekler, _ = _oku(ortam)
    assert {o.belge for o in ornekler} == {"MIL-PRF-23377K", "MIL-PRF-81733D"}
    assert len(ornekler) == 6


def test_gold_yoksa_belge_atlanir_ve_listelenir(ortam):
    _belge_yaz(ortam, "MIL-PRF-23377K")
    _belge_yaz(ortam, "MIL-PRF-81733D", gold_klasoru=None)
    ornekler, atlanan = _oku(ortam)
    assert atlanan == ["MIL-PRF-81733D"]
    assert {o.belge for o in ornekler} == {"MIL-PRF-23377K"}


def test_gold_taslak_yoksa_gold_codex_okunur(ortam):
    _belge_yaz(ortam, gold_klasoru="gold_codex")
    ornekler, atlanan = _oku(ortam)
    assert atlanan == []
    assert len(ornekler) == 3


def test_gold_taslak_gold_codexten_once_gelir(ortam):
    _belge_yaz(ortam, gold_klasoru="gold_codex", hatali_ust=True)  # codex: viskozite hatalı
    _belge_yaz(ortam, gold_klasoru="gold_taslak", hatali_ust=False)  # taslak: viskozite doğru
    ornekler, _ = _oku(ortam)
    assert {o.test_id: o.hatali for o in ornekler}["viscosity"] is False


def test_data_gold_varsa_once_o_okunur_ve_degismez(ortam):
    """kok tmp_path altındadır; gerçek depodaki data/gold'a dokunulmaz."""
    _belge_yaz(ortam, gold_klasoru="gold_taslak", hatali_ust=True)  # taslak: viskozite hatalı
    _belge_yaz(ortam, gold_klasoru="gold", hatali_ust=False)  # (tmp) gold: viskozite doğru
    gold_klasoru = ortam["kok"] / "data" / "gold"
    once = klasor_snapshot(gold_klasoru)
    ornekler, _ = _oku(ortam)
    assert {o.test_id: o.hatali for o in ornekler}["viscosity"] is False
    assert klasor_snapshot(gold_klasoru) == once


def test_klasorden_oku_gercek_depodaki_data_goldu_degistirmez(ortam):
    gercek_gold = KOK / "data" / "gold"
    once = klasor_snapshot(gercek_gold)
    _belge_yaz(ortam)
    _oku(ortam)
    assert klasor_snapshot(gercek_gold) == once


def test_test_kumesindeki_belge_kilitlidir(ortam):
    _belge_yaz(ortam, "MIL-PRF-23377K")
    _belge_yaz(ortam, ortam["test_etiketi"])
    with pytest.raises(TestKumesiKilitli):
        _oku(ortam)


def test_bos_klasorde_ornek_ve_atlanan_yoktur(ortam):
    ortam["klasor"].mkdir()
    assert _oku(ortam) == ([], [])


def test_taranmis_belge_ocr_gelene_kadar_reddedilir(ortam):
    """Bölünmede ocr_gerekli sayılan belge, gold'u olsa bile okunmaz: OcrGerekli."""
    _belge_yaz(ortam, "MIL-PRF-23377K")
    _belge_yaz(ortam, TARANMIS)
    with pytest.raises(OcrGerekli):
        _oku(ortam)


def test_yalniz_taranmis_belge_varken_de_reddedilir(ortam):
    _belge_yaz(ortam, TARANMIS)
    with pytest.raises(OcrGerekli):
        _oku(ortam)
