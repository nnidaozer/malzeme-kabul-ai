"""Sınır yönü doğrulaması: dil modelinin yazdığı yön, özgün metinden kuralla çıkarılan yönle karşılaştırılır.

docs/mimari.md madde 6, kör nokta 6 (sınır yönü hatası). Örnek: qwen2.5:7b, 23377K
kadmiyum şartındaki "≤ 1 ppm" metnini alt sınır 0,001 olarak yazdı
(deney/sonuclar/colab/MIL-PRF-23377K_dil_modeli_qwen2.json).
"""

from __future__ import annotations

import json

import pytest

from malzeme_kabul.kural.yon_dogrulama import metinden_yon, okuma_yonu_dogrula, yon_dogrula, yonu_guvenli_yap
from malzeme_kabul.sozlesme.okuma import HamOkuma
from malzeme_kabul.sozlesme.sema import Sinir


def _sinir(**k) -> Sinir:
    return Sinir.model_validate({"kriter_turu": "sayisal", "birim": "ppm", **k})


# --- Metinden yön -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("metin", "yon"),
    [
        ("≤ 1 ppm", "en_cok"),
        ("<= 1 ppm", "en_cok"),
        ("shall be not greater than one part per million (ppm)", "en_cok"),
        ("shall contain not more than 0.05 percent by weight of lead", "en_cok"),
        ("the maximum viscosity shall be 40 seconds", "en_cok"),
        ("shall not exceed 340 g/L", "en_cok"),
        ("shall be tack free within 5 hours", "en_cok"),
        ("pot life shall be not less than 4 hours", "en_az"),
        ("adhesion shall be at least 4A", "en_az"),
        ("minimum 85 percent", "en_az"),
        ("≥ 60", "en_az"),
        ("15 to 30 seconds", "aralik"),
        ("within the range of 10 to 30 seconds", "aralik"),
        ("between 1.0 and 1.5 mils", "aralik"),
        ("0.6 – 0.9 mil", "aralik"),
        ("1.0 ± 0.2 mil", "aralik"),
    ],
)
def test_metinden_yon_ipuclarini_tanir(metin, yon):
    assert metinden_yon(metin) == yon


@pytest.mark.parametrize(
    "metin",
    [
        "Viscosity by Ford Viscosity Cup",  # yön ipucu yok
        "shall be 40 seconds",  # yön söylenmemiş
        "not less than 2 hours and not more than 8 hours",  # iki ayrı yön, aralık kalıbı yok: kural karar vermez
    ],
)
def test_ipucu_yoksa_ya_da_karisiksa_yon_bilinmez(metin):
    assert metinden_yon(metin) is None


def test_kosul_araligi_sinir_araligi_sayilmaz():
    # Dalga boyu ya da sıcaklık aralığı test koşuludur; sınırın yönü "not greater than".
    metin = ("shall be not greater than ten percent throughout the range of 700 to 2,600 nanometers (nm)")
    assert metinden_yon(metin) == "en_cok"
    assert metinden_yon("not less than 4 hours at 21 to 27 °C") == "en_az"


def test_madde_numarasi_aralik_sayilmaz():
    metin = "cleaning efficiency of not less than 75 percent, when cleaned in accordance with 4.6.13 through 4.6.13.5"
    assert metinden_yon(metin) == "en_az"


def test_aralik_ile_tek_yon_birlikteyse_kural_karar_vermez():
    metin = "contrast ratio of no less than 0.95, when cast to a dry film thickness of 1.9 to 2.1 mils"
    assert metinden_yon(metin) is None


def test_uzaktaki_olumsuzluk_yonu_cevirir():
    assert metinden_yon("no component shall contain cadmium, or more than 0.05 percent by weight of lead") == "en_cok"
    assert metinden_yon("no component of the coating shall contain ... more than 0.05 percent of lead") == "en_cok"
    assert metinden_yon("Do not add thinner if that addition will raise the VOC content to greater than 340 g/L") == "en_cok"


def test_olumsuz_kalip_olumlu_kaliba_yenilmez():
    # "not less than" içinde "less than" geçer; uzun kalıp önce eşleşmeli.
    assert metinden_yon("not less than 4 hours") == "en_az"
    assert metinden_yon("not greater than 1 ppm") == "en_cok"


# --- Sınır doğrulama ---------------------------------------------------------------


def test_kadmiyum_ornegi_celiski_olarak_yakalanir():
    # qwen2.5'in gerçek çıktısı: metin "≤ 1 ppm", model alt=0.001 yazdı (yön: en_az).
    s = _sinir(alt=0.001, ust=None, alt_dahil=True, ust_dahil=False, orijinal_metin="≤ 1 ppm")
    d = yon_dogrula(s)
    assert d.durum == "celiski"
    assert d.metin_yonu == "en_cok" and d.model_yonu == "en_az"
    assert "en_cok" in d.aciklama and "en_az" in d.aciklama


def test_dogru_yon_uyumlu():
    s = _sinir(ust=1.0, orijinal_metin="not greater than one part per million (ppm)")
    assert yon_dogrula(s).durum == "uyumlu"


def test_acik_yazilmis_yon_de_denetlenir():
    s = _sinir(ust=40.0, yon="en_cok", birim="s", orijinal_metin="15 to 30 seconds")
    d = yon_dogrula(s)
    assert d.durum == "celiski" and d.metin_yonu == "aralik" and d.model_yonu == "en_cok"


def test_metinde_ipucu_yoksa_dogrulanamaz_ama_celiski_sayilmaz():
    s = _sinir(alt=10.0, ust=30.0, birim="s", orijinal_metin="Viscosity by Ford Viscosity Cup")
    assert yon_dogrula(s).durum == "metinde_ipucu_yok"


def test_yonu_zaten_belirsiz_olan_dokunulmaz():
    s = _sinir(alt=4.0, yon="belirsiz", birim="hour", orijinal_metin="not less than 4 hours")
    assert yon_dogrula(s).durum == "belirsiz"


def test_sayisal_olmayan_kriter_denetlenmez():
    s = Sinir(kriter_turu="metinsel", orijinal_metin="shall not exceed the standard")
    assert yon_dogrula(s).durum == "sayisal_degil"


# --- Güvenli hale getirme ----------------------------------------------------------


def test_celiskide_yon_belirsiz_yapilir_sayilar_korunur():
    s = _sinir(alt=0.001, ust=None, orijinal_metin="≤ 1 ppm")
    yeni, d = yonu_guvenli_yap(s)
    assert d.durum == "celiski"
    assert yeni.yon == "belirsiz" and yeni.yon_belirsiz  # karar motoru insan incelemesine gönderir
    assert yeni.alt == 0.001 and yeni.orijinal_metin == "≤ 1 ppm"
    assert s.yon is None  # özgün nesne değişmez


def test_uyumluysa_sinir_aynen_doner():
    s = _sinir(ust=1.0, orijinal_metin="≤ 1 ppm")
    yeni, d = yonu_guvenli_yap(s)
    assert d.durum == "uyumlu" and yeni == s


# --- Ürün sözleşmesi: HamOkuma ------------------------------------------------------


def _okuma(metin: str, yon) -> HamOkuma:
    return HamOkuma(sart_id="cadmium", alan="sinir", ham_metin=metin, konum={"sayfa": 5, "madde": "3.4"}, sinir_yonu=yon)


def test_ham_okumada_modelin_yonu_metinle_celisirse_yakalanir():
    assert okuma_yonu_dogrula(_okuma("≤ 1 ppm", "en_az")).durum == "celiski"
    assert okuma_yonu_dogrula(_okuma("≤ 1 ppm", "en_cok")).durum == "uyumlu"
    assert okuma_yonu_dogrula(_okuma("≤ 1 ppm", "belirsiz")).durum == "belirsiz"


def test_ham_okumada_yon_yoksa_denetlenmez():
    o = HamOkuma(sart_id="viscosity", alan="test_adi", ham_metin="Viscosity", konum={"sayfa": 7})
    assert okuma_yonu_dogrula(o).durum == "sayisal_degil"


# --- Yalnız dil modeli deneyine bağlı ------------------------------------------------


def test_belgeden_cikar_yon_celiskisini_belirsiz_yapar_ve_rapora_yazar():
    from deney.yalniz_dil_modeli import belgeden_cikar
    from malzeme_kabul.belge.pdf_okuyucu import Belge, Sayfa

    kadmiyum = {
        "id": "lead_cadmium_content", "test_adi": "Lead and cadmium content",
        "sinir": {"kriter_turu": "sayisal", "alt": 0.001, "ust_dahil": False, "birim": "ppm", "orijinal_metin": "≤ 1 ppm"},
        "kaynak": {"belge_no": "MIL-PRF-23377", "revizyon": "K", "madde": "3.4"}, "test_turleri": ["kabul"],
    }
    dogru = dict(kadmiyum, id="lead", sinir={"kriter_turu": "sayisal", "ust": 0.05, "birim": "percent",
                                              "orijinal_metin": "not more than 0.05 percent by weight"})

    class Istemci:
        def sohbet(self, mesajlar, sema):
            return json.dumps({"testler": [kadmiyum, dogru]})

    belge = Belge(dosya="sahte.pdf", sayfalar=[Sayfa(11, "3.4 Lead and cadmium content")])
    dokuman, rapor = belgeden_cikar(belge, "MIL-PRF-23377", "K", Istemci())

    testler = {t.id: t for t in dokuman.testler}
    assert testler["lead_cadmium_content"].sinir.yon == "belirsiz"
    assert testler["lead"].sinir.yon is None
    assert rapor.yon_celiskileri == [
        {"id": "lead_cadmium_content", "sayfa": 11, "metin_yonu": "en_cok", "model_yonu": "en_az",
         "orijinal_metin": "≤ 1 ppm"},
    ]
    json.dumps(rapor.sozluk())
