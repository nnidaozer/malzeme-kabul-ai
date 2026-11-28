"""Sonuç ayrıştırma regresyonları: üslü yazım ve algılama sınırlı ND (Codex incelemesi).

- Üslü yazım ("1e-3", "1E3", "5e-3") kural katmanında sayı olarak çözülmez;
  "e-3" gibi kuyruk birim sanılırsa değer 1000 kat yanlış okunur. Bu yüzden
  hiçbir şartla (alt/üst, dar/geniş, birimli/birimsiz) "uygun" verilmez; karar
  insan incelemelidir.
- "ND (<0.5 ppm)" algılama sınırıyla okunur: gerçek değer 0.5 ppm'den küçüktür.
  Tam sınırdaki ND hiçbir zaman red sayılmaz (sınırı sağlar); uygun ya da,
  sınıra yakınlık bandı açıksa, insan incelemelidir. Algılama sınırı
  float'a kayıplı sığıyorsa ("0.50000000000000001") tam eşitlik istisnası
  geçmez, değer sınıra çok yakın sayılır: insan incelemeli.

Dil modeli kullanılmaz; yalnız kural motoru.
"""

from __future__ import annotations

import pytest

from malzeme_kabul.kural.karar_motoru import kontrol_et
from malzeme_kabul.sozlesme.sema import KabulDokumani
from malzeme_kabul.sozlesme.sertifika import Sertifika, SertifikaSatiri


def _sinir(alt=None, ust=None, birim="ppm", alt_dahil=True, ust_dahil=True):
    return {
        "kriter_turu": "sayisal", "alt": alt, "ust": ust, "birim": birim,
        "alt_dahil": alt_dahil, "ust_dahil": ust_dahil, "orijinal_metin": "metin",
    }


def _satir(sinir: dict, sonuc: str, birim: str | None):
    dokuman = KabulDokumani.model_validate({
        "standart": {"belge_no": "MIL-PRF-23377", "revizyon": "K"},
        "testler": [{
            "id": "kadmiyum", "test_adi": "Cadmium content", "sinir": sinir, "test_turleri": ["kabul"],
            "kaynak": {"belge_no": "MIL-PRF-23377", "revizyon": "K", "madde": "3.5.3"},
        }],
    })
    sertifika = Sertifika(
        sertifika_no="S-US", standart_atfi="MIL-PRF-23377K Type I Class C2",
        satirlar=[SertifikaSatiri(test_adi="Cadmium content", sonuc=sonuc, birim=birim)],
    )
    (satir,) = kontrol_et(dokuman, sertifika).satirlar
    return satir


# --- üslü yazım ----------------------------------------------------------------

USLU = ["1e-3", "1E3", "5e-3", "1e3", "5E-3", "1.0e-3", "1 e-3", "5e-3 ppm", "1E3 ppm"]
SARTLAR = {
    "en_cok_0_01": _sinir(ust=0.01),
    "en_cok_5": _sinir(ust=5.0),
    "en_cok_1000": _sinir(ust=1000.0),
    "en_cok_1e6": _sinir(ust=1e6),
    "en_az_0_001": _sinir(alt=0.001),
    "en_az_1": _sinir(alt=1.0),
    "aralik_0_1e6": _sinir(alt=0.0, ust=1e6),
    "tam_1": _sinir(alt=1.0, ust=1.0),
    "birimsiz_en_cok_1e6": _sinir(ust=1e6, birim=None),
    "birimsiz_aralik": _sinir(alt=0.0, ust=1e6, birim=None),
    "percent_en_cok_100": _sinir(ust=100.0, birim="percent"),
}


@pytest.mark.parametrize("birim", ["ppm", None])
@pytest.mark.parametrize("sart", list(SARTLAR))
@pytest.mark.parametrize("sonuc", USLU)
def test_uslu_yazimli_sonuc_hicbir_sartla_uygun_vermez_insan_incelemeli(sonuc, sart, birim):
    satir = _satir(SARTLAR[sart], sonuc, birim)
    assert satir.karar == "insan_incelemeli", (sonuc, sart, birim, satir.gerekce)


# --- ND ve algılama sınırı ----------------------------------------------------


def test_nd_algilama_siniri_en_cok_dahil_tam_sinirda_red_degil():
    satir = _satir(_sinir(ust=0.5, ust_dahil=True), "ND (<0.5 ppm)", "ppm")
    assert satir.karar in ("uygun", "insan_incelemeli"), satir.gerekce


def test_nd_algilama_siniri_birim_hucresi_bossa_da_tam_sinirda_red_degil():
    satir = _satir(_sinir(ust=0.5, ust_dahil=True), "ND (<0.5 ppm)", None)
    assert satir.karar in ("uygun", "insan_incelemeli"), satir.gerekce


def test_nd_algilama_siniri_en_cok_haric_tam_sinirda_red_degil():
    # "<0.5" gerçek değeri 0.5'ten küçük tutar; "0.5'ten küçük" şartını kesin sağlar.
    satir = _satir(_sinir(ust=0.5, ust_dahil=False), "ND (<0.5 ppm)", "ppm")
    assert satir.karar in ("uygun", "insan_incelemeli"), satir.gerekce


def test_nd_algilama_siniri_kayipli_yazimda_insan_incelemeli():
    satir = _satir(_sinir(ust=0.5, ust_dahil=True), "ND (<0.50000000000000001 ppm)", "ppm")
    assert satir.karar == "insan_incelemeli", satir.gerekce
    assert "sınıra çok yakın" in satir.gerekce


def test_nd_algilama_siniri_kayipli_yazimda_haric_sartta_da_insan_incelemeli():
    satir = _satir(_sinir(ust=0.5, ust_dahil=False), "ND (<0.50000000000000001 ppm)", "ppm")
    assert satir.karar == "insan_incelemeli", satir.gerekce


def test_nd_algilama_siniri_hemen_altinda_uygun():
    satir = _satir(_sinir(ust=0.5), "ND (<0.4 ppm)", "ppm")
    assert satir.karar == "uygun", satir.gerekce


def test_nd_algilama_siniri_sinirin_hemen_ustundeyse_uygun_sayilmaz():
    # "<0.6": gerçek değer 0.5'in altında da üstünde de olabilir.
    satir = _satir(_sinir(ust=0.5), "ND (<0.6 ppm)", "ppm")
    assert satir.karar == "insan_incelemeli", satir.gerekce


def test_nd_algilama_siniri_sinira_cok_yakin_ustte_uygun_sayilmaz():
    satir = _satir(_sinir(ust=0.5), "ND (<0.5000001 ppm)", "ppm")
    assert satir.karar == "insan_incelemeli", satir.gerekce


def test_nd_algilama_siniri_yuzdeyle_verilirse_ppm_ye_cevrilir_ve_altindaysa_uygun():
    # 0.00004 % = 0.4 ppm < 0.5 ppm
    satir = _satir(_sinir(ust=0.5), "ND (<0.00004 %)", None)
    assert satir.karar == "uygun", satir.gerekce


def test_nd_algilama_siniri_yuzdeden_cevrilince_tam_sinirdaysa_insan_incelemeli():
    # 0.00005 % = 0.5 ppm; birim dönüşümü yapılınca tam eşitlik de bant içindedir.
    satir = _satir(_sinir(ust=0.5), "ND (<0.00005 %)", None)
    assert satir.karar == "insan_incelemeli", satir.gerekce


def test_nd_algilama_siniri_tanimsiz_birimde_insan_incelemeli():
    satir = _satir(_sinir(ust=0.5), "ND (<400 ppb)", None)
    assert satir.karar == "insan_incelemeli", satir.gerekce


def test_nd_algilama_siniri_birim_hucresiyle_celisirse_insan_incelemeli():
    satir = _satir(_sinir(ust=0.5), "ND (<0.4 ppm)", "percent")
    assert satir.karar == "insan_incelemeli", satir.gerekce


def test_sinirsiz_nd_insan_incelemeli():
    satir = _satir(_sinir(ust=0.5), "ND", "ppm")
    assert satir.karar == "insan_incelemeli", satir.gerekce
