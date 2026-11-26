"""`kanit_dogrulama.deger_kaniti` ve `kanit_dogrulama.atif_kaniti` için birim testleri (retro H5, H6).

`deger_kaniti`: üst bilgi değeri (tedarikçi, lot, tarih...) belgenin herhangi
bir sayfasında sayı ve sözcük sınırıyla aranır. `atif_kaniti`: standart atfı
belgedeki atfın tamamı olmalıdır; ardından satır biter ya da üretim tarihi
alanı gelir.

Sayfalar düz metindir (PDF yok, dil modeli yok, ağ yok).
"""

from __future__ import annotations

import pytest

from malzeme_kabul.kural.kanit_dogrulama import KanitSonucu, atif_kaniti, deger_kaniti, okuma_kaniti, satir_kaniti
from malzeme_kabul.sozlesme.okuma import HamOkuma, SertifikaSatirOkumasi

UST = ("Kurgu Coatings Inc. (kurgusal)\n"
       "Certificate No T-12 Batch/Lot A94009\n"
       "Specification MIL-PRF-23377K Type II Class N Date of manufacture2026-08-21\n"
       "Cadmium content ASTM D3335 1 ppm max 0.1 ppm\n"
       "Low temperature -5 °C\n"
       "Drying time 5 minutes\n")
SAYFALAR = {1: UST}


def kanitli(sonuc: KanitSonucu) -> bool:
    assert isinstance(sonuc, KanitSonucu) and sonuc.neden
    return sonuc.kanitli


# --- deger_kaniti: sınırla eşleşme --------------------------------------------------------------


@pytest.mark.parametrize("deger", ["A94009", "T-12", "0.1 ppm", "Kurgu Coatings Inc. (kurgusal)", "-5 °C"])
def test_deger_kaniti_belgede_sinirla_gecen_degeri_kabul_eder(deger):
    assert kanitli(deger_kaniti(deger, SAYFALAR))


@pytest.mark.parametrize("deger", ["a94009", "  A94009 ", "kurgu   coatings inc. (KURGUSAL)"])
def test_deger_kaniti_bosluk_ve_harf_buyuklugu_farkini_yok_sayar(deger):
    assert kanitli(deger_kaniti(deger, SAYFALAR))


@pytest.mark.parametrize("deger, sayfa", [
    ("1 ppm", "max 0.1 ppm"),          # önünde ondalık ayırıcı
    ("A9400", "Batch/Lot A94009"),     # ardında rakam
    ("T-1", "Certificate No T-12"),    # ardında rakam
    ("5 °C", "Low temperature -5 °C"),  # önünde eksi işareti
    ("5 min", "Drying time 5 minutes"),  # ardında harf
    ("Kurgu", "Inc. (kurgusal)"),      # ardında harf
    ("Coatings", "Kurgu XCoatings"),   # önünde harf
])
def test_deger_kaniti_sayi_ve_sozcuk_sinirini_asan_parcayi_kabul_etmez(deger, sayfa):
    assert not kanitli(deger_kaniti(deger, {1: sayfa}))


@pytest.mark.parametrize("sayfa, beklenen", [
    ("limit 1", True),       # satır sonu sınırdır
    ("limit 1.", True),      # cümle sonu noktası sınırdır (ardında rakam yok)
    ("limit 1,", True),
    ("limit 1.5", False),    # ondalık kısım: başka sayı
    ("limit 1,5", False),    # virgüllü ondalık
    ("limit 10", False),
    ("limit 0.1", False),
    ("limit 21", False),
    ("limit <1", False),     # işaret anlamı değiştirir
    ("limit ±1", False),
])
def test_deger_kaniti_sayinin_tam_sinirini_hemen_alti_ve_ustunden_ayirir(sayfa, beklenen):
    assert kanitli(deger_kaniti("1", {1: sayfa})) is beklenen


def test_deger_kaniti_herhangi_bir_sayfada_bulunursa_kanitlidir():
    assert kanitli(deger_kaniti("A94009", {1: "Kurgu Coatings Inc.", 2: "Batch/Lot A94009"}))
    assert not kanitli(deger_kaniti("A94009", {1: "Kurgu Coatings Inc.", 2: "Batch/Lot A94008"}))


@pytest.mark.parametrize("deger", ["", "   "])
def test_deger_kaniti_bos_degeri_kanitsiz_sayar(deger):
    assert not kanitli(deger_kaniti(deger, SAYFALAR))


# --- deger_kaniti: etiketine yapışık tarih -----------------------------------------------------


def test_deger_kaniti_etiketine_yapisik_tarihi_bulur():
    # Metin katmanında etiket ile değer arasındaki boşluk kaybolabilir: "manufacture2026-08-21".
    assert kanitli(deger_kaniti("2026-08-21", SAYFALAR))


@pytest.mark.parametrize("deger", ["2026-08-2", "026-08-21", "2026-08-210", "2026-08-22"])
def test_deger_kaniti_yapisik_tarihin_parcasini_ya_da_komsusunu_kabul_etmez(deger):
    assert not kanitli(deger_kaniti(deger, SAYFALAR))


# --- atif_kaniti --------------------------------------------------------------------------------


@pytest.mark.parametrize("sayfa", [
    "Specification MIL-PRF-23377K Type II Class N",                                  # satır sonu
    "Specification MIL-PRF-23377K Type II Class N\nDate of manufacture 2026-08-21",
    "Specification MIL-PRF-23377K Type II Class N Date of manufacture 2026-08-21",  # aynı satırda tarih etiketi
    "Specification MIL-PRF-23377K Type II Class N Date of manufacture2026-08-21",   # etikete yapışık tarih
    "Şartname MIL-PRF-23377K Type II Class N Üretim tarihi 2026-08-21",             # Türkçe etiket
    "Şartname MIL-PRF-23377K Type II Class N Uretim tarihi: 2026-08-21",
])
def test_atif_kaniti_ardindan_satir_biten_ya_da_uretim_tarihi_gelen_tam_atfi_kabul_eder(sayfa):
    assert kanitli(atif_kaniti("MIL-PRF-23377K Type II Class N", {1: sayfa}))


def test_atif_kaniti_bosluk_ve_harf_buyuklugu_farkini_yok_sayar():
    assert kanitli(atif_kaniti("mil-prf-23377k  type ii class n", SAYFALAR))


@pytest.mark.parametrize("atif", [
    "MIL-PRF-23377K Type II Class",  # sınıf atılmış
    "MIL-PRF-23377K Type II",        # sınıf atılmış
    "MIL-PRF-23377K Type I",         # "Type II" içinde: sözcük sınırı
    "MIL-PRF-23377K",                # tip ve sınıf atılmış
    "MIL-PRF-23377",                 # revizyon da atılmış ("23377K" içinde: sözcük sınırı)
    "MIL-PRF-2337",                  # numara kısaltılmış
])
def test_atif_kaniti_belgedeki_atfin_bir_parcasini_kabul_etmez(atif):
    assert not kanitli(atif_kaniti(atif, SAYFALAR))


@pytest.mark.parametrize("sayfa", [
    "Specification MIL-PRF-23377K Type II Class N2",                      # ardında rakam: başka sınıf
    "Specification MIL-PRF-23377K Type II Class N supersedes revision J",  # ardında başka metin
    "Specification MIL-PRF-23377K Type II Class N, Batch A94009",
])
def test_atif_kaniti_ardindan_uretim_tarihi_disinda_metin_gelirse_kabul_etmez(sayfa):
    assert not kanitli(atif_kaniti("MIL-PRF-23377K Type II Class N", {1: sayfa}))


def test_atif_kaniti_satir_sonundan_sonraki_satira_tasmaz():
    # Atıf iki satıra bölünmüşse tam atıf olarak bir satırda yoktur.
    assert not kanitli(atif_kaniti("MIL-PRF-23377K Type II Class N",
                                   {1: "Specification MIL-PRF-23377K Type II\nClass N"}))


@pytest.mark.parametrize("atif", ["Supersedes: MIL-PRF-23377K Type II Class N", "Type II Class N", ""])
def test_atif_kaniti_standart_numarasiyla_baslamayan_atfi_kabul_etmez(atif):
    assert not kanitli(atif_kaniti(atif, SAYFALAR))


def test_atif_kaniti_belgede_olmayan_revizyonu_kabul_etmez():
    assert not kanitli(atif_kaniti("MIL-PRF-23377J Type II Class N", SAYFALAR))


def test_atif_kaniti_herhangi_bir_sayfada_bulunursa_kanitlidir():
    sayfalar = {1: "Kurgu Coatings Inc.", 2: "Specification MIL-PRF-23377K Type II Class N"}
    assert kanitli(atif_kaniti("MIL-PRF-23377K Type II Class N", sayfalar))


# =================================================================================================
# Hibrit hat gözden geçirme bulguları (Ö2, Ö3, K1-K3, K7).
# =================================================================================================

# --- Ö2: numara alanlarında alana özgü sınır -----------------------------------------------------
# Tasarım: deger_kaniti(deger, sayfalar, alan=...). Parti ve sertifika numarasında değerin önünde ve
# ardında harf, rakam ya da "-" olamaz; üretim tarihi etiketine yapışık olabilir ("manufacture2026-08-21").


@pytest.mark.parametrize("alan", ["parti_no", "sertifika_no"])
@pytest.mark.parametrize("deger, sayfa", [
    ("94009", "Batch/Lot A94009"),        # önünde harf
    ("94009", "Batch/Lot 94009B"),        # ardında harf
    ("A-2512-01", "Batch/Lot A-2512-01-2"),  # ardında "-"
    ("A-2512", "Batch/Lot A-2512-01"),
    ("2512-01", "Batch/Lot A-2512-01"),   # önünde "-"
])
def test_o2_numara_alaninda_baska_numaranin_parcasi_kanitsizdir(alan, deger, sayfa):
    assert not kanitli(deger_kaniti(deger, {1: sayfa}, alan=alan))


@pytest.mark.parametrize("alan", ["parti_no", "sertifika_no"])
@pytest.mark.parametrize("deger, sayfa", [
    ("A94009", "Batch/Lot A94009"),
    ("A-2512-01", "Batch/Lot A-2512-01, PO-1"),   # noktalama sınırdır
    ("A-2512-01", "Lot No: A-2512-01"),
    ("T-900", "Certificate No T-900\nBatch/Lot T900"),
])
def test_o2_numara_alaninda_tam_numara_kanitlidir(alan, deger, sayfa):
    assert kanitli(deger_kaniti(deger, {1: sayfa}, alan=alan))


def test_o2_uretim_tarihi_etiketine_yapisik_kalabilir():
    assert kanitli(deger_kaniti("2026-08-21", SAYFALAR, alan="uretim_tarihi"))
    assert not kanitli(deger_kaniti("2026-08-2", SAYFALAR, alan="uretim_tarihi"))


def test_o2_yapisik_tarih_kurali_numara_alanina_tasinmaz():
    # Aynı "harfe yapışık" yerleşim parti numarasında kanıt değildir.
    assert not kanitli(deger_kaniti("2026", {1: "Batch/LotA2026"}, alan="parti_no"))


# --- Ö3: atıf etiketleri kuralla atılır ------------------------------------------------------------


@pytest.mark.parametrize("atif, satir", [
    ("Şartname: MIL-PRF-23377K, Tip II, Sınıf N",
     "Standart Şartname: MIL-PRF-23377K, Tip II, Sınıf N Üretim tarihi 2026-03-21"),  # C şablonu
    ("Specification: MIL-PRF-23377K Type I Class N", "Specification: MIL-PRF-23377K Type I Class N"),
    ("Specification MIL-PRF-23377K Type I Class N", "Specification MIL-PRF-23377K Type I Class N"),
    ("Spec. MIL-PRF-23377K Type I Class N", "Spec. MIL-PRF-23377K Type I Class N Date of manufacture 2026-01-15"),
    ("Şartname: MIL-PRF-23377K, Tip II, Sınıf N", "Spec. MIL-PRF-23377K, Tip II, Sınıf N"),  # etiket farklı, atıf aynı
])
def test_o3_bilinen_etiketle_baslayan_atif_etiketi_atilarak_aranir(atif, satir):
    assert kanitli(atif_kaniti(atif, {1: satir}))


@pytest.mark.parametrize("atif", [
    "Şartname: MIL-PRF-23377K",            # etiket atılınca da parça atıftır
    "Şartname: MIL-PRF-23377K, Tip I",     # "Tip II" içinde
    "Specification: MIL-PRF-23377J, Tip II, Sınıf N",  # revizyon farklı
])
def test_o3_etiket_atildiktan_sonra_da_parca_atif_kanitsizdir(atif):
    assert not kanitli(atif_kaniti(atif, {1: "Standart Şartname: MIL-PRF-23377K, Tip II, Sınıf N Üretim tarihi 2026-03-21"}))


def test_o3_bilinmeyen_etiket_atilmaz():
    assert not kanitli(atif_kaniti("Supersedes: MIL-PRF-23377K Type I Class N",
                                   {1: "Supersedes: MIL-PRF-23377K Type I Class N"}))


# --- K1-K2, K7: satır kanıtında şart sözcükleri ve birim -------------------------------------------


def satir_okumasi(test_adi: str, sonuc: str, birim: str | None = None) -> SertifikaSatirOkumasi:
    return SertifikaSatirOkumasi(sayfa=1, test_adi=test_adi, sonuc_hucresi=sonuc, birim_hucresi=birim)


@pytest.mark.parametrize("satir, ad, sonuc, birim", [
    ("Fineness of grind ASTM D1210 5 min 6", "Fineness of grind", "5", "min"),  # "5 min" şarttır, sonuç 6
    ("Pot life ASTM D1200 70 min 47 s", "Pot life", "47", "min"),                # "min" şartın birimi, bitişik değil
])
def test_k1_sart_sozcugu_olan_birim_sonuca_bitisik_degilse_ya_da_sart_ise_kanitsizdir(satir, ad, sonuc, birim):
    assert not kanitli(satir_kaniti(satir_okumasi(ad, sonuc, birim), {1: satir}))


@pytest.mark.parametrize("satir, ad, sonuc, birim", [
    ("Fineness of grind ASTM D1210 5 min 6", "Fineness of grind", "6", None),
    ("Pot life ASTM D1200 70 min 47 s", "Pot life", "47", "s"),
    ("Pot life ASTM D1200 70 min max 47 min", "Pot life", "47", "min"),  # birim "min" sonuca bitişik
])
def test_k1_gercek_sonuc_kanitli_kalir(satir, ad, sonuc, birim):
    assert kanitli(satir_kaniti(satir_okumasi(ad, sonuc, birim), {1: satir}))


@pytest.mark.parametrize("satir, ad, sonuc, birim", [
    ("Fineness of grind ASTM D1210 min 5 6", "Fineness of grind", "5", None),
    ("Cadmium content ASTM D3335 Max 1 ppm 0.4 ppm", "Cadmium content", "1", "ppm"),
    ("Application 15 to 23 µm 20", "Application", "23", "µm"),
    ("Application 15 to 23 µm 20", "Application", "23", None),
    ("Application 15-23 µm 20 µm", "Application", "15-23", "µm"),   # aralık şarttır
    ("Viscosity ASTM D1200 NMT 40 s 33 s", "Viscosity", "40", "s"),
    ("Flexibility ASTM D6905 NLT 10 % 28 %", "Flexibility", "10", "%"),
    ("Viscosity ASTM D1200 nmt 40 s 33 s", "Viscosity", "40", "s"),   # harf büyüklüğü fark etmez
])
def test_k2_onunde_sart_sozcugu_olan_deger_kanitsizdir(satir, ad, sonuc, birim):
    assert not kanitli(satir_kaniti(satir_okumasi(ad, sonuc, birim), {1: satir}))


@pytest.mark.parametrize("satir, ad, sonuc, birim", [
    ("Fineness of grind ASTM D1210 min 5 6", "Fineness of grind", "6", None),
    ("Cadmium content ASTM D3335 Max 1 ppm 0.4 ppm", "Cadmium content", "0.4", "ppm"),
    ("Application 15 to 23 µm 20 µm", "Application", "20", "µm"),
    ("Application 15-23 µm 20 µm", "Application", "20", "µm"),
    ("Viscosity ASTM D1200 NMT 40 s 33 s", "Viscosity", "33", "s"),
    ("Flexibility ASTM D6905 NLT 10 % 28 %", "Flexibility", "28", "%"),
])
def test_k2_sart_sozcugunden_sonraki_gercek_sonuc_kanitlidir(satir, ad, sonuc, birim):
    assert kanitli(satir_kaniti(satir_okumasi(ad, sonuc, birim), {1: satir}))


def test_k7_bitisik_olmayan_birim_sutunu_kabul_edilir():
    # Birim sütunu sonuçtan önce gelebilir; birim satırda ve ardından şart sözcüğü yok.
    assert kanitli(satir_kaniti(satir_okumasi("Viscosity", "22", "s"), {1: "Viscosity s ASTM 22 40 max"}))


def test_k7_satir_sonunda_bolunen_hucre_sonraki_satirin_basina_tasabilir():
    sayfa = "Cadmium content ASTM D3335 1 ppm max ND (<0,5\nppm)\nDrying time ASTM D5895 5 hour max 2.6 h"
    # Sonuç hücresi "ND (<0,5 ppm)" iki satıra bölünmüş; eşleşme test adının satırında başlar.
    assert kanitli(satir_kaniti(satir_okumasi("Cadmium content", "ND (<0,5 ppm)"), {1: sayfa}))


def test_k7_bolunen_hucre_sonraki_satirin_ortasina_tasamaz():
    sayfa = "Cadmium content ASTM D3335 1 ppm max ND\nDrying time ASTM D5895 5 hour max 2.6 h"
    assert not kanitli(satir_kaniti(satir_okumasi("Cadmium content", "ND 2.6"), {1: sayfa}))


# --- K3: boş ya da yalnız boşluktan oluşan standart okuması ----------------------------------------


@pytest.mark.parametrize("ham", ["", "   ", "\n\t"])
def test_k3_bos_ya_da_yalniz_bosluk_ham_metin_kanitsizdir(ham):
    # Şema ham_metin'i boş bırakmaz; doğrulayıcı da şemaya güvenmeden reddetmelidir (model_copy şemayı atlar).
    okuma = HamOkuma(sart_id="cd", alan="sinir", ham_metin="1 ppm", konum={"sayfa": 1}).model_copy(
        update={"ham_metin": ham})
    assert not kanitli(okuma_kaniti(okuma, {1: "Cadmium content not greater than 1 ppm."}))


def test_k3_sema_yalniz_bosluk_ham_metni_kabul_etmez():
    with pytest.raises(ValueError):
        HamOkuma(sart_id="cd", alan="sinir", ham_metin="   ", konum={"sayfa": 1})
