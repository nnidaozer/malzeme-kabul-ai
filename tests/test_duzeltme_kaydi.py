"""Plan adım 2 ve 4: düzeltme olay deposu (malzeme_kabul.kayit.duzeltme_kaydi) ve etiket adayı.

Bütün dosya yazımları tmp_path altındadır; data/gold/ kullanılmaz.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sqlite3
from pathlib import Path

import pytest

from malzeme_kabul.katalog.veritabani import Katalog, KatalogHatasi
from malzeme_kabul.kayit import duzeltme_kaydi as dk
from malzeme_kabul.kayit.duzeltme_kaydi import (
    ISLEMLER,
    DuzeltmeKaydi,
    Olay,
    alan_farklari,
    etiket_adayi_yaz,
)
from malzeme_kabul.sozlesme.alanlar import alanlari_duzlestir
from malzeme_kabul.sozlesme.sema import KabulDokumani, StandartBilgisi
from tests.duzeltme_ornekleri import (
    alan_anahtarlari,
    alan_sayisi,
    dok,
    raf,
    sart,
    taban,
    viskozite_ust,
)

UST = ("test.sinir.ust", "viskozite")


def farklar_sozluk(farklar):
    return {(f.alan, f.kayit): f for f in farklar}


@pytest.fixture
def baglanti():
    b = sqlite3.connect(":memory:")
    yield b
    b.close()


@pytest.fixture
def kaydi(baglanti):
    return DuzeltmeKaydi(baglanti)


# --- sabitler ve veri yapıları -------------------------------------------------------------


def test_islemler_dort_islemdir():
    assert ISLEMLER == ("degistir", "ekle", "sil", "onayla")


def test_olay_alanlari_tasarim_notundaki_alanlardir():
    assert [a.name for a in dataclasses.fields(Olay)] == [
        "olay_id", "zaman", "muhendis", "taslak_id", "belge", "dokuman_surumu", "kayit_turu", "kayit",
        "alan", "eski_deger", "yeni_deger", "islem", "kaynak", "gerekce", "ureten",
    ]


# --- şema ve değiştirilemezlik --------------------------------------------------------------


def test_sema_iki_tabloyu_kurar(baglanti, kaydi):
    tablolar = {s[0] for s in baglanti.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"duzeltme_tabanlari", "duzeltme_olaylari"} <= tablolar


def test_sema_iki_kez_kurulabilir(baglanti, kaydi):
    DuzeltmeKaydi(baglanti)  # IF NOT EXISTS: hata yok


@pytest.mark.parametrize("sql", [
    "UPDATE duzeltme_olaylari SET muhendis = 'baska'",
    "DELETE FROM duzeltme_olaylari",
])
def test_olay_tablosu_guncellenemez_ve_silinemez(kaydi, baglanti, sql):
    kaydi.duzeltmeleri_kaydet(1, taban(), viskozite_ust(35.0), "mp1")
    with pytest.raises(sqlite3.DatabaseError):
        baglanti.execute(sql)


@pytest.mark.parametrize("sql", [
    "UPDATE duzeltme_tabanlari SET icerik = '{}'",
    "DELETE FROM duzeltme_tabanlari",
])
def test_taban_tablosu_guncellenemez_ve_silinemez(kaydi, baglanti, sql):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    with pytest.raises(sqlite3.DatabaseError):
        baglanti.execute(sql)


# --- alan_farklari ----------------------------------------------------------------------------


def test_ayni_dokuman_icin_fark_yoktur():
    assert alan_farklari(taban(), taban()) == []


def test_degisen_sinir_degistir_farki_verir():
    f = farklar_sozluk(alan_farklari(taban(), viskozite_ust(35.0)))
    assert list(f) == [UST]
    fark = f[UST]
    assert (fark.kayit_turu, fark.kayit, fark.alan) == ("test", "viskozite", "test.sinir.ust")
    assert (fark.eski_deger, fark.yeni_deger, fark.islem) == (30.0, 35.0, "degistir")


def test_fark_alan_adlari_duzeltme_alanlari_anahtarlaridir():
    eski, yeni = taban(), dok([sart("viskozite", ust=35.0, madde="3.6.3", sayfa=6)])
    anahtarlar = alan_anahtarlari(eski) | alan_anahtarlari(yeni)
    assert {(f.alan, f.kayit) for f in alan_farklari(eski, yeni)} <= anahtarlar


def test_tolerans_icindeki_sayi_farki_fark_degildir():
    assert alan_farklari(taban(), viskozite_ust(30.0 + 1e-12)) == []


def test_tam_sinirin_hemen_ustu_fark_sayilir():
    assert [f.islem for f in alan_farklari(taban(), viskozite_ust(30.001))] == ["degistir"]


def test_tam_sinirin_hemen_alti_fark_sayilir():
    assert [f.islem for f in alan_farklari(taban(), viskozite_ust(29.999))] == ["degistir"]


def test_ayni_birimin_farkli_yazimi_fark_degildir():
    assert alan_farklari(dok([sart("viskozite", birim="s")]), dok([sart("viskozite", birim="second")])) == []


def test_farkli_birim_fark_sayilir():
    f = farklar_sozluk(alan_farklari(dok([sart("viskozite", birim="s")]), dok([sart("viskozite", birim="min")])))
    assert list(f) == [("test.sinir.birim", "viskozite")]
    assert (f[("test.sinir.birim", "viskozite")].eski_deger, f[("test.sinir.birim", "viskozite")].yeni_deger) == ("s", "min")


def test_ayni_sayi_farkli_birimle_hem_sayi_hem_birim_degil_yalniz_birim_farkidir():
    # 30 s ile 30 min: sayı aynı, birim farklı -> yalnız birim alanı değişmiştir (dönüşüm yapılmaz)
    eski, yeni = dok([sart("viskozite", ust=30.0, birim="s")]), dok([sart("viskozite", ust=30.0, birim="min")])
    assert [(f.alan, f.islem) for f in alan_farklari(eski, yeni)] == [("test.sinir.birim", "degistir")]


def test_yenide_olan_eskide_olmayan_alan_ekle_farkidir():
    farklar = alan_farklari(dok([sart("viskozite")]), dok([sart("viskozite"), sart("kap_omru")]))
    assert farklar and all(f.islem == "ekle" and f.kayit == "kap_omru" and f.eski_deger is None for f in farklar)


def test_eskide_olan_yenide_olmayan_alan_sil_farkidir():
    farklar = alan_farklari(dok([sart("viskozite"), sart("kap_omru")]), dok([sart("viskozite")]))
    assert farklar and all(f.islem == "sil" and f.kayit == "kap_omru" and f.yeni_deger is None for f in farklar)


def test_silinen_test_metodu_sil_farkidir():
    f = farklar_sozluk(alan_farklari(dok([sart("viskozite")]), dok([sart("viskozite", metot=None)])))
    assert f[("test.test_metodu", "viskozite")].islem == "sil"


def test_kayit_turu_alan_adinin_ilk_parcasidir():
    farklar = alan_farklari(dok([], raf=[raf(sure=12)]), dok([], raf=[raf(sure=24)]))
    assert [(f.kayit_turu, f.kayit, f.alan) for f in farklar] == [("raf_omru", "genel", "raf_omru.sure")]


def test_fark_degerleri_json_a_yazilabilir():
    farklar = alan_farklari(dok([sart("viskozite")]), dok([sart("viskozite"), sart("kap_omru")]))
    turler = farklar_sozluk(farklar)[("test.test_turleri", "kap_omru")]
    assert turler.yeni_deger == ["kabul"]
    json.dumps([[f.eski_deger, f.yeni_deger] for f in farklar])


# --- taban ---------------------------------------------------------------------------------------


def test_taban_kaydedilir_ve_geri_okunur(kaydi):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    assert alanlari_duzlestir(kaydi.taban(1)) == alanlari_duzlestir(taban())
    assert kaydi.ureten(1)["yaklasim"] == "kural"


def test_tabani_olmayan_taslak_icin_none_doner(kaydi):
    assert kaydi.taban(99) is None and kaydi.ureten(99) is None


def test_ayni_taslak_icin_ikinci_taban_reddedilir(kaydi):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        kaydi.taban_kaydet(1, viskozite_ust(35.0), {"yaklasim": "dil_modeli"})
    assert kaydi.taban(1).testler[0].sinir.ust == 30.0


# --- duzeltmeleri_kaydet ---------------------------------------------------------------------------


def test_duzeltme_alan_farkini_olay_olarak_yazar(kaydi):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    olaylar = kaydi.duzeltmeleri_kaydet(1, taban(), viskozite_ust(35.0), "mp1", gerekce="tabloda 35 s")
    assert len(olaylar) == 1
    o = olaylar[0]
    assert (o.taslak_id, o.belge, o.kayit_turu, o.kayit, o.alan) == (1, "MIL-PRF-23377K", "test", "viskozite", "test.sinir.ust")
    assert (o.eski_deger, o.yeni_deger, o.islem) == (30.0, 35.0, "degistir")
    assert (o.muhendis, o.gerekce) == ("mp1", "tabloda 35 s")


def test_olay_kaynagi_kaydin_maddesini_icerir(kaydi):
    olaylar = kaydi.duzeltmeleri_kaydet(1, taban(), viskozite_ust(35.0, kap_omru_ust=80.0), "mp1")
    kaynak = {o.kayit: o.kaynak for o in olaylar}
    assert "3.6.2" in kaynak["viskozite"] and "3.6.4" in kaynak["kap_omru"]


def test_olay_ureteni_tabanin_ureteni_olur(kaydi):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    (o,) = kaydi.duzeltmeleri_kaydet(1, taban(), viskozite_ust(35.0), "mp1")
    assert o.ureten == {"yaklasim": "kural"}


def test_farksiz_kaydetme_olay_yazmaz(kaydi):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    assert kaydi.duzeltmeleri_kaydet(1, taban(), taban(), "mp1") == []
    assert kaydi.olaylar(1) == []


def test_tabani_olmayan_taslakta_eski_dokuman_taban_olur_ve_ureten_bilinmiyor(kaydi):
    kaydi.duzeltmeleri_kaydet(7, taban(), viskozite_ust(35.0), "mp1")
    assert alanlari_duzlestir(kaydi.taban(7)) == alanlari_duzlestir(taban())
    assert kaydi.ureten(7) == {"yaklasim": "bilinmiyor"}


def test_ikinci_duzeltme_tabani_degistirmez(kaydi):
    kaydi.duzeltmeleri_kaydet(7, taban(), viskozite_ust(35.0), "mp1")
    kaydi.duzeltmeleri_kaydet(7, viskozite_ust(35.0), viskozite_ust(36.0), "mp1")
    assert kaydi.taban(7).testler[0].sinir.ust == 30.0


@pytest.mark.parametrize("muhendis", ["", "   "])
def test_muhendis_bos_olamaz(kaydi, muhendis):
    with pytest.raises(ValueError):
        kaydi.duzeltmeleri_kaydet(1, taban(), viskozite_ust(35.0), muhendis)
    assert kaydi.olaylar() == []


def test_olaylar_ekleme_sirasiyla_ve_taslaga_gore_doner(kaydi):
    a = kaydi.duzeltmeleri_kaydet(1, taban(), viskozite_ust(35.0), "mp1")
    b = kaydi.duzeltmeleri_kaydet(2, taban(), viskozite_ust(30.0, kap_omru_ust=80.0), "mp2")
    c = kaydi.duzeltmeleri_kaydet(1, viskozite_ust(35.0), viskozite_ust(36.0), "mp1")
    assert kaydi.olaylar() == a + b + c
    assert kaydi.olaylar(1) == a + c and kaydi.olaylar(2) == b


def test_olay_kimlikleri_benzersizdir(kaydi):
    kaydi.duzeltmeleri_kaydet(1, taban(), viskozite_ust(35.0, kap_omru_ust=80.0), "mp1")
    kimlikler = [o.olay_id for o in kaydi.olaylar()]
    assert len(set(kimlikler)) == len(kimlikler) == 2


# --- onaylari_kaydet -----------------------------------------------------------------------------------


def test_onay_degismemis_her_alan_icin_onayla_olayi_yazar(kaydi):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    son = viskozite_ust(35.0)
    kaydi.duzeltmeleri_kaydet(1, taban(), son, "mp1")
    onaylar = kaydi.onaylari_kaydet(1, son, "mp1")
    beklenen = alan_anahtarlari(taban()) - {UST}
    assert {(o.alan, o.kayit) for o in onaylar} == beklenen
    assert all(o.islem == "onayla" and o.eski_deger == o.yeni_deger for o in onaylar)


def test_net_degisen_alan_onayla_almaz(kaydi):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    kaydi.duzeltmeleri_kaydet(1, taban(), viskozite_ust(35.0), "mp1")
    onaylar = kaydi.onaylari_kaydet(1, viskozite_ust(35.0), "mp1")
    assert UST not in {(o.alan, o.kayit) for o in onaylar}


def test_degistirilip_geri_alinan_alan_onayla_alir(kaydi):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    kaydi.duzeltmeleri_kaydet(1, taban(), viskozite_ust(35.0), "mp1")
    kaydi.duzeltmeleri_kaydet(1, viskozite_ust(35.0), taban(), "mp1")
    onaylar = {(o.alan, o.kayit): o for o in kaydi.onaylari_kaydet(1, taban(), "mp1")}
    assert UST in onaylar
    assert onaylar[UST].eski_deger == onaylar[UST].yeni_deger == 30.0


def test_hic_degismeyen_taslakta_butun_alanlar_onaylanir(kaydi):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    onaylar = kaydi.onaylari_kaydet(1, taban(), "mp1")
    assert len(onaylar) == alan_sayisi(taban())


def test_onay_olaylari_olaylar_listesinde_gorunur(kaydi):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    onaylar = kaydi.onaylari_kaydet(1, taban(), "mp1")
    assert kaydi.olaylar(1) == onaylar


# --- etiket adayı (adım 4) ---------------------------------------------------------------------------


def onayli_taslak(katalog: Katalog, son: KabulDokumani = None) -> int:
    """Katalogda taban → düzeltme → onay akışını alttaki API ile kurar."""
    son = son or viskozite_ust(35.0)
    kaydi = DuzeltmeKaydi(katalog.baglanti)
    t = katalog.taslak_kaydet(taban(), "mp1")
    kaydi.taban_kaydet(t.id, taban(), {"yaklasim": "kural"})
    kaydi.duzeltmeleri_kaydet(t.id, taban(), son, "mp1")
    katalog.taslak_guncelle(t.id, son)
    katalog.taslagi_onayla(t.id, "mp1")
    kaydi.onaylari_kaydet(t.id, son, "mp1")
    return t.id


@pytest.fixture
def katalog():
    k = Katalog()
    yield k
    k.kapat()


def test_etiket_adayi_son_dokumani_ve_olaylari_yazar(katalog, tmp_path):
    tid = onayli_taslak(katalog)
    klasor = tmp_path / "etiket_adaylari"
    yollar = etiket_adayi_yaz(katalog, tid, klasor)
    assert sorted(p.name for p in yollar) == [f"MIL-PRF-23377K_taslak{tid}.json", f"MIL-PRF-23377K_taslak{tid}.olaylar.jsonl"]
    assert all(p.parent == klasor and p.is_file() for p in yollar)


def test_etiket_adayi_json_son_dokumana_esittir(katalog, tmp_path):
    tid = onayli_taslak(katalog)
    etiket_adayi_yaz(katalog, tid, tmp_path)
    okunan = KabulDokumani.model_validate_json((tmp_path / f"MIL-PRF-23377K_taslak{tid}.json").read_text(encoding="utf-8"))
    assert okunan.model_dump(exclude={"durum"}) == viskozite_ust(35.0).model_dump(exclude={"durum"})


def test_etiket_adayi_olaylar_dosyasi_her_satirda_bir_olaydir(katalog, tmp_path):
    tid = onayli_taslak(katalog)
    etiket_adayi_yaz(katalog, tid, tmp_path)
    satirlar = (tmp_path / f"MIL-PRF-23377K_taslak{tid}.olaylar.jsonl").read_text(encoding="utf-8").splitlines()
    olaylar = [json.loads(s) for s in satirlar]
    assert len(olaylar) == len(DuzeltmeKaydi(katalog.baglanti).olaylar(tid))
    assert {o["islem"] for o in olaylar} == {"degistir", "onayla"}
    assert all(o["taslak_id"] == tid for o in olaylar)


def test_onaylanmamis_taslak_etiket_adayi_olamaz(katalog, tmp_path):
    t = katalog.taslak_kaydet(taban(), "mp1")
    with pytest.raises((KatalogHatasi, ValueError)):
        etiket_adayi_yaz(katalog, t.id, tmp_path / "aday")
    assert not (tmp_path / "aday").exists()


@pytest.mark.parametrize("goreli", ["data/gold", "data/gold/alt", "gold"])
def test_gold_klasorune_etiket_adayi_yazilmaz(katalog, tmp_path, goreli):
    tid = onayli_taslak(katalog)
    klasor = tmp_path / goreli
    with pytest.raises(ValueError):
        etiket_adayi_yaz(katalog, tid, klasor)
    assert not klasor.exists() or not any(klasor.iterdir())


def test_gold_a_isaret_eden_baglanti_uzerinden_yazilmaz(katalog, tmp_path):
    tid = onayli_taslak(katalog)
    gold = tmp_path / "data" / "gold"
    gold.mkdir(parents=True)
    kisayol = tmp_path / "adaylar"
    kisayol.symlink_to(gold, target_is_directory=True)
    with pytest.raises(ValueError):
        etiket_adayi_yaz(katalog, tid, kisayol)
    assert not any(gold.iterdir())


def test_adi_gold_iceren_ama_gold_olmayan_klasore_yazilir(katalog, tmp_path):
    tid = onayli_taslak(katalog)
    assert len(etiket_adayi_yaz(katalog, tid, tmp_path / "goldsmith")) == 2


# --- gözden geçirme: gold koruması (public gold_yolu_mu, yol kaçışı, dosya bağlantısı) -----------------


@pytest.mark.parametrize("parcalar", [
    ("data", "GOLD"),
    ("data", "Gold"),
    ("data", "gold."),
    ("data", "gold "),
    ("data", "gold.."),
    ("data", "Gold", "alt"),
    ("gold",),
])
def test_gold_yolu_mu_buyuk_kucuk_harf_ve_sondaki_nokta_bosluga_duyarsizdir(tmp_path, parcalar):
    assert dk.gold_yolu_mu(tmp_path.joinpath(*parcalar)) is True


@pytest.mark.parametrize("parcalar", [
    ("data", "goldsmith"),
    ("data", "altin_gold_degil"),
    ("data", "calisma", "etiket_adaylari"),
])
def test_gold_yolu_mu_adinda_gold_gecen_baska_klasoru_gold_saymaz(tmp_path, parcalar):
    assert dk.gold_yolu_mu(tmp_path.joinpath(*parcalar)) is False


def test_gold_yolu_mu_gold_a_isaret_eden_klasor_baglantisini_gold_sayar(tmp_path):
    gold = tmp_path / "data" / "gold"
    gold.mkdir(parents=True)
    kisayol = tmp_path / "adaylar"
    kisayol.symlink_to(gold, target_is_directory=True)
    assert dk.gold_yolu_mu(kisayol) is True


@pytest.mark.parametrize("ad", ["GOLD", "Gold", "gold.", "gold "])
def test_buyuk_harfli_ya_da_noktali_gold_klasorune_etiket_adayi_yazilmaz(katalog, tmp_path, ad):
    tid = onayli_taslak(katalog)
    klasor = tmp_path / "data" / ad
    with pytest.raises(ValueError):
        etiket_adayi_yaz(katalog, tid, klasor)
    assert not klasor.exists() or not any(klasor.iterdir())


def _kotu_belge_nolu_onayli_taslak(katalog: Katalog, belge_no: str) -> int:
    kotu = taban().model_copy(update={"standart": StandartBilgisi(belge_no=belge_no, revizyon="K")})
    t = katalog.taslak_kaydet(kotu, "mp1")
    DuzeltmeKaydi(katalog.baglanti).taban_kaydet(t.id, katalog.taslak(t.id).dokuman, {"yaklasim": "kural"})
    katalog.taslagi_onayla(t.id, "mp1")
    return t.id


@pytest.mark.parametrize("gold_onceden_var", [False, True])
@pytest.mark.parametrize("belge_no", ["../../gold/MIL-PRF-23377", "..\\..\\gold\\MIL-PRF-23377", "/gold/MIL-PRF-23377"])
def test_belge_numarasindaki_yol_kacisi_klasor_disina_ve_gold_a_dosya_cikarmaz(katalog, tmp_path, belge_no,
                                                                                 gold_onceden_var):
    if belge_no.startswith("/") and Path("/gold").exists():
        pytest.skip("kök dizinde /gold var; mutlak yol örneği tmp dışına yazabilir")
    tid = _kotu_belge_nolu_onayli_taslak(katalog, belge_no)
    klasor = tmp_path / "k1" / "k2" / "adaylar"
    gold = tmp_path / "k1" / "gold"  # klasor/../../gold
    if gold_onceden_var:
        gold.mkdir(parents=True)
    try:
        yollar = etiket_adayi_yaz(katalog, tid, klasor)
    except ValueError:
        yollar = []
    hedef = klasor.resolve()
    for yol in yollar:
        assert Path(yol).resolve().parent == hedef, yol
    disaridakiler = [p for p in tmp_path.rglob("*") if p.is_file() and not p.resolve().is_relative_to(hedef)]
    assert disaridakiler == []
    if gold_onceden_var:
        assert not any(gold.iterdir())
    else:
        assert [p for p in tmp_path.rglob("*") if p.name.casefold().startswith("gold")] == []


def test_belge_numarasindaki_izinsiz_karakterler_dosya_adinda_alt_cizgi_olur(katalog, tmp_path):
    tid = _kotu_belge_nolu_onayli_taslak(katalog, "../../gold/MIL-PRF-23377")
    klasor = tmp_path / "adaylar"
    yollar = etiket_adayi_yaz(katalog, tid, klasor)
    assert all(p.parent == klasor for p in yollar)
    assert all(re.fullmatch(r"[A-Za-z0-9._-]+", p.name) for p in yollar), [p.name for p in yollar]


@pytest.mark.parametrize("uzanti", [".json", ".olaylar.jsonl"])
def test_gold_dosyasina_isaret_eden_dosya_baglantisi_uzerinden_gold_degismez(katalog, tmp_path, uzanti):
    tid = onayli_taslak(katalog)
    gold = tmp_path / "data" / "gold"
    gold.mkdir(parents=True)
    hedef = gold / "x.json"
    hedef.write_text("ORIJINAL", encoding="utf-8")
    klasor = tmp_path / "adaylar"
    klasor.mkdir()
    baglanti = klasor / f"MIL-PRF-23377K_taslak{tid}{uzanti}"
    baglanti.symlink_to(hedef)
    try:
        etiket_adayi_yaz(katalog, tid, klasor)
    except ValueError:
        pass
    else:
        assert not baglanti.is_symlink() and baglanti.is_file()
    assert hedef.read_text(encoding="utf-8") == "ORIJINAL"
    assert sorted(p.name for p in gold.iterdir()) == ["x.json"]


# --- gözden geçirme: tablodan düzenlenen ek alanlar ---------------------------------------------------------


def test_ek_alanlar_demeti_tablodan_duzenlenen_ama_f1_de_olmayan_alanlardir():
    assert isinstance(dk.EK_ALANLAR, tuple)
    assert set(dk.EK_ALANLAR) == {"test.kaynak.sayfa", "test.sinir.orijinal_metin", "test.sonuc_kaynagi"}
    assert "EK_ALANLAR" in dk.__all__


def test_ek_alanlar_f1_duzlestirmesinde_yoktur():
    alanlar = {alan for alan, _ in alanlari_duzlestir(taban())}
    assert not alanlar & set(dk.EK_ALANLAR)


def _sinir_metni(metin: str) -> KabulDokumani:
    t = sart("viskozite")
    return dok([t.model_copy(update={"sinir": t.sinir.model_copy(update={"orijinal_metin": metin})})])


def _sonuc_kaynagi(kaynak: str) -> KabulDokumani:
    return dok([sart("viskozite").model_copy(update={"sonuc_kaynagi": kaynak})])


@pytest.mark.parametrize("eski, yeni, alan, eski_deger, yeni_deger", [
    (dok([sart("viskozite", sayfa=5)]), dok([sart("viskozite", sayfa=6)]), "test.kaynak.sayfa", 5, 6),
    (_sinir_metni("20 to 30 s"), _sinir_metni("20 - 35 s"), "test.sinir.orijinal_metin", "20 to 30 s", "20 - 35 s"),
    (_sonuc_kaynagi("coc"), _sonuc_kaynagi("ic_laboratuvar"), "test.sonuc_kaynagi", "coc", "ic_laboratuvar"),
])
def test_ek_alan_degisimi_test_kaydinda_degistir_farkidir(eski, yeni, alan, eski_deger, yeni_deger):
    farklar = alan_farklari(eski, yeni)
    assert [(f.kayit_turu, f.kayit, f.alan, f.eski_deger, f.yeni_deger, f.islem) for f in farklar] == [
        ("test", "viskozite", alan, eski_deger, yeni_deger, "degistir")]


def test_sayfanin_silinmesi_sil_farkidir():
    farklar = alan_farklari(dok([sart("viskozite", sayfa=5)]), dok([sart("viskozite", sayfa=None)]))
    assert [(f.alan, f.islem, f.eski_deger, f.yeni_deger) for f in farklar] == [("test.kaynak.sayfa", "sil", 5, None)]


def test_sayfanin_eklenmesi_ekle_farkidir():
    farklar = alan_farklari(dok([sart("viskozite", sayfa=None)]), dok([sart("viskozite", sayfa=6)]))
    assert [(f.alan, f.islem, f.eski_deger, f.yeni_deger) for f in farklar] == [("test.kaynak.sayfa", "ekle", None, 6)]


def test_ayni_sayfa_fark_degildir():
    assert alan_farklari(dok([sart("viskozite", sayfa=5)]), dok([sart("viskozite", sayfa=5)])) == []


def test_yalniz_sayfa_degisince_duzeltme_olayi_yazilir(kaydi):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    yeni = dok([sart("viskozite", sayfa=6), sart("kap_omru", alt=None, ust=70.0, madde="3.6.4", sayfa=7)])
    olaylar = kaydi.duzeltmeleri_kaydet(1, taban(), yeni, "mp1")
    assert [(o.alan, o.kayit, o.islem, o.eski_deger, o.yeni_deger) for o in olaylar] == [
        ("test.kaynak.sayfa", "viskozite", "degistir", 5, 6)]


# --- gözden geçirme: INSERT OR REPLACE iki olay tablosunda da reddedilir -------------------------------------


@pytest.fixture
def dosyadaki_kayit(tmp_path):
    yol = tmp_path / "k.sqlite"
    b = sqlite3.connect(yol)
    k = DuzeltmeKaydi(b)
    k.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    k.duzeltmeleri_kaydet(1, taban(), viskozite_ust(35.0), "mp1")
    b.commit()
    b.close()
    return yol


def _tablo(yol, tablo):
    b = sqlite3.connect(yol)
    try:
        return b.execute(f"SELECT * FROM {tablo} ORDER BY 1").fetchall()
    finally:
        b.close()


def test_insert_or_replace_ile_duzeltme_tabani_uzerine_yazilamaz(dosyadaki_kayit):
    once = _tablo(dosyadaki_kayit, "duzeltme_tabanlari")
    b = sqlite3.connect(dosyadaki_kayit)
    with pytest.raises(sqlite3.DatabaseError):
        b.execute(
            "INSERT OR REPLACE INTO duzeltme_tabanlari (taslak_id, belge, icerik, ozet, ureten, zaman)"
            " VALUES (1, 'MIL-PRF-23377K', '{}', ?, '{\"yaklasim\": \"dil_modeli\"}', '2000-01-01')",
            ("a" * 64,),
        )
        b.commit()
    b.close()
    assert _tablo(dosyadaki_kayit, "duzeltme_tabanlari") == once


def test_insert_or_replace_ile_duzeltme_olayi_uzerine_yazilamaz(dosyadaki_kayit):
    once = _tablo(dosyadaki_kayit, "duzeltme_olaylari")
    (olay_id,) = once[0][:1]
    b = sqlite3.connect(dosyadaki_kayit)
    with pytest.raises(sqlite3.DatabaseError):
        b.execute(
            "INSERT OR REPLACE INTO duzeltme_olaylari (olay_id, zaman, muhendis, taslak_id, belge, dokuman_surumu,"
            " kayit_turu, kayit, alan, eski_deger, yeni_deger, islem, kaynak, gerekce, ureten)"
            " VALUES (?, '2000-01-01', 'sahte', 1, 'MIL-PRF-23377K', 'x', 'test', 'viskozite', 'test.sinir.ust',"
            " '30.0', '99.0', 'degistir', NULL, NULL, '{}')",
            (olay_id,),
        )
        b.commit()
    b.close()
    assert _tablo(dosyadaki_kayit, "duzeltme_olaylari") == once


# --- koordinatör kararı: ek alanlar paydaya girer (duzeltme_alanlari) ----------------------------------------


def test_duzeltme_alanlari_f1_alanlari_ve_dolu_ek_alanlardir():
    alanlar = dk.duzeltme_alanlari(taban())
    assert set(alanlar) == alan_anahtarlari(taban())
    assert "duzeltme_alanlari" in dk.__all__


def test_duzeltme_alanlari_f1_degerlerini_aynen_icerir():
    alanlar, f1 = dk.duzeltme_alanlari(taban()), alanlari_duzlestir(taban())
    assert all(alanlar[a] == f1[a] for a in f1)


def test_duzeltme_alanlari_ek_alan_degerlerini_icerir():
    alanlar = dk.duzeltme_alanlari(taban())
    assert alanlar[("test.kaynak.sayfa", "viskozite")] == 5
    assert alanlar[("test.kaynak.sayfa", "kap_omru")] == 7
    assert alanlar[("test.sinir.orijinal_metin", "viskozite")] == "20 to 30 s"
    assert alanlar[("test.sonuc_kaynagi", "viskozite")] == "coc"


def test_duzeltme_alanlari_bos_sayfayi_saymaz():
    alanlar = dk.duzeltme_alanlari(dok([sart("viskozite", sayfa=None)]))
    assert ("test.kaynak.sayfa", "viskozite") not in alanlar
    assert ("test.sonuc_kaynagi", "viskozite") in alanlar


def test_onay_degismemis_ek_alanlar_icin_de_onayla_olayi_yazar(kaydi):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    onaylar = {(o.alan, o.kayit) for o in kaydi.onaylari_kaydet(1, taban(), "mp1")}
    assert {(a, k) for a in dk.EK_ALANLAR for k in ("viskozite", "kap_omru")} <= onaylar


def test_sayfasi_duzeltilen_alan_onayla_almaz_digerleri_alir(kaydi):
    kaydi.taban_kaydet(1, taban(), {"yaklasim": "kural"})
    son = dok([sart("viskozite", sayfa=6), sart("kap_omru", alt=None, ust=70.0, madde="3.6.4", sayfa=7)])
    kaydi.duzeltmeleri_kaydet(1, taban(), son, "mp1")
    onaylar = {(o.alan, o.kayit) for o in kaydi.onaylari_kaydet(1, son, "mp1")}
    assert onaylar == alan_anahtarlari(taban()) - {("test.kaynak.sayfa", "viskozite")}


def test_bos_sayfa_icin_onayla_olayi_yazilmaz(kaydi):
    d = dok([sart("viskozite", sayfa=None)])
    kaydi.taban_kaydet(1, d, {"yaklasim": "kural"})
    onaylar = {(o.alan, o.kayit) for o in kaydi.onaylari_kaydet(1, d, "mp1")}
    assert ("test.kaynak.sayfa", "viskozite") not in onaylar
    assert onaylar == alan_anahtarlari(d)


def test_uzerine_yaz_kapaliyken_var_olan_aday_korunur_ve_hata_verilir(katalog, tmp_path):
    tid = onayli_taslak(katalog)
    json_yolu, olay_yolu = etiket_adayi_yaz(katalog, tid, tmp_path)
    json_yolu.write_text("elle düzeltilmiş", encoding="utf-8")
    with pytest.raises(FileExistsError):
        etiket_adayi_yaz(katalog, tid, tmp_path, uzerine_yaz=False)
    assert json_yolu.read_text(encoding="utf-8") == "elle düzeltilmiş"


def test_uzerine_yaz_acikken_var_olan_aday_yenilenir(katalog, tmp_path):
    tid = onayli_taslak(katalog)
    json_yolu, _ = etiket_adayi_yaz(katalog, tid, tmp_path)
    json_yolu.write_text("eski", encoding="utf-8")
    etiket_adayi_yaz(katalog, tid, tmp_path, uzerine_yaz=True)
    KabulDokumani.model_validate_json(json_yolu.read_text(encoding="utf-8"))
