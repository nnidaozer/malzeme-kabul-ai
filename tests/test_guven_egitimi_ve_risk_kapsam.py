"""Güven skoru eğitimi ve risk–kapsam eğrisi (deney, docs/guven_skoru.md).

Saf Python; numpy, internet ve dil modeli yok. Veri elle kurulur ya da
tmp_path altına yazılır.
"""

from __future__ import annotations

import csv
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from guven_ornekleri import TARANMIS, belge_ornegi, bolunme_dosyasi, gold_yaz, klasor_snapshot, uc_mod_yaz

KOK = Path(__file__).resolve().parents[1]
ADLAR = ("anlasmazlik_sayisi", "kanit_yok", "yalniz_model", "sayfa_kanitsiz_sayisi", "yon_celiskisi",
         "sayfa_sema_hatasi")


def eg():
    from deney import guven_egitimi

    return guven_egitimi


def rk():
    from deney import risk_kapsam

    return risk_kapsam


def G(**kw):
    from malzeme_kabul.kural.guven_skoru import GuvenGirdileri

    return GuvenGirdileri(**kw)


def ornek(belge, test_id, girdiler, hatali, zorunlu=False):
    from deney.guven_verisi import GuvenOrnegi

    return GuvenOrnegi(belge=belge, test_id=test_id, girdiler=girdiler, hatali=hatali, zorunlu_inceleme=zorunlu)


def ayrilabilir_veri():
    """Anlaşmazlıklı örneklerin hepsi hatalı, diğerleri doğru."""
    girdiler = [G(anlasmazlik_sayisi=1), G(anlasmazlik_sayisi=2), G(anlasmazlik_sayisi=1), G(), G(), G(kanit_yok=True)]
    hatalilar = [True, True, True, False, False, False]
    return girdiler, hatalilar


A, B = "MIL-PRF-23377K", "MIL-PRF-81733D"  # iki ayrı revizyon ailesi (23377, 81733)
A_REV2 = "MIL-PRF-23377G"  # A ile aynı aile


def _belge_ornekleri(belge, girdiler, etiketler, ters=False):
    return [ornek(belge, f"{belge}_{i}", g, (not h) if ters else h)
            for i, (g, h) in enumerate(zip(girdiler, etiketler))]


A_GIRDI = [G(anlasmazlik_sayisi=1), G(yon_celiskisi=True), G(), G(kanit_yok=True)]
A_ETIKET = [True, True, False, False]
B_GIRDI = [G(anlasmazlik_sayisi=2), G(), G(sayfa_sema_hatasi=1), G(yalniz_model=True)]
B_ETIKET = [True, False, False, True]
A2_GIRDI = [G(anlasmazlik_sayisi=1), G(), G(sayfa_kanitsiz_sayisi=2), G(yon_celiskisi=True)]
A2_ETIKET = [False, False, True, True]


def iki_belge(a_ters=False):
    return _belge_ornekleri(A, A_GIRDI, A_ETIKET, a_ters) + _belge_ornekleri(B, B_GIRDI, B_ETIKET)


def iki_aile_uc_revizyon(a2_ters=False):
    """A ve A_REV2 aynı aileden (23377), B başka aileden (81733)."""
    return (_belge_ornekleri(A, A_GIRDI, A_ETIKET) + _belge_ornekleri(A_REV2, A2_GIRDI, A2_ETIKET, a2_ters)
            + _belge_ornekleri(B, B_GIRDI, B_ETIKET))


# --- egit ------------------------------------------------------------------------------


def test_egit_bos_listeyi_reddeder():
    with pytest.raises(ValueError):
        eg().egit([], [])


def test_egit_uzunluk_farkini_reddeder():
    with pytest.raises(ValueError):
        eg().egit([G(), G()], [True])


def test_egit_negatif_l2yi_reddeder():
    girdiler, hatalilar = ayrilabilir_veri()
    with pytest.raises(ValueError):
        eg().egit(girdiler, hatalilar, l2=-1e-9)


def test_egit_sifir_l2yi_kabul_eder():
    girdiler = [G(anlasmazlik_sayisi=1), G(anlasmazlik_sayisi=1), G(), G()]
    hatalilar = [True, False, False, True]  # ayrılamaz veri
    m = eg().egit(girdiler, hatalilar, l2=0.0)
    assert all(math.isfinite(w) for w in m.agirliklar.values())


def test_egit_guven_modeli_doner_ve_esigi_yarimdir():
    from malzeme_kabul.kural.guven_skoru import GuvenModeli

    m = eg().egit(*ayrilabilir_veri())
    assert isinstance(m, GuvenModeli)
    assert m.esik == 0.5


def test_egit_bilgiye_ornek_sayisi_ve_l2_yazar():
    m = eg().egit(*ayrilabilir_veri(), l2=2.5)
    assert m.bilgi["ornek_sayisi"] == 6
    assert m.bilgi["l2"] == 2.5


def test_egit_belirlenimcidir():
    a = eg().egit(*ayrilabilir_veri())
    b = eg().egit(*ayrilabilir_veri())
    assert a.agirliklar == b.agirliklar
    assert a.sabit == b.sabit


def test_ayrilabilir_veride_agirliklar_sonludur():
    m = eg().egit(*ayrilabilir_veri(), l2=1.0)
    assert all(math.isfinite(w) for w in m.agirliklar.values())
    assert math.isfinite(m.sabit)


def test_anlasmazlik_hatayla_birlikteyse_agirligi_pozitiftir():
    m = eg().egit(*ayrilabilir_veri())
    assert m.agirliklar["anlasmazlik_sayisi"] > 0


def test_anlasmazlikli_ornegin_guveni_anlasmazliksizdan_dusuktur():
    m = eg().egit(*ayrilabilir_veri())
    assert m.guven(G(anlasmazlik_sayisi=1)) < m.guven(G())


@pytest.mark.parametrize("sinif", [True, False])
def test_hepsi_ayni_siniftayken_egitim_hata_vermez(sinif):
    girdiler = [G(), G(anlasmazlik_sayisi=1), G(kanit_yok=True)]
    m = eg().egit(girdiler, [sinif] * 3)
    assert all(math.isfinite(w) for w in m.agirliklar.values())
    assert math.isfinite(m.sabit)


def test_buyuk_l2de_agirliklar_sifira_yaklasir_sabit_duzenlenmez():
    """Sabit terim düzenlenmez: ağırlıklar ~0 iken sabit, hata oranının logitine oturur (1/4 -> log(1/3))."""
    girdiler = [G(anlasmazlik_sayisi=1), G(), G(kanit_yok=True), G(yon_celiskisi=True)]
    m = eg().egit(girdiler, [True, False, False, False], l2=1e6)
    assert all(abs(w) < 1e-3 for w in m.agirliklar.values())
    assert m.sabit == pytest.approx(math.log(1 / 3), abs=1e-2)


def test_buyuk_l2_agirliklari_kucuk_l2den_kucuk_tutar():
    zayif = eg().egit(*ayrilabilir_veri(), l2=0.1)
    guclu = eg().egit(*ayrilabilir_veri(), l2=10.0)
    assert abs(guclu.agirliklar["anlasmazlik_sayisi"]) < abs(zayif.agirliklar["anlasmazlik_sayisi"])


# --- disarida_birakmali_tahmin -------------------------------------------------------


def test_disarida_birakmali_tahmin_her_ornek_icin_bir_guven_doner():
    ornekler = iki_belge()
    tahmin = eg().disarida_birakmali_tahmin(ornekler)
    assert len(tahmin) == len(ornekler)
    assert all(0.0 <= g <= 1.0 for g in tahmin)


def test_belgenin_kendi_etiketleri_kendi_tahminini_degistirmez():
    once = eg().disarida_birakmali_tahmin(iki_belge(a_ters=False))
    sonra = eg().disarida_birakmali_tahmin(iki_belge(a_ters=True))
    assert once[:4] == sonra[:4]  # A'nın tahminleri yalnız B ile eğitilen modelden


def test_belgenin_etiketleri_diger_belgenin_tahminini_degistirir():
    once = eg().disarida_birakmali_tahmin(iki_belge(a_ters=False))
    sonra = eg().disarida_birakmali_tahmin(iki_belge(a_ters=True))
    assert once[4:] != sonra[4:]


def test_disarida_birakmali_tahmin_tek_belgede_hata_verir():
    ornekler = [o for o in iki_belge() if o.belge == A]
    with pytest.raises(ValueError):
        eg().disarida_birakmali_tahmin(ornekler)


def test_ayni_ailedeki_revizyonun_etiketleri_kardes_revizyonun_tahminini_degistirmez():
    """Dışarıda bırakma revizyon ailesi bazında: 23377G ve 23377K birlikte dışarıda kalır."""
    once = eg().disarida_birakmali_tahmin(iki_aile_uc_revizyon(a2_ters=False))
    sonra = eg().disarida_birakmali_tahmin(iki_aile_uc_revizyon(a2_ters=True))
    assert once[:4] == sonra[:4]  # A (23377K)
    assert once[4:8] == sonra[4:8]  # A_REV2 (23377G) kendi etiketlerinden de etkilenmez


def test_baska_ailenin_tahmini_revizyonun_etiketleriyle_degisir():
    once = eg().disarida_birakmali_tahmin(iki_aile_uc_revizyon(a2_ters=False))
    sonra = eg().disarida_birakmali_tahmin(iki_aile_uc_revizyon(a2_ters=True))
    assert once[8:] != sonra[8:]  # B (81733D) 23377 ailesiyle eğitilir


def test_tek_aile_iki_revizyon_olsa_bile_disarida_birakmali_tahmin_hata_verir():
    ornekler = [o for o in iki_aile_uc_revizyon() if o.belge in (A, A_REV2)]
    assert len({o.belge for o in ornekler}) == 2
    with pytest.raises(ValueError):
        eg().disarida_birakmali_tahmin(ornekler)


# --- risk_kapsam.egri ----------------------------------------------------------------


def test_egri_noktasi_alanlari_plandaki_sirayladir():
    import dataclasses

    assert tuple(f.name for f in dataclasses.fields(rk().EgriNoktasi)) == (
        "esik", "kapsam", "risk", "otomatik", "hatali_otomatik")


def test_egrinin_ilk_noktasi_bos_kapsam_ve_sifir_risktir():
    n = rk().egri([0.9, 0.2], [False, True], [False, False])[0]
    assert n.esik > 1.0
    assert (n.kapsam, n.risk, n.otomatik, n.hatali_otomatik) == (0.0, 0.0, 0, 0)


def test_egri_el_hesabiyla_dort_testte_dogrudur():
    noktalar = rk().egri([0.9, 0.8, 0.7, 0.6], [False, False, True, False], [False] * 4)
    beklenen = [(0.9, 0.25, 0.0, 1, 0), (0.8, 0.5, 0.0, 2, 0), (0.7, 0.75, 1 / 3, 3, 1), (0.6, 1.0, 0.25, 4, 1)]
    assert len(noktalar) == 5
    for n, (esik, kapsam, risk, otomatik, hatali) in zip(noktalar[1:], beklenen):
        assert n.esik == pytest.approx(esik)
        assert n.kapsam == pytest.approx(kapsam)
        assert n.risk == pytest.approx(risk)
        assert (n.otomatik, n.hatali_otomatik) == (otomatik, hatali)


def test_egri_esikleri_buyukten_kucuge_siralidir():
    noktalar = rk().egri([0.3, 0.9, 0.6], [False, False, False], [False] * 3)
    esikler = [n.esik for n in noktalar]
    assert esikler == sorted(esikler, reverse=True)
    assert esikler[1:] == pytest.approx([0.9, 0.6, 0.3])


def test_esit_guvenler_ayni_noktadadir():
    noktalar = rk().egri([0.8, 0.8, 0.5], [False, True, False], [False] * 3)
    assert len(noktalar) == 3
    assert noktalar[1].esik == pytest.approx(0.8)
    assert (noktalar[1].otomatik, noktalar[1].hatali_otomatik) == (2, 1)
    assert noktalar[1].risk == pytest.approx(0.5)


def test_zorunlu_testler_hicbir_noktada_otomatik_sayilmaz():
    guvenler = [0.9, 0.8, 0.8, 0.6, 0.95]
    hatalilar = [False, False, True, False, True]
    zorunlular = [False, False, False, False, True]
    noktalar = rk().egri(guvenler, hatalilar, zorunlular)
    beklenen = [(0.9, 0.2, 0.0, 1, 0), (0.8, 0.6, 1 / 3, 3, 1), (0.6, 0.8, 0.25, 4, 1)]
    assert len(noktalar) == 4  # zorunlu testin güveni (0.95) eşik olmaz
    for n, (esik, kapsam, risk, otomatik, hatali) in zip(noktalar[1:], beklenen):
        assert n.esik == pytest.approx(esik)
        assert n.kapsam == pytest.approx(kapsam)
        assert n.risk == pytest.approx(risk)
        assert (n.otomatik, n.hatali_otomatik) == (otomatik, hatali)
    assert noktalar[-1].kapsam < 1.0


def test_egri_uzunluk_farkini_reddeder():
    with pytest.raises(ValueError):
        rk().egri([0.9, 0.8], [False], [False, False])
    with pytest.raises(ValueError):
        rk().egri([0.9, 0.8], [False, False], [False])


# --- aurc ------------------------------------------------------------------------------


def test_aurc_yamuk_kuraliyla_el_hesabina_esittir():
    noktalar = rk().egri([0.9, 0.8, 0.7, 0.6], [False, False, True, False], [False] * 4)
    # 0.25*(0+1/3)/2 + 0.25*(1/3+1/4)/2
    assert rk().aurc(noktalar) == pytest.approx(0.25 * (1 / 3) / 2 + 0.25 * (1 / 3 + 0.25) / 2)


def test_aurc_elle_kurulan_noktalarda_yamuk_alanidir():
    N = rk().EgriNoktasi
    noktalar = [N(math.inf, 0.0, 0.0, 0, 0), N(0.8, 0.5, 0.2, 1, 0), N(0.4, 1.0, 0.4, 2, 1)]
    assert rk().aurc(noktalar) == pytest.approx(0.5 * 0.2 / 2 + 0.5 * (0.2 + 0.4) / 2)


def test_mukemmel_siralamanin_aurcu_ters_siralamadan_kucuktur():
    guvenler = [0.9, 0.8, 0.7, 0.6]
    mukemmel = rk().aurc(rk().egri(guvenler, [False, False, False, True], [False] * 4))
    ters = rk().aurc(rk().egri(guvenler, [True, False, False, False], [False] * 4))
    assert mukemmel == pytest.approx(0.25 * 0.25 / 2)
    assert ters == pytest.approx(0.25 * 1 / 2 + 0.25 * 1.5 / 2 + 0.25 * (0.5 + 1 / 3) / 2 + 0.25 * (1 / 3 + 0.25) / 2)
    assert mukemmel < ters


# --- esik_sec ------------------------------------------------------------------------


def test_esik_sec_hedef_riski_asmayan_en_yuksek_kapsamin_esigini_verir():
    guvenler = [0.9, 0.8, 0.7, 0.6]
    hatalilar = [False, False, True, False]
    assert eg().esik_sec(guvenler, hatalilar, [False] * 4, hedef_risk=0.01) == pytest.approx(0.8)


def test_esik_sec_hedef_risk_genisleyince_kapsam_artar():
    guvenler = [0.9, 0.8, 0.7, 0.6]
    hatalilar = [False, False, True, False]
    assert eg().esik_sec(guvenler, hatalilar, [False] * 4, hedef_risk=0.3) == pytest.approx(0.6)


def test_esik_sec_tam_hedef_riskteki_noktayi_kabul_eder():
    guvenler = [0.9, 0.8, 0.7, 0.6]
    hatalilar = [False, False, True, False]
    assert eg().esik_sec(guvenler, hatalilar, [False] * 4, hedef_risk=0.25) == pytest.approx(0.6)


def test_esik_sec_hedef_riskin_hemen_altinda_daha_dar_esigi_verir():
    guvenler = [0.9, 0.8, 0.7, 0.6]
    hatalilar = [False, False, True, False]
    assert eg().esik_sec(guvenler, hatalilar, [False] * 4, hedef_risk=math.nextafter(0.25, 0.0)) == pytest.approx(0.8)


def test_hedefi_saglayan_nokta_yoksa_esikte_otomatik_gecen_yoktur():
    guvenler = [0.9, 0.8, 0.7]
    hatalilar = [True, False, False]  # en güvenli test hatalı
    esik = eg().esik_sec(guvenler, hatalilar, [False] * 3, hedef_risk=0.01)
    assert esik <= 1.0
    assert not any(g >= esik for g in guvenler)


def test_esik_sec_zorunlu_testin_hatasini_riske_katmaz():
    guvenler = [0.95, 0.9, 0.8]
    hatalilar = [True, False, False]
    assert eg().esik_sec(guvenler, hatalilar, [True, False, False], hedef_risk=0.01) == pytest.approx(0.8)


def test_hedefi_saglayan_nokta_yoksa_bire_cok_yakin_guvenle_de_otomatik_gecen_yoktur():
    en_yuksek = math.nextafter(1.0, 0.0)
    guvenler = [en_yuksek, 0.8, 0.7]
    hatalilar = [True, False, False]
    esik = eg().esik_sec(guvenler, hatalilar, [False] * 3, hedef_risk=0.01)
    assert esik <= 1.0
    assert not any(g >= esik for g in guvenler)


def test_egitilen_modelin_guvenleriyle_hedef_tutmazsa_hicbir_test_gecmez():
    """Model güveni 1.0'a ulaşmadığından esik_sec'in 1.0 eşiği gerçekten her testi incelemeye gönderir."""
    from malzeme_kabul.kural.guven_skoru import GuvenModeli, yonlendir

    m = GuvenModeli(agirliklar={ad: 0.0 for ad in ADLAR}, sabit=-1000.0, esik=0.5)
    guvenler = [m.guven(G()), 0.5]
    esik = eg().esik_sec(guvenler, [True, False], [False, False], hedef_risk=0.01)
    assert all(yonlendir("uygun", g, esik)[0] == "insan_incelemeli" for g in guvenler)


@pytest.mark.parametrize("hedef", [math.nan, -1e-9, 1.0 + 1e-9, -0.5, 2.0, math.inf])
def test_esik_sec_gecersiz_hedef_riski_reddeder(hedef):
    with pytest.raises(ValueError, match="hedef_risk"):
        eg().esik_sec([0.9, 0.8], [False, False], [False, False], hedef_risk=hedef)


@pytest.mark.parametrize("hedef,beklenen", [(0.0, 0.8), (1.0, 0.6)])
def test_esik_sec_sinirdaki_hedef_riskleri_kabul_eder(hedef, beklenen):
    guvenler = [0.9, 0.8, 0.7, 0.6]
    hatalilar = [False, False, True, False]
    assert eg().esik_sec(guvenler, hatalilar, [False] * 4, hedef_risk=hedef) == pytest.approx(beklenen)


# --- svg_ciz ---------------------------------------------------------------------------


def _noktalar():
    return rk().egri([0.9, 0.8, 0.7, 0.6], [False, False, True, False], [False] * 4)


def test_svg_ciz_svg_ile_baslar_ve_cizgi_icerir():
    svg = rk().svg_ciz(_noktalar(), "Risk–kapsam")
    assert svg.startswith("<svg")
    assert "<polyline" in svg


def test_svg_ciz_xml_olarak_ayristirilir():
    kok = ET.fromstring(rk().svg_ciz(_noktalar(), "Risk–kapsam"))
    assert kok.tag.endswith("svg")


def test_svg_ciz_basligi_xml_kacisiyla_yazar():
    baslik = "Güven <&> \"skoru\""
    svg = rk().svg_ciz(_noktalar(), baslik)
    assert "<&>" not in svg
    kok = ET.fromstring(svg)
    assert baslik in "".join(kok.itertext())


# --- Ortak: tmp_path altında üç mod sonuçları --------------------------------------------


@pytest.fixture
def ortam(tmp_path):
    bolunme, test_etiketi = bolunme_dosyasi(tmp_path)
    girdi = tmp_path / "colab_uc_mod"
    kok = tmp_path / "kok"
    for etiket, hatali_ust in (("MIL-PRF-23377K", True), ("MIL-PRF-81733D", False)):
        kural, dil, hibrit, r, gold = belge_ornegi(etiket[:-1], etiket[-1], hatali_ust=hatali_ust)
        uc_mod_yaz(girdi, etiket, kural, dil, hibrit, r)
        gold_yaz(kok, "gold_taslak", etiket, gold)
    return {"tmp": tmp_path, "bolunme": bolunme, "test_etiketi": test_etiketi, "girdi": girdi, "kok": kok}


def _egitim_argv(ortam, cikti, *ek):
    return ["--girdi", str(ortam["girdi"]), "--cikti", str(cikti), "--bolunme", str(ortam["bolunme"]),
            "--kok", str(ortam["kok"]), *ek]


def _bool(metin: str) -> bool:
    m = metin.strip().casefold()
    assert m in ("1", "0", "true", "false"), f"beklenmeyen ikili değer: {metin!r}"
    return m in ("1", "true")


def _csv(yol: Path) -> list[dict[str, str]]:
    with open(yol, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# --- guven_egitimi.main --------------------------------------------------------------


def test_egitim_main_model_tahmin_ve_rapor_yazar(ortam):
    cikti = ortam["tmp"] / "guven"
    assert eg().main(_egitim_argv(ortam, cikti)) == 0
    assert (cikti / "model.json").is_file()
    assert (cikti / "tahminler.csv").is_file()
    assert isinstance(json.loads((cikti / "egitim_raporu.json").read_text(encoding="utf-8")), dict)


def test_tahminler_csv_sutunlari_plandaki_gibidir(ortam):
    cikti = ortam["tmp"] / "guven"
    eg().main(_egitim_argv(ortam, cikti))
    with open(cikti / "tahminler.csv", encoding="utf-8", newline="") as f:
        baslik = next(csv.reader(f))
    assert baslik == ["belge", "test_id", *ADLAR, "hatali", "zorunlu_inceleme", "guven"]


def test_tahminler_her_ornek_icin_disarida_birakmali_guveni_yazar(ortam):
    from deney.guven_verisi import klasorden_oku

    cikti = ortam["tmp"] / "guven"
    eg().main(_egitim_argv(ortam, cikti))
    ornekler, _ = klasorden_oku(ortam["girdi"], bolunme=ortam["bolunme"], kok=ortam["kok"])
    beklenen = {(o.belge, o.test_id): g for o, g in zip(ornekler, eg().disarida_birakmali_tahmin(ornekler))}
    satirlar = _csv(cikti / "tahminler.csv")
    assert len(satirlar) == len(ornekler) == 6
    for s in satirlar:
        assert float(s["guven"]) == pytest.approx(beklenen[(s["belge"], s["test_id"])], rel=1e-9)
    hatali = {(s["belge"], s["test_id"]): _bool(s["hatali"]) for s in satirlar}
    assert hatali == {(o.belge, o.test_id): o.hatali for o in ornekler}


def test_model_butun_orneklerle_egitilir_ve_esik_esik_secten_gelir(ortam):
    from deney.guven_verisi import klasorden_oku
    from malzeme_kabul.kural.guven_skoru import GuvenModeli

    cikti = ortam["tmp"] / "guven"
    eg().main(_egitim_argv(ortam, cikti, "--l2", "2.0", "--hedef-risk", "0.2"))
    m = GuvenModeli.yukle(cikti / "model.json")
    ornekler, _ = klasorden_oku(ortam["girdi"], bolunme=ortam["bolunme"], kok=ortam["kok"])
    beklenen = eg().egit([o.girdiler for o in ornekler], [o.hatali for o in ornekler], l2=2.0)
    assert m.agirliklar == pytest.approx(beklenen.agirliklar, rel=1e-9, abs=1e-12)
    assert m.sabit == pytest.approx(beklenen.sabit, rel=1e-9, abs=1e-12)
    guvenler = eg().disarida_birakmali_tahmin(ornekler, l2=2.0)
    esik = eg().esik_sec(guvenler, [o.hatali for o in ornekler], [o.zorunlu_inceleme for o in ornekler],
                         hedef_risk=0.2)
    assert m.esik == pytest.approx(esik, rel=1e-9)


@pytest.mark.parametrize("parcalar", [("data", "gold", "guven"), ("DATA", "Gold", "guven")])
def test_egitim_ciktisi_data_gold_altindaysa_2_doner_ve_yazmaz(ortam, parcalar):
    cikti = ortam["tmp"].joinpath(*parcalar)
    assert eg().main(_egitim_argv(ortam, cikti)) == 2
    assert not cikti.exists() or not any(cikti.iterdir())


def test_egitim_test_kumesi_belgesinde_2_doner(ortam):
    kural, dil, hibrit, r, gold = belge_ornegi(ortam["test_etiketi"][:-1], ortam["test_etiketi"][-1])
    uc_mod_yaz(ortam["girdi"], ortam["test_etiketi"], kural, dil, hibrit, r)
    cikti = ortam["tmp"] / "guven"
    assert eg().main(_egitim_argv(ortam, cikti)) == 2
    assert not (cikti / "model.json").exists()


def test_egitim_hic_ornek_yoksa_2_doner_ve_sonuc_yok_der(ortam, capsys):
    bos = ortam["tmp"] / "bos"
    bos.mkdir()
    argv = ["--girdi", str(bos), "--cikti", str(ortam["tmp"] / "guven"), "--bolunme", str(ortam["bolunme"]),
            "--kok", str(ortam["kok"])]
    assert eg().main(argv) == 2
    assert "sonuç yok" in capsys.readouterr().err


def test_egitim_main_gercek_depodaki_data_goldu_degistirmez(ortam):
    once = klasor_snapshot(KOK / "data" / "gold")
    eg().main(_egitim_argv(ortam, ortam["tmp"] / "guven"))
    assert klasor_snapshot(KOK / "data" / "gold") == once


def _bos_ya_da_yok(klasor: Path) -> bool:
    return not klasor.exists() or not any(klasor.iterdir())


@pytest.mark.parametrize("hedef", ["nan", "-0.01", "1.01", "inf"])
def test_egitim_gecersiz_hedef_riskte_2_doner_ve_yazmaz(ortam, capsys, hedef):
    cikti = ortam["tmp"] / "guven"
    assert eg().main(_egitim_argv(ortam, cikti, "--hedef-risk", hedef)) == 2
    assert "hedef_risk" in capsys.readouterr().err
    assert _bos_ya_da_yok(cikti)


@pytest.mark.parametrize("hedef", ["0", "1"])
def test_egitim_sinirdaki_hedef_riskleri_kabul_eder(ortam, hedef):
    assert eg().main(_egitim_argv(ortam, ortam["tmp"] / "guven", "--hedef-risk", hedef)) == 0


def test_egitim_taranmis_belgede_2_doner_ve_yazmaz(ortam):
    kural, dil, hibrit, r, gold = belge_ornegi(TARANMIS[:-1], TARANMIS[-1])
    uc_mod_yaz(ortam["girdi"], TARANMIS, kural, dil, hibrit, r)
    gold_yaz(ortam["kok"], "gold_taslak", TARANMIS, gold)
    cikti = ortam["tmp"] / "guven"
    assert eg().main(_egitim_argv(ortam, cikti)) == 2
    assert _bos_ya_da_yok(cikti)


def test_egitim_test_kumesi_belgesinde_hicbir_sey_yazmaz(ortam):
    kural, dil, hibrit, r, gold = belge_ornegi(ortam["test_etiketi"][:-1], ortam["test_etiketi"][-1])
    uc_mod_yaz(ortam["girdi"], ortam["test_etiketi"], kural, dil, hibrit, r)
    cikti = ortam["tmp"] / "guven"
    assert eg().main(_egitim_argv(ortam, cikti)) == 2
    assert _bos_ya_da_yok(cikti)


def _rapor_oku(cikti: Path) -> dict:
    return json.loads((cikti / "egitim_raporu.json").read_text(encoding="utf-8"))


def test_egitim_raporu_gold_u_olmayan_belgeleri_atlanan_diye_yazar(ortam):
    kural, dil, hibrit, r, _ = belge_ornegi("MIL-PRF-23377", "G")
    uc_mod_yaz(ortam["girdi"], "MIL-PRF-23377G", kural, dil, hibrit, r)  # gold yok
    cikti = ortam["tmp"] / "guven"
    assert eg().main(_egitim_argv(ortam, cikti)) == 0
    assert _rapor_oku(cikti)["atlanan"] == ["MIL-PRF-23377G"]


def test_egitim_raporunda_atlanan_yoksa_bos_listedir(ortam):
    cikti = ortam["tmp"] / "guven"
    eg().main(_egitim_argv(ortam, cikti))
    assert _rapor_oku(cikti)["atlanan"] == []


def test_egitim_raporunun_aurcu_tahminlerin_egrisinden_gelir(ortam):
    cikti = ortam["tmp"] / "guven"
    eg().main(_egitim_argv(ortam, cikti))
    satirlar = _csv(cikti / "tahminler.csv")
    beklenen = rk().aurc(rk().egri([float(s["guven"]) for s in satirlar], [_bool(s["hatali"]) for s in satirlar],
                                   [_bool(s["zorunlu_inceleme"]) for s in satirlar]))
    assert _rapor_oku(cikti)["aurc_disarida_birakmali"] == pytest.approx(beklenen, rel=1e-9, abs=1e-12)


def test_egitim_raporunun_esigi_model_dosyasindakiyle_aynidir(ortam):
    from malzeme_kabul.kural.guven_skoru import GuvenModeli

    cikti = ortam["tmp"] / "guven"
    eg().main(_egitim_argv(ortam, cikti, "--hedef-risk", "0.3"))
    assert _rapor_oku(cikti)["esik"] == pytest.approx(GuvenModeli.yukle(cikti / "model.json").esik, rel=1e-12)


# --- risk_kapsam.main ----------------------------------------------------------------


def _rk_argv(ortam, tahminler, cikti):
    return [str(tahminler), "--cikti", str(cikti), "--bolunme", str(ortam["bolunme"])]


@pytest.fixture
def tahminler(ortam):
    cikti = ortam["tmp"] / "guven"
    assert eg().main(_egitim_argv(ortam, cikti)) == 0
    return cikti / "tahminler.csv"


def test_risk_kapsam_main_csv_ve_svg_yazar(ortam, tahminler, capsys):
    cikti = ortam["tmp"] / "egri"
    assert rk().main(_rk_argv(ortam, tahminler, cikti)) == 0
    with open(cikti / "risk_kapsam.csv", encoding="utf-8", newline="") as f:
        assert next(csv.reader(f)) == ["esik", "kapsam", "risk", "otomatik", "hatali_otomatik"]
    ET.fromstring((cikti / "risk_kapsam.svg").read_text(encoding="utf-8"))


def test_risk_kapsam_csv_tahminlerin_egrisidir(ortam, tahminler):
    cikti = ortam["tmp"] / "egri"
    rk().main(_rk_argv(ortam, tahminler, cikti))
    satirlar = _csv(tahminler)
    noktalar = rk().egri([float(s["guven"]) for s in satirlar], [_bool(s["hatali"]) for s in satirlar],
                         [_bool(s["zorunlu_inceleme"]) for s in satirlar])
    yazilan = _csv(cikti / "risk_kapsam.csv")
    assert len(yazilan) == len(noktalar)
    for s, n in zip(yazilan, noktalar):
        assert float(s["kapsam"]) == pytest.approx(n.kapsam)
        assert float(s["risk"]) == pytest.approx(n.risk)
        assert (int(s["otomatik"]), int(s["hatali_otomatik"])) == (n.otomatik, n.hatali_otomatik)


def test_risk_kapsam_main_aurcu_stdouta_basar(ortam, tahminler, capsys):
    rk().main(_rk_argv(ortam, tahminler, ortam["tmp"] / "egri"))
    cikis = capsys.readouterr().out
    satirlar = _csv(tahminler)
    beklenen = rk().aurc(rk().egri([float(s["guven"]) for s in satirlar], [_bool(s["hatali"]) for s in satirlar],
                                   [_bool(s["zorunlu_inceleme"]) for s in satirlar]))
    sayilar = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?", cikis)]
    assert any(abs(x - beklenen) < 1e-3 for x in sayilar), cikis


def test_risk_kapsam_ciktisi_data_gold_altindaysa_2_doner_ve_yazmaz(ortam, tahminler):
    cikti = ortam["tmp"] / "data" / "gold" / "egri"
    assert rk().main(_rk_argv(ortam, tahminler, cikti)) == 2
    assert not cikti.exists() or not any(cikti.iterdir())


def _belge_degistir(tahminler: Path, yeni_belge: str) -> Path:
    """Eğitimin yazdığı tahminler.csv'nin ilk satırının belgesini değiştirip yeni bir dosyaya yazar."""
    with open(tahminler, encoding="utf-8", newline="") as f:
        okuyucu = csv.DictReader(f)
        sutunlar, satirlar = okuyucu.fieldnames, list(okuyucu)
    satirlar[0]["belge"] = yeni_belge
    yol = tahminler.with_name("degistirilmis.csv")
    with open(yol, "w", encoding="utf-8", newline="") as f:
        yazici = csv.DictWriter(f, fieldnames=sutunlar)
        yazici.writeheader()
        yazici.writerows(satirlar)
    return yol


def test_risk_kapsam_test_kumesi_satirinda_2_doner_ve_yazmaz(ortam, tahminler):
    cikti = ortam["tmp"] / "egri"
    yol = _belge_degistir(tahminler, ortam["test_etiketi"])
    assert rk().main(_rk_argv(ortam, yol, cikti)) == 2
    assert _bos_ya_da_yok(cikti)


def test_risk_kapsam_taranmis_belge_satirinda_2_doner_ve_yazmaz(ortam, tahminler):
    cikti = ortam["tmp"] / "egri"
    yol = _belge_degistir(tahminler, TARANMIS)
    assert rk().main(_rk_argv(ortam, yol, cikti)) == 2
    assert _bos_ya_da_yok(cikti)


def test_risk_kapsam_bolunmeyi_verilen_dosyadan_okur(ortam, tahminler):
    """Yalnız tmp bölünmesinin geliştirme kümesinde olan belge kabul edilir; --bolunme yok sayılırsa düşer."""
    from deney.bolunme import bolunme_oku

    gercek = bolunme_oku()
    tmp = bolunme_oku(ortam["bolunme"])
    adaylar = [e for e in tmp.gelistirme if tmp.kume(e) == "gelistirme" and e not in tmp.ocr_gerekli
               and gercek.kume(e) is None]
    assert adaylar, "tmp bölünmesinde gerçek bölünmede olmayan geliştirme belgesi yok"
    cikti = ortam["tmp"] / "egri"
    yol = _belge_degistir(tahminler, adaylar[0])
    assert rk().main(_rk_argv(ortam, yol, cikti)) == 0
    assert (cikti / "risk_kapsam.csv").is_file()
