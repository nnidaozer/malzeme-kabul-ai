"""Çıkarıcı çıktısını gold ile karşılaştıran değerlendirmenin testleri."""

from __future__ import annotations

import json

import pytest

from conftest import betik_yukle

from malzeme_kabul.degerlendirme import alanlari_duzlestir, degerlendir
from malzeme_kabul.sema import KabulDokumani, Kaynak, Kosul, RafOmru, Sinir, StandartBilgisi
from malzeme_kabul.sema import TestSarti as Sart


def kaynak(madde):
    return Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde=madde)


def sart(id, alt=20.0, ust=30.0, birim="s", metot="ASTM D 1200", madde="3.5.1", ad=None):
    return Sart(
        id=id,
        test_adi=ad or id.title(),
        test_metodu=metot,
        sinir=Sinir(kriter_turu="sayisal", alt=alt, ust=ust, birim=birim, orijinal_metin="20 to 30 s"),
        kaynak=kaynak(madde),
        test_turleri={"kabul"},
    )


def dok(testler, raf=(), kosullar=()):
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        testler=testler,
        raf_omurleri=list(raf),
        kosullar=list(kosullar),
    )


# --- Düzleştirme -----------------------------------------------------------------


def test_test_alanlari_test_kimligiyle_anahtarlanir():
    alanlar = alanlari_duzlestir(dok([sart("viskozite")]))
    assert alanlar[("test.sinir.alt", "viskozite")] == 20.0
    assert alanlar[("test.kaynak.madde", "viskozite")] == "3.5.1"
    assert alanlar[("test.test_turleri", "viskozite")] == ("kabul",)


def test_bos_alanlar_duzlestirilmez():
    d = dok([sart("viskozite", metot=None)])
    assert ("test.test_metodu", "viskozite") not in alanlari_duzlestir(d)


def test_raf_omru_ve_kosullar_duzlestirilir():
    d = dok(
        [],
        raf=[RafOmru(sure=12, birim="month", kaynak=kaynak("3.7"))],
        kosullar=[Kosul(kategori="kullanim", ad="Pot life", aciklama="4 hours", kaynak=kaynak("3.5.2"))],
    )
    alanlar = alanlari_duzlestir(d)
    assert alanlar[("raf_omru.sure", "genel")] == 12
    assert alanlar[("kosul.aciklama", "kullanim:pot life")] == "4 hours"


# --- Ölçütler --------------------------------------------------------------------


def test_birebir_ayni_cikti_tam_puan_alir():
    gold = dok([sart("viskozite"), sart("kap_omru")])
    sonuc = degerlendir(gold, gold)
    assert sonuc.genel.precision == sonuc.genel.recall == sonuc.genel.f1 == 1.0


def test_yanlis_deger_hem_fp_hem_fn_sayilir():
    gold = dok([sart("viskozite", alt=20)])
    tahmin = dok([sart("viskozite", alt=25)])
    alan = degerlendir(tahmin, gold).alanlar["test.sinir.alt"]
    assert (alan.dp, alan.yp, alan.yn) == (0, 1, 1)
    assert alan.f1 == 0.0


def test_eksik_test_yalniz_recalli_dusurur():
    gold = dok([sart("viskozite"), sart("kap_omru")])
    tahmin = dok([sart("viskozite")])
    alan = degerlendir(tahmin, gold).alanlar["test.sinir.alt"]
    assert alan.precision == 1.0
    assert alan.recall == 0.5
    assert alan.f1 == pytest.approx(2 / 3)


def test_fazladan_test_yalniz_precisioni_dusurur():
    gold = dok([sart("viskozite")])
    tahmin = dok([sart("viskozite"), sart("uydurma")])
    alan = degerlendir(tahmin, gold).alanlar["test.test_adi"]
    assert alan.precision == 0.5
    assert alan.recall == 1.0


def test_metin_karsilastirmasi_buyuk_kucuk_harf_ve_bosluga_duyarsiz():
    gold = dok([sart("viskozite", metot="ASTM D 1200")])
    tahmin = dok([sart("viskozite", metot="astm  d 1200")])
    assert degerlendir(tahmin, gold).alanlar["test.test_metodu"].f1 == 1.0


def test_ayni_birimin_farkli_yazimi_dogru_sayilir():
    # "s" ile "second" pint'te aynı birimdir.
    gold = dok([sart("viskozite", birim="s")])
    tahmin = dok([sart("viskozite", birim="second")])
    assert degerlendir(tahmin, gold).alanlar["test.sinir.birim"].f1 == 1.0


def test_farkli_birim_yanlis_sayilir_ve_cevrilmez():
    # 20-30 s ile 20-30 min farklıdır; değerlendirme değeri çevirip eşitlemeye çalışmaz.
    gold = dok([sart("viskozite", birim="s")])
    tahmin = dok([sart("viskozite", birim="minute")])
    sonuc = degerlendir(tahmin, gold)
    assert sonuc.alanlar["test.sinir.birim"].f1 == 0.0
    assert sonuc.alanlar["test.sinir.alt"].f1 == 1.0


def test_kaynak_belge_no_ve_revizyon_ayri_alan_olarak_olculur():
    gold = dok([sart("viskozite")])
    alanlar = degerlendir(gold, gold).alanlar
    assert "test.kaynak.belge_no" in alanlar and "test.kaynak.revizyon" in alanlar


def test_kriter_turu_olculur_orijinal_metin_olculmez():
    gold = dok([sart("viskozite")])
    alanlar = degerlendir(gold, gold).alanlar
    assert "test.sinir.kriter_turu" in alanlar
    assert "test.sinir.orijinal_metin" not in alanlar


def test_sayisal_degerde_kayan_nokta_farki_dogru_sayilir():
    gold = dok([sart("viskozite", alt=0.3)])
    tahmin = dok([sart("viskozite", alt=0.1 + 0.2)])
    assert degerlendir(tahmin, gold).alanlar["test.sinir.alt"].f1 == 1.0


def test_hic_ornek_olmayan_alanda_olcutler_tanimsiz_degil_sifir():
    gold = dok([sart("viskozite")])
    sonuc = degerlendir(dok([]), gold)
    alan = sonuc.alanlar["test.sinir.alt"]
    assert alan.precision == 0.0 and alan.recall == 0.0 and alan.f1 == 0.0


def test_genel_skor_mikro_ortalama():
    gold = dok([sart("viskozite"), sart("kap_omru")])
    tahmin = dok([sart("viskozite")])
    g = degerlendir(tahmin, gold).genel
    assert g.dp == sum(a.dp for a in degerlendir(tahmin, gold).alanlar.values())
    assert g.precision == 1.0
    assert g.recall == 0.5


def test_tablo_satirlari_alan_adiyla_siralanir():
    gold = dok([sart("viskozite")])
    satirlar = degerlendir(gold, gold).tablo()
    adlar = [s["alan"] for s in satirlar]
    assert adlar[-1] == "GENEL (mikro)"
    assert adlar[:-1] == sorted(adlar[:-1])


# --- scripts/degerlendir.py ------------------------------------------------------


def test_betik_json_dosyalarini_karsilastirir_ve_csv_yazar(tmp_path, capsys):
    betik = betik_yukle("scripts/degerlendir.py")
    gold = dok([sart("viskozite"), sart("kap_omru")])
    tahmin = dok([sart("viskozite")])
    (tmp_path / "g.json").write_text(gold.model_dump_json(), encoding="utf-8")
    (tmp_path / "t.json").write_text(tahmin.model_dump_json(), encoding="utf-8")
    csv_yolu = tmp_path / "sonuc.csv"

    kod = betik.main([str(tmp_path / "t.json"), str(tmp_path / "g.json"), "--csv", str(csv_yolu)])

    assert kod == 0
    cikti = capsys.readouterr().out
    assert "test.sinir.alt" in cikti and "GENEL" in cikti
    assert csv_yolu.read_text(encoding="utf-8").startswith("alan,dp,yp,yn,precision,recall,f1")


def test_betik_gecersiz_json_icin_hata_kodu_doner(tmp_path, capsys):
    betik = betik_yukle("scripts/degerlendir.py")
    (tmp_path / "g.json").write_text(json.dumps({"standart": {}}), encoding="utf-8")
    (tmp_path / "t.json").write_text("{}", encoding="utf-8")
    assert betik.main([str(tmp_path / "t.json"), str(tmp_path / "g.json")]) == 2
    assert "geçersiz" in capsys.readouterr().err


def test_dahil_bilgisi_sinir_yoksa_olculmez():
    gold = dok([Sart(id="a", test_adi="A", sinir=Sinir(kriter_turu="metinsel", orijinal_metin="x"),
                     kaynak=kaynak("3.1"), test_turleri={"kabul"})])
    alanlar = alanlari_duzlestir(gold)
    assert ("test.sinir.alt_dahil", "a") not in alanlar
    assert ("test.sinir.ust_dahil", "a") not in alanlar


def test_numune_baglantisi_olculur():
    from malzeme_kabul.sema import NumuneHazirlama

    s = sart("viskozite").model_copy(update={"numune_hazirlama_id": "panel_A"})
    d = KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        testler=[s],
        numune_hazirlama=[NumuneHazirlama(id="panel_A", kaynak=kaynak("TABLE I"))],
    )
    assert alanlari_duzlestir(d)[("test.numune_hazirlama_id", "viskozite")] == "panel_A"


def test_raf_omru_kayitlari_kap_turuyle_eslesir():
    gold = dok([], raf=[RafOmru(kap_turu="metal", sure=1, birim="year", kaynak=kaynak("3.5.3")),
                        RafOmru(kap_turu="plastik", sure=6, birim="month", kaynak=kaynak("3.5.3"))])
    tahmin = dok([], raf=[RafOmru(kap_turu="Metal", sure=1, birim="year", kaynak=kaynak("3.5.3"))])
    alan = degerlendir(tahmin, gold).alanlar["raf_omru.sure"]
    assert (alan.dp, alan.yp, alan.yn) == (1, 0, 1)
