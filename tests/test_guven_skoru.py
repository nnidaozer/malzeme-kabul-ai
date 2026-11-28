"""Güven skoru (ürün): girdiler, lojistik model, yönlendirme (docs/guven_skoru.md).

Skor kabul ya da red kararı vermez; yalnız "uygun" kararı insan incelemesine
gönderebilir. "uygun_degil" ve "insan_incelemeli" hiçbir skorla değişmez.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import math
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
MODUL_YOLU = KOK / "src" / "malzeme_kabul" / "kural" / "guven_skoru.py"

ADLAR = ("anlasmazlik_sayisi", "kanit_yok", "yalniz_model", "sayfa_kanitsiz_sayisi", "yon_celiskisi",
         "sayfa_sema_hatasi")
SAYI_ALANLARI = ("anlasmazlik_sayisi", "sayfa_kanitsiz_sayisi", "sayfa_sema_hatasi")
IKILI_ALANLAR = ("kanit_yok", "yalniz_model", "yon_celiskisi")


def gs():
    from malzeme_kabul.kural import guven_skoru

    return guven_skoru


def sifir_agirliklar(**degisen) -> dict[str, float]:
    a = {ad: 0.0 for ad in ADLAR}
    a.update(degisen)
    return a


def model(sabit=0.0, esik=0.5, bilgi=None, **agirliklar):
    kw = {"bilgi": bilgi} if bilgi is not None else {}
    return gs().GuvenModeli(agirliklar=sifir_agirliklar(**agirliklar), sabit=sabit, esik=esik, **kw)


# --- Özellik adları ve girdiler --------------------------------------------------------


def test_ozellik_adlari_plandaki_sirayla_tanimlidir():
    assert gs().OZELLIK_ADLARI == ADLAR


def test_guven_girdileri_alanlari_ozellik_adlari_sirasindadir():
    assert tuple(f.name for f in dataclasses.fields(gs().GuvenGirdileri)) == ADLAR


def test_guven_girdileri_varsayilanlari_sifir_ve_yanlistir():
    g = gs().GuvenGirdileri()
    assert (g.anlasmazlik_sayisi, g.sayfa_kanitsiz_sayisi, g.sayfa_sema_hatasi) == (0, 0, 0)
    assert (g.kanit_yok, g.yalniz_model, g.yon_celiskisi) == (False, False, False)


def test_guven_girdileri_degistirilemez():
    g = gs().GuvenGirdileri()
    with pytest.raises(dataclasses.FrozenInstanceError):
        g.anlasmazlik_sayisi = 3


@pytest.mark.parametrize("alan", SAYI_ALANLARI)
def test_negatif_sayi_alani_reddedilir(alan):
    with pytest.raises(ValueError):
        gs().GuvenGirdileri(**{alan: -1})


@pytest.mark.parametrize("alan", SAYI_ALANLARI)
def test_sayi_alaninda_sifir_kabul_edilir(alan):
    assert getattr(gs().GuvenGirdileri(**{alan: 0}), alan) == 0


@pytest.mark.parametrize("alan", SAYI_ALANLARI)
def test_sayi_alaninda_bool_reddedilir(alan):
    with pytest.raises(ValueError):
        gs().GuvenGirdileri(**{alan: True})


@pytest.mark.parametrize("alan", SAYI_ALANLARI)
@pytest.mark.parametrize("deger", [1.0, "1", None])
def test_sayi_alaninda_tamsayi_olmayan_reddedilir(alan, deger):
    with pytest.raises(ValueError):
        gs().GuvenGirdileri(**{alan: deger})


@pytest.mark.parametrize("alan", IKILI_ALANLAR)
@pytest.mark.parametrize("deger", [1, 0, "True", None])
def test_ikili_alanda_bool_olmayan_reddedilir(alan, deger):
    with pytest.raises(ValueError):
        gs().GuvenGirdileri(**{alan: deger})


def test_varsayilan_girdilerin_vektoru_sifirdir():
    assert gs().GuvenGirdileri().vektor() == (0.0,) * 6


def test_vektor_sayilari_log1p_ile_ikilileri_bir_sifir_ile_verir():
    g = gs().GuvenGirdileri(anlasmazlik_sayisi=3, kanit_yok=True, yalniz_model=False, sayfa_kanitsiz_sayisi=1,
                            yon_celiskisi=True, sayfa_sema_hatasi=7)
    v = g.vektor()
    assert isinstance(v, tuple) and all(type(x) is float for x in v)
    assert v == pytest.approx((math.log1p(3), 1.0, 0.0, math.log1p(1), 1.0, math.log1p(7)))


# --- Model doğrulaması ---------------------------------------------------------------


def test_guven_modeli_hatasi_value_error_turudur():
    assert issubclass(gs().GuvenModeliHatasi, ValueError)


def test_guven_modeli_bilgi_verilmezse_bos_sozluktur():
    m = gs().GuvenModeli(agirliklar=sifir_agirliklar(), sabit=0.0, esik=0.5)
    assert m.bilgi == {}


def test_guven_modeli_degistirilemez():
    m = model()
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.sabit = 1.0


def test_eksik_agirlik_anahtari_reddedilir():
    a = sifir_agirliklar()
    del a["yon_celiskisi"]
    with pytest.raises(gs().GuvenModeliHatasi):
        gs().GuvenModeli(agirliklar=a, sabit=0.0, esik=0.5)


def test_fazla_agirlik_anahtari_reddedilir():
    with pytest.raises(gs().GuvenModeliHatasi):
        gs().GuvenModeli(agirliklar=sifir_agirliklar(bilinmeyen=1.0), sabit=0.0, esik=0.5)


@pytest.mark.parametrize("deger", [math.nan, math.inf, -math.inf])
def test_sonlu_olmayan_agirlik_reddedilir(deger):
    with pytest.raises(gs().GuvenModeliHatasi):
        gs().GuvenModeli(agirliklar=sifir_agirliklar(kanit_yok=deger), sabit=0.0, esik=0.5)


@pytest.mark.parametrize("deger", [math.nan, math.inf, -math.inf])
def test_sonlu_olmayan_sabit_reddedilir(deger):
    with pytest.raises(gs().GuvenModeliHatasi):
        gs().GuvenModeli(agirliklar=sifir_agirliklar(), sabit=deger, esik=0.5)


@pytest.mark.parametrize("esik", [-1e-9, 1.0 + 1e-9, -0.5, 2.0, math.nan, math.inf])
def test_sifir_bir_disindaki_esik_reddedilir(esik):
    with pytest.raises(gs().GuvenModeliHatasi):
        gs().GuvenModeli(agirliklar=sifir_agirliklar(), sabit=0.0, esik=esik)


@pytest.mark.parametrize("esik", [0.0, 1.0, 0.5])
def test_sinirdaki_esikler_kabul_edilir(esik):
    assert gs().GuvenModeli(agirliklar=sifir_agirliklar(), sabit=0.0, esik=esik).esik == esik


# --- Skor ------------------------------------------------------------------------------


def test_sifir_agirlik_ve_sifir_sabitte_guven_yarimdir():
    m = model()
    assert m.guven(gs().GuvenGirdileri(anlasmazlik_sayisi=5, kanit_yok=True)) == pytest.approx(0.5)


def test_hata_olasiligi_dogrusal_toplamin_sigmoididir():
    # sabit 0, anlaşmazlık ağırlığı 1, bir anlaşmazlık: sigmoid(log 2) = 2/3
    m = model(anlasmazlik_sayisi=1.0)
    g = gs().GuvenGirdileri(anlasmazlik_sayisi=1)
    assert m.hata_olasiligi(g) == pytest.approx(2 / 3)


def test_guven_bir_eksi_hata_olasiligidir():
    m = model(sabit=-0.3, kanit_yok=1.2, sayfa_sema_hatasi=0.4)
    g = gs().GuvenGirdileri(kanit_yok=True, sayfa_sema_hatasi=2)
    assert m.guven(g) == pytest.approx(1 - m.hata_olasiligi(g))


def test_cok_buyuk_dogrusal_toplamda_tasma_olmadan_bire_yakin_hata_olasiligi():
    p = model(sabit=1000.0).hata_olasiligi(gs().GuvenGirdileri())
    assert 0.999 < p <= 1.0


def test_cok_kucuk_dogrusal_toplamda_tasma_olmadan_sifira_yakin_hata_olasiligi():
    p = model(sabit=-1000.0).hata_olasiligi(gs().GuvenGirdileri())
    assert 0.0 <= p < 1e-3


def test_guven_asiri_negatif_sabitte_bile_bire_ulasmaz():
    """Açık kalma yok: güven en çok nextafter(1.0, 0.0); 1.0 eşiği her testi incelemeye gönderir."""
    g = gs().GuvenGirdileri()
    guven = model(sabit=-1000.0).guven(g)
    assert guven < 1.0
    assert guven <= math.nextafter(1.0, 0.0)


@pytest.mark.parametrize("sabit", [-40.0, -1000.0, -1e300])
def test_guven_bir_esiginde_uygun_karari_insan_incelemesine_gider(sabit):
    m = model(sabit=sabit)
    g = gs().GuvenGirdileri()
    assert gs().yonlendir("uygun", m.guven(g), 1.0)[0] == "insan_incelemeli"


def test_negatif_agirlikla_cok_kucuk_toplamda_da_guven_bire_ulasmaz():
    m = model(yalniz_model=-1e6)
    assert m.guven(gs().GuvenGirdileri(yalniz_model=True)) < 1.0


def test_pozitif_agirlikli_ozellik_artinca_guven_azalir():
    m = model(anlasmazlik_sayisi=0.8)
    guvenler = [m.guven(gs().GuvenGirdileri(anlasmazlik_sayisi=n)) for n in (0, 1, 2, 5)]
    assert guvenler == sorted(guvenler, reverse=True)
    assert len(set(guvenler)) == 4


def test_negatif_agirlikli_ozellik_artinca_guven_artar():
    m = model(yalniz_model=-1.0)
    assert m.guven(gs().GuvenGirdileri(yalniz_model=True)) > m.guven(gs().GuvenGirdileri(yalniz_model=False))


# --- Sözlük ve dosya -------------------------------------------------------------------


def test_sozluk_surum_ozellikler_agirliklar_sabit_esik_ve_bilgi_icerir():
    m = model(sabit=0.25, esik=0.7, bilgi={"ornek_sayisi": 12}, kanit_yok=1.5)
    d = m.sozluk()
    assert d == {
        "surum": "guven-skoru-v1",
        "ozellikler": list(ADLAR),
        "agirliklar": sifir_agirliklar(kanit_yok=1.5),
        "sabit": 0.25,
        "esik": 0.7,
        "bilgi": {"ornek_sayisi": 12},
    }
    json.dumps(d)  # JSON'a yazılabilir


def test_sozlukten_sozlugun_tersidir():
    m = model(sabit=-0.5, esik=0.9, bilgi={"l2": 1.0}, anlasmazlik_sayisi=2.0, yon_celiskisi=0.5)
    assert gs().GuvenModeli.sozlukten(m.sozluk()) == m


def test_sozlukten_farkli_surumu_reddeder():
    d = model().sozluk()
    d["surum"] = "guven-skoru-v2"
    with pytest.raises(gs().GuvenModeliHatasi):
        gs().GuvenModeli.sozlukten(d)


def test_sozlukten_farkli_sirali_ozellik_listesini_reddeder():
    d = model().sozluk()
    d["ozellikler"] = list(reversed(ADLAR))
    with pytest.raises(gs().GuvenModeliHatasi):
        gs().GuvenModeli.sozlukten(d)


def test_sozlukten_eksik_ozellik_listesini_reddeder():
    d = model().sozluk()
    d["ozellikler"] = list(ADLAR[:-1])
    with pytest.raises(gs().GuvenModeliHatasi):
        gs().GuvenModeli.sozlukten(d)


def test_kaydet_ve_yukle_gidis_donus_esittir(tmp_path):
    m = model(sabit=0.1, esik=0.8, bilgi={"ornek_sayisi": 3, "l2": 1.0}, sayfa_kanitsiz_sayisi=0.3)
    yol = tmp_path / "model.json"
    m.kaydet(yol)
    assert json.loads(yol.read_text(encoding="utf-8")) == m.sozluk()
    assert gs().GuvenModeli.yukle(yol) == m


def test_gold_taslak_altina_kaydetmeye_izin_verilir(tmp_path):
    """Sınırın hemen yanı: data/gold_taslak data/gold değildir."""
    yol = tmp_path / "data" / "gold_taslak" / "model.json"
    yol.parent.mkdir(parents=True)
    model().kaydet(yol)
    assert yol.is_file()


@pytest.mark.parametrize("parcalar", [("data", "gold"), ("Data", "GOLD"), ("data", "gold", "alt")])
def test_data_gold_altina_kaydetme_reddedilir_ve_dosya_yazilmaz(tmp_path, parcalar):
    klasor = tmp_path.joinpath(*parcalar)
    klasor.mkdir(parents=True)
    yol = klasor / "x.json"
    with pytest.raises(gs().GuvenModeliHatasi):
        model().kaydet(yol)
    assert not yol.exists()


def test_olmayan_dosyayi_yuklemek_guven_modeli_hatasidir(tmp_path):
    with pytest.raises(gs().GuvenModeliHatasi):
        gs().GuvenModeli.yukle(tmp_path / "yok.json")


def test_bozuk_json_yuklemek_guven_modeli_hatasidir(tmp_path):
    yol = tmp_path / "bozuk.json"
    yol.write_text("{ bu json değil", encoding="utf-8")
    with pytest.raises(gs().GuvenModeliHatasi):
        gs().GuvenModeli.yukle(yol)


@pytest.mark.parametrize("bozma", ["sabit_yok", "agirlik_eksik", "liste", "esik_buyuk"])
def test_sema_disi_json_yuklemek_guven_modeli_hatasidir(tmp_path, bozma):
    d = model().sozluk()
    if bozma == "sabit_yok":
        del d["sabit"]
    elif bozma == "agirlik_eksik":
        del d["agirliklar"]["kanit_yok"]
    elif bozma == "liste":
        d = [d]
    elif bozma == "esik_buyuk":
        d["esik"] = 1.5
    yol = tmp_path / "sema_disi.json"
    yol.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(gs().GuvenModeliHatasi):
        gs().GuvenModeli.yukle(yol)


# --- Yönlendirme -----------------------------------------------------------------------


def test_dusuk_guvenli_uygun_insan_incelemesine_gider_ve_neden_yazilir():
    karar, neden = gs().yonlendir("uygun", 0.2, 0.5)
    assert karar == "insan_incelemeli"
    assert "güven skoru düşük" in neden


def test_esigin_hemen_altindaki_guvenle_uygun_insan_incelemesine_gider():
    esik = 0.5
    assert gs().yonlendir("uygun", math.nextafter(esik, 0.0), esik)[0] == "insan_incelemeli"


def test_tam_esikteki_guvenle_uygun_kalir():
    assert gs().yonlendir("uygun", 0.5, 0.5) == ("uygun", None)


def test_esigin_hemen_ustundeki_guvenle_uygun_kalir():
    esik = 0.5
    assert gs().yonlendir("uygun", math.nextafter(esik, 1.0), esik) == ("uygun", None)


def test_nan_guvenli_uygun_temkinle_insan_incelemesine_gider():
    karar, neden = gs().yonlendir("uygun", math.nan, 0.5)
    assert karar == "insan_incelemeli"
    assert neden


def test_model_yoksa_uygun_karari_degismez():
    assert gs().yonlendir("uygun", None, 0.5) == ("uygun", None)


@pytest.mark.parametrize("karar", ["uygun_degil", "insan_incelemeli"])
@pytest.mark.parametrize("guven", [0.0, 1.0, math.nan, None, 0.49, 0.51])
def test_uygun_olmayan_kararlar_hicbir_guvenle_degismez(karar, guven):
    sonuc, _ = gs().yonlendir(karar, guven, 0.5)
    assert sonuc == karar
    assert sonuc != "uygun"


@pytest.mark.parametrize("karar", ["kabul", "", "red"])
def test_bilinmeyen_karar_metni_reddedilir(karar):
    with pytest.raises(ValueError):
        gs().yonlendir(karar, 0.9, 0.5)


def test_incelenecek_testler_esik_alti_ve_nan_olanlari_sirali_doner():
    guvenler = {"b": 0.2, "a": 0.1, "c": 0.9, "d": math.nan, "e": 0.5, "f": math.nextafter(0.5, 0.0)}
    assert gs().incelenecek_testler(guvenler, 0.5) == ["a", "b", "d", "f"]


def test_incelenecek_testler_bos_sozlukte_bos_listedir():
    assert gs().incelenecek_testler({}, 0.5) == []


GECERSIZ_ESIKLER = [math.nan, math.inf, -math.inf, -1e-9, 1.0 + 1e-9, -0.5, 2.0]


@pytest.mark.parametrize("esik", GECERSIZ_ESIKLER)
@pytest.mark.parametrize("karar", ["uygun", "uygun_degil", "insan_incelemeli"])
@pytest.mark.parametrize("guven", [0.5, None, math.nan])
def test_yonlendir_gecersiz_esigi_karar_ne_olursa_olsun_reddeder(esik, karar, guven):
    with pytest.raises(ValueError):
        gs().yonlendir(karar, guven, esik)


def test_yonlendir_sifir_esigini_kabul_eder():
    assert gs().yonlendir("uygun", 0.0, 0.0) == ("uygun", None)


def test_yonlendir_bir_esigini_kabul_eder_ve_birin_altini_incelemeye_gonderir():
    assert gs().yonlendir("uygun", math.nextafter(1.0, 0.0), 1.0)[0] == "insan_incelemeli"


def test_bir_esiginde_tam_bir_guvenli_uygun_bile_incelemeye_gider():
    """Eşik 1.0 "otomatik geçiş yok" demektir; "uygun" yalnız güven >= eşik ve eşik < 1 iken geçer."""
    karar, neden = gs().yonlendir("uygun", 1.0, 1.0)
    assert karar == "insan_incelemeli"
    assert neden


def test_birin_hemen_altindaki_esikte_tam_bir_guvenli_uygun_gecer():
    esik = math.nextafter(1.0, 0.0)
    assert gs().yonlendir("uygun", 1.0, esik) == ("uygun", None)
    assert gs().yonlendir("uygun", esik, esik) == ("uygun", None)


GECERSIZ_GUVENLER = [-0.1, -1e-9, 1.5, 1.0 + 1e-9, math.inf, -math.inf]


@pytest.mark.parametrize("guven", GECERSIZ_GUVENLER)
@pytest.mark.parametrize("karar", ["uygun", "uygun_degil", "insan_incelemeli"])
def test_yonlendir_sifir_bir_disindaki_guveni_reddeder(guven, karar):
    with pytest.raises(ValueError):
        gs().yonlendir(karar, guven, 0.5)


@pytest.mark.parametrize("guven", [0.0, 1.0])
def test_yonlendir_sinirdaki_guvenleri_kabul_eder(guven):
    assert gs().yonlendir("uygun_degil", guven, 0.5) == ("uygun_degil", None)


@pytest.mark.parametrize("guven", GECERSIZ_GUVENLER)
def test_incelenecek_testler_sifir_bir_disindaki_guveni_reddeder(guven):
    with pytest.raises(ValueError):
        gs().incelenecek_testler({"a": 0.9, "b": guven}, 0.5)


@pytest.mark.parametrize("esik", GECERSIZ_ESIKLER)
@pytest.mark.parametrize("guvenler", [{}, {"a": 0.3, "b": 0.9}])
def test_incelenecek_testler_gecersiz_esigi_reddeder(esik, guvenler):
    with pytest.raises(ValueError):
        gs().incelenecek_testler(guvenler, esik)


def test_incelenecek_testler_sifir_ve_bir_esigini_kabul_eder():
    guvenler = {"a": 0.0, "b": math.nextafter(1.0, 0.0), "c": 1.0}
    assert gs().incelenecek_testler(guvenler, 0.0) == []
    assert gs().incelenecek_testler(guvenler, 1.0) == ["a", "b", "c"]


def test_bir_esiginde_tam_bir_guvenli_test_de_incelenir():
    assert "c" in gs().incelenecek_testler({"c": 1.0, "d": 0.2}, 1.0)


# --- Katman sınırı ---------------------------------------------------------------------


def _ice_aktarimlar(dosya: Path) -> set[str]:
    moduller: set[str] = set()
    for d in ast.walk(ast.parse(dosya.read_text(encoding="utf-8"))):
        if isinstance(d, ast.Import):
            moduller.update(a.name for a in d.names)
        elif isinstance(d, ast.ImportFrom):
            moduller.add(d.module or "")
    return moduller


def test_guven_skoru_deney_cikarim_ve_numpy_ice_aktarmaz():
    assert MODUL_YOLU.is_file(), "src/malzeme_kabul/kural/guven_skoru.py yok"
    moduller = _ice_aktarimlar(MODUL_YOLU)
    yasak = {
        m for m in moduller
        if m.split(".")[0] in ("deney", "numpy") or m == "malzeme_kabul.cikarim" or m.startswith("malzeme_kabul.cikarim.")
    }
    assert not yasak, f"yasak içe aktarma: {yasak}"
