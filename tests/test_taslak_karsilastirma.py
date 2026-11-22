"""İki bağımsız doğru cevap taslağını karşılaştırmanın testleri."""

from __future__ import annotations

import csv
import math

import pytest

from conftest import betik_yukle

from malzeme_kabul.sema import (
    KabulDokumani, Kaynak, Kosul, NumuneHazirlama, RafOmru, Sinir, StandartBilgisi,
)
from malzeme_kabul.sema import TestSarti as Sart
from malzeme_kabul.taslak_karsilastirma import kaydi_eslestir, karsilastir


def kaynak(madde):
    return Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde=madde)


def sart(id, ad=None, ust=30.0, madde="3.5.1", metot="ASTM D 1200", numune=None):
    return Sart(
        id=id,
        test_adi=ad or id.replace("_", " ").title(),
        test_metodu=metot,
        sinir=Sinir(kriter_turu="sayisal", ust=ust, birim="s", orijinal_metin="not more than 30 s"),
        kaynak=kaynak(madde),
        test_turleri={"kabul"},
        numune_hazirlama_id=numune,
    )


def dok(testler=(), raf=(), kosullar=(), numune=()):
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        testler=list(testler),
        raf_omurleri=list(raf),
        kosullar=list(kosullar),
        numune_hazirlama=list(numune),
    )


# --- Satır sınıflandırma ----------------------------------------------------------


def test_ayni_taslaklar_tam_uyusur():
    a = dok([sart("viscosity"), sart("pot_life", madde="3.6.4")])
    k = karsilastir(a, a)
    assert k.ayrisan == [] and k.yalniz_a == [] and k.yalniz_b == []
    assert k.uyusma_orani == 1.0
    assert len(k.uyusan) == len(k.satirlar) > 0


def test_farkli_deger_ayrisan_satirdir():
    k = karsilastir(dok([sart("viscosity", ust=30)]), dok([sart("viscosity", ust=40)]))
    assert [(s.alan, s.a, s.b) for s in k.ayrisan] == [("test.sinir.ust", 30.0, 40.0)]


def test_yalniz_bir_tarafta_olan_alan_ve_kayit():
    a = dok([sart("viscosity"), sart("odor", madde="3.6.2")])
    b = dok([sart("viscosity", metot=None)])
    k = karsilastir(a, b)
    assert ("test.test_metodu", "viscosity") in {(s.alan, s.kayit_a) for s in k.yalniz_a}
    assert {s.kayit_a for s in k.yalniz_a} == {"viscosity", "odor"}
    assert k.yalniz_b == []
    assert all(s.b is None for s in k.yalniz_a)


def test_uyusma_orani_uyusan_bolu_toplam_satir():
    k = karsilastir(dok([sart("viscosity", ust=30)]), dok([sart("viscosity", ust=40), sart("odor", madde="3.6.2")]))
    assert k.uyusma_orani == pytest.approx(len(k.uyusan) / len(k.satirlar))
    assert 0 < k.uyusma_orani < 1


def test_alan_dokumu_her_alan_icin_sayar():
    k = karsilastir(dok([sart("viscosity", ust=30)]), dok([sart("viscosity", ust=40)]))
    dokum = {d["alan"]: d for d in k.alan_dokumu()}
    assert dokum["test.sinir.ust"]["ayrisan"] == 1
    assert dokum["test.test_adi"]["uyusan"] == 1


def test_bos_taslaklarda_oran_sifirdir():
    k = karsilastir(dok(), dok())
    assert k.satirlar == [] and k.uyusma_orani == 0.0


# --- Kayıt eşleştirme -------------------------------------------------------------


def test_farkli_id_ayni_madde_benzer_ad_benzerlikle_eslesir():
    a = dok([sart("viscosity", ad="Viscosity")])
    b = dok([sart("viscosity_of_admixed", ad="Viscosity of admixed primer")])
    k = karsilastir(a, b)
    assert k.yalniz_a == [] and k.yalniz_b == []
    [e] = [e for e in k.eslesmeler if e.tur == "test"]
    assert (e.a, e.b, e.yontem) == ("viscosity", "viscosity_of_admixed", "benzerlik")
    # Benzerlikle eşleşen kaydın satırları işaretli; test_adi ayrışıyor.
    assert all(s.eslesme == "benzerlik" for s in k.satirlar)
    assert [s.alan for s in k.ayrisan] == ["test.test_adi"]


def test_anahtarla_eslesenler_benzerlik_diye_isaretlenmez():
    k = karsilastir(dok([sart("viscosity")]), dok([sart("viscosity")]))
    assert {e.yontem for e in k.eslesmeler} == {"anahtar"}
    assert {s.eslesme for s in k.satirlar} == {"anahtar"}


def test_farkli_maddedeki_kayitlar_eslesmez():
    k = karsilastir(dok([sart("viscosity", madde="3.6.3")]), dok([sart("viscosity_x", ad="Viscosity", madde="3.6.4")]))
    assert {s.kayit_a for s in k.yalniz_a} == {"viscosity"}
    assert {s.kayit_b for s in k.yalniz_b} == {"viscosity_x"}


def test_ayni_maddede_en_benzer_ad_secilir():
    a = dok([sart("drying_time", ad="Drying time"), sart("dry_hard", ad="Drying time, dry hard", madde="3.5.1")])
    b = dok([sart("set_to_touch", ad="Drying time set to touch"), sart("hard_dry", ad="Drying time dry hard")])
    eslesmeler = kaydi_eslestir(a, b)
    ciftler = {(e.a, e.b) for e in eslesmeler if e.tur == "test"}
    assert ("dry_hard", "hard_dry") in ciftler
    assert ("drying_time", "set_to_touch") in ciftler


def test_benzemeyen_adlar_ayni_maddede_bile_eslesmez():
    a = dok([sart("lead", ad="Lead content"), sart("cadmium", ad="Cadmium content")])
    b = dok([sart("lead_x", ad="Lead content"), sart("toxicity", ad="Toxicity")])
    k = karsilastir(a, b)
    assert {s.kayit_a for s in k.yalniz_a} == {"cadmium"}
    assert {s.kayit_b for s in k.yalniz_b} == {"toxicity"}


def test_kosul_raf_omru_ve_numune_eslesir_ve_numune_baglantisi_cevrilir():
    a = dok(
        [sart("adhesion", numune="panel_A")],
        raf=[RafOmru(kap_turu="metal", sure=1, birim="year", kaynak=kaynak("3.5.3"))],
        kosullar=[Kosul(kategori="kullanim", ad="Kap ömrü", aciklama="4 saat", kaynak=kaynak("3.6.4"))],
        numune=[NumuneHazirlama(id="panel_A", kupon_malzemesi="2024-T3", kaynak=kaynak("4.4.2"))],
    )
    b = dok(
        [sart("adhesion", numune="panel_a_aluminyum")],
        raf=[RafOmru(kap_turu="Metal", sure=1, birim="year", kaynak=kaynak("3.5.3"))],
        kosullar=[Kosul(kategori="kullanim", ad="Kap ömrü süresi", aciklama="4 saat", kaynak=kaynak("3.6.4"))],
        numune=[NumuneHazirlama(id="panel_a_aluminyum", kupon_malzemesi="2024-T3", kaynak=kaynak("4.4.2"))],
    )
    k = karsilastir(a, b)
    assert k.ayrisan == [] and k.yalniz_a == [] and k.yalniz_b == []
    yontem = {e.tur: e.yontem for e in k.eslesmeler}
    assert yontem == {"test": "anahtar", "raf_omru": "anahtar", "kosul": "benzerlik", "numune": "benzerlik"}


# --- Kontrol örneği ---------------------------------------------------------------


def _cok_testli(n):
    return dok([sart(f"t{i}", ad=f"Test {i}", madde=f"3.{i + 1}") for i in range(n)])


def test_kontrol_ornegi_uyusanlarin_yuzde_yirmisi_yukari_yuvarlanir():
    d = _cok_testli(7)
    k = karsilastir(d, d)
    ornek = k.kontrol_ornegi()
    # Kayan nokta hatası (0.2 * 70 = 14.000000000000002) bir satır fazla seçtirmesin.
    assert len(ornek) == math.ceil(round(len(k.uyusan) * 0.2, 9))
    assert all(s.durum == "uyusan" for s in ornek)
    assert len({(s.alan, s.kayit_a) for s in ornek}) == len(ornek)


def test_kontrol_ornegi_ayni_seed_ile_tekrarlanir_farkli_seed_ile_degisir():
    d = _cok_testli(10)
    k1, k2 = karsilastir(d, d), karsilastir(d, d)
    anahtar = lambda ornek: [(s.alan, s.kayit_a) for s in ornek]
    assert anahtar(k1.kontrol_ornegi(seed=7)) == anahtar(k2.kontrol_ornegi(seed=7))
    assert anahtar(k1.kontrol_ornegi(seed=7)) != anahtar(k1.kontrol_ornegi(seed=8))


def test_kontrol_ornegi_girdi_sirasindan_bagimsizdir():
    d = _cok_testli(10)
    ters = dok(list(reversed(d.testler)))
    anahtar = lambda k: [(s.alan, s.kayit_a) for s in k.kontrol_ornegi(seed=3)]
    assert anahtar(karsilastir(d, d)) == anahtar(karsilastir(ters, ters))


def test_kontrol_ornegi_orani_ayarlanabilir_ve_sinirlidir():
    d = _cok_testli(5)
    k = karsilastir(d, d)
    assert len(k.kontrol_ornegi(oran=1.0)) == len(k.uyusan)
    assert k.kontrol_ornegi(oran=0.0) == []
    with pytest.raises(ValueError):
        k.kontrol_ornegi(oran=1.5)


# --- Betik ------------------------------------------------------------------------


@pytest.fixture
def taslaklar(tmp_path):
    a = dok([sart("viscosity", ust=30), sart("odor", ad="Odor", madde="3.6.2")] + [
        sart(f"t{i}", ad=f"Test {i}", madde=f"3.{i + 10}") for i in range(6)
    ])
    b = dok([sart("viscosity_b", ad="Viscosity", ust=40)] + [
        sart(f"t{i}", ad=f"Test {i}", madde=f"3.{i + 10}") for i in range(6)
    ])
    ya, yb = tmp_path / "a.json", tmp_path / "b.json"
    ya.write_text(a.model_dump_json(), encoding="utf-8")
    yb.write_text(b.model_dump_json(), encoding="utf-8")
    return ya, yb


def test_betik_rapor_ve_csv_yazar(taslaklar, tmp_path, capsys):
    betik = betik_yukle("scripts/taslak_karsilastir.py")
    md, cs = tmp_path / "out" / "rapor.md", tmp_path / "out" / "rapor.csv"
    assert betik.main([str(taslaklar[0]), str(taslaklar[1]), "--md", str(md), "--csv", str(cs), "--seed", "5"]) == 0
    assert "Uyuşma oranı" in capsys.readouterr().out
    metin = md.read_text(encoding="utf-8")
    for baslik in ("Uyuşma oranı", "Ayrışan satırlar", "Yalnız A", "Yalnız B", "Kontrol örneği", "Ad benzerliğiyle eşleşen kayıtlar"):
        assert baslik in metin
    assert "viscosity_b" in metin and "- [ ]" in metin
    with open(cs, encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    durumlar = {s["durum"] for s in satirlar}
    assert {"uyusan", "ayrisan", "yalniz_a"} <= durumlar
    assert any(s["kontrol_ornegi"] == "evet" for s in satirlar)
    assert {s["eslesme"] for s in satirlar if s["kayit_b"] == "viscosity_b"} == {"benzerlik"}


def test_betik_ayni_seed_ile_ayni_raporu_uretir(taslaklar, tmp_path):
    betik = betik_yukle("scripts/taslak_karsilastir.py")
    r1, r2 = tmp_path / "r1.md", tmp_path / "r2.md"
    betik.main([str(taslaklar[0]), str(taslaklar[1]), "--md", str(r1)])
    betik.main([str(taslaklar[0]), str(taslaklar[1]), "--md", str(r2)])
    assert r1.read_text(encoding="utf-8") == r2.read_text(encoding="utf-8")


def test_betik_gecersiz_girdide_2_doner(taslaklar, tmp_path):
    betik = betik_yukle("scripts/taslak_karsilastir.py")
    bozuk = tmp_path / "bozuk.json"
    bozuk.write_text('{"standart": {}}', encoding="utf-8")
    assert betik.main([str(taslaklar[0]), str(bozuk)]) == 2


def test_betik_data_gold_altina_yazmayi_reddeder(taslaklar, tmp_path):
    betik = betik_yukle("scripts/taslak_karsilastir.py")
    hedef = tmp_path / "data" / "gold" / "rapor.md"
    assert betik.main([str(taslaklar[0]), str(taslaklar[1]), "--md", str(hedef)]) == 2
    assert not hedef.exists()


# --- Kaynak tablo adı -------------------------------------------------------------


def _tablolu(id, ad, tablo):
    return sart(id, ad=ad, madde="3.4").model_copy(update={"kaynak_tablo_adi": tablo})


def test_kaynak_tablo_adi_alan_olarak_karsilastirilir():
    a = dok([_tablolu("cadmium", "Cadmium content", "Lead and cadmium content")])
    b = dok([_tablolu("cadmium", "Cadmium content", None)])
    k = karsilastir(a, b)
    assert [(s.alan, s.a) for s in k.yalniz_a] == [("test.kaynak_tablo_adi", "Lead and cadmium content")]


def test_tablo_satir_adini_test_adi_yapan_taslak_tablo_adiyla_eslesir():
    # A test adını ayırmış, B tablo satır adını test adı olarak bırakmış.
    a = dok([_tablolu("cd", "Cd ppm", "Lead and cadmium content")])
    b = dok([sart("lead_and_cadmium_content", ad="Lead and cadmium content", madde="3.4")])
    k = karsilastir(a, b)
    [e] = k.eslesmeler
    assert (e.a, e.b, e.yontem) == ("cd", "lead_and_cadmium_content", "benzerlik")
    assert {s.alan for s in k.ayrisan} == {"test.test_adi"}
    assert {s.alan for s in k.yalniz_a} == {"test.kaynak_tablo_adi"}
