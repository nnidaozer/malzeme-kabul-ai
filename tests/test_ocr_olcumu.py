"""OCR ölçüm betiğinin testleri (deney/ocr_olcumu.py, docs/ocr.md "Ölçüm").

Sahte OCR motoru ve tmp_path'te üretilen küçük PDF'ler kullanılır; gerçek
standartlar ve test kümesi açılmaz. Geçici bir bolunme.yaml yazılır.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pdf_uretici import pdf_yaz

from deney.bolunme import bolunme_oku
from deney.ocr_olcumu import (
    kelime_hata_orani,
    kelimelere_bol,
    olcum_yap,
    sayi_olcumu,
    sayilari_bul,
)
from malzeme_kabul.belge.ocr import OcrKelime, OcrSonucu

KOK = Path(__file__).resolve().parents[1]

METIN_BELGE = "MIL-PRF-11111A"     # metin tabanlı, geliştirme
TARANMIS_BELGE = "MIL-S-22222B"    # taranmış (ocr_gerekli), geliştirme
TEST_BELGE = "MIL-PRF-33333C"      # test kümesi (kilitli)
KATMANLI_BELGE = "MIL-PRF-44444D"  # hazır OCR katmanlı, geliştirme

PDF_SATIRI = "3.6.3 Viscosity shall be 6,000 to 16,000 cP."
OCR_SATIRI = "3.6.3 Viscosity shall be 6,000 to 16 ,000 cP."  # OCR virgülden önce boşluk koymuş
EK_SATIR = "The admixed primer shall have a viscosity within limits."  # OCR doğru okumuş (9 kelime)

BOLUNME = f"""test_kumesi_acik: false
test_durumu: secildi
tohum: 1

gelistirme:
  - {METIN_BELGE}
  - {TARANMIS_BELGE}
  - {KATMANLI_BELGE}

yeni_standartlar:
  - {TEST_BELGE}

test:
  - {TEST_BELGE}

ocr_gerekli:
  - {TARANMIS_BELGE}
"""


# --- Kelimeler ve kelime hata oranı -----------------------------------------------


def test_kelimelere_bol_bosluklara_gore_boler():
    assert kelimelere_bol("  3.6.3 Viscosity.\n40\tseconds  ") == ["3.6.3", "Viscosity.", "40", "seconds"]


def test_kelimelere_bol_nfkc_normallestirir():
    assert kelimelere_bol("ﬁneness of grind") == ["fineness", "of", "grind"]  # ﬁ bağlacı
    assert kelimelere_bol("１００ cP") == ["100", "cP"]  # tam genişlikli rakam


def test_kelimelere_bol_bos_metinde_bos_liste():
    assert kelimelere_bol("") == []
    assert kelimelere_bol(" \n\t ") == []


def test_kelime_hata_orani_levenshtein_bolu_referans_uzunlugudur():
    # Bir değiştirme (b -> x) ve bir ekleme (d): 2 / 3.
    assert kelime_hata_orani(["a", "b", "c"], ["a", "x", "c", "d"]) == pytest.approx(2 / 3)


def test_ayni_kelimelerde_hata_orani_sifirdir():
    assert kelime_hata_orani(["a", "b"], ["a", "b"]) == 0.0


def test_silinen_kelime_hata_sayilir():
    assert kelime_hata_orani(["a", "b", "c", "d"], ["a", "d"]) == pytest.approx(0.5)


def test_hata_orani_birden_buyuk_olabilir():
    assert kelime_hata_orani(["a"], ["x", "y", "z"]) == pytest.approx(3.0)


def test_referans_ve_tahmin_bossa_hata_orani_sifirdir():
    assert kelime_hata_orani([], []) == 0.0


def test_referans_bos_tahmin_doluysa_hata_orani_birdir():
    assert kelime_hata_orani([], ["a", "b"]) == 1.0


def test_kelime_hata_orani_buyuk_kucuk_harfe_duyarlidir():
    assert kelime_hata_orani(["Viscosity"], ["viscosity"]) == pytest.approx(1.0)


# --- Sayılar ----------------------------------------------------------------------


def test_binlik_virgul_ve_ocr_boslugu_kaldirilir():
    assert sayilari_bul("6,000-16 ,000") == ["6000", "16000"]


def test_binlik_virgullu_sayi_tek_sayidir():
    assert sayilari_bul("not greater than 1,500 cP") == ["1500"]


def test_ondalik_sayilar_korunur():
    assert sayilari_bul("0.5 to 1.5") == ["0.5", "1.5"]


def test_madde_numarasi_tek_belirtectir():
    assert sayilari_bul("3.6.3") == ["3.6.3"]
    assert sayilari_bul("see 4.6.10 and 3.4") == ["4.6.10", "3.4"]


def test_tire_ile_ayrilan_aralik_iki_sayidir():
    assert sayilari_bul("Viscosity 100-500 poises") == ["100", "500"]


def test_sayi_yoksa_bos_liste():
    assert sayilari_bul("The odor shall not be objectionable.") == []


def test_sayi_olcumu_coklu_kume_kesisimiyle_hesaplanir():
    # Referansta iki "1" var, tahminde bir: kesişim {1, 2} = 2.
    sonuc = sayi_olcumu(["1", "1", "2"], ["1", "2", "3"])
    assert set(sonuc) == {"kesinlik", "duyarlilik", "f1"}
    assert sonuc["kesinlik"] == pytest.approx(2 / 3)
    assert sonuc["duyarlilik"] == pytest.approx(2 / 3)
    assert sonuc["f1"] == pytest.approx(2 / 3)


def test_sayi_olcumu_eksik_okumada_duyarlilik_duser():
    sonuc = sayi_olcumu(["16000", "16000"], ["16000"])
    assert sonuc["kesinlik"] == pytest.approx(1.0)
    assert sonuc["duyarlilik"] == pytest.approx(0.5)
    assert sonuc["f1"] == pytest.approx(2 / 3)


def test_bir_rakami_yanlis_okunan_sinir_eslesmez():
    sonuc = sayi_olcumu(["6000", "16000"], ["6000", "18000"])
    assert sonuc["kesinlik"] == pytest.approx(0.5)
    assert sonuc["duyarlilik"] == pytest.approx(0.5)


def test_ikisi_de_bossa_sayi_olcumu_tamdir():
    assert sayi_olcumu([], []) == {"kesinlik": 1.0, "duyarlilik": 1.0, "f1": 1.0}


def test_referans_bossa_kesinlik_ve_f1_sifirdir():
    sonuc = sayi_olcumu([], ["5"])
    assert sonuc["kesinlik"] == 0.0
    assert sonuc["f1"] == 0.0


def test_tahmin_bossa_duyarlilik_ve_f1_sifirdir():
    sonuc = sayi_olcumu(["5"], [])
    assert sonuc["duyarlilik"] == 0.0
    assert sonuc["f1"] == 0.0


# --- olcum_yap ----------------------------------------------------------------------


class SahteMotor:
    """PDF dosya adına göre sonuç döner; her çağrıyı (dosya adı, sayfa) olarak kaydeder."""

    dil, psm, dpi = "eng", 3, 300

    def __init__(self, sonuclar: dict[str, OcrSonucu]):
        self.sonuclar = sonuclar
        self.cagrilar: list[tuple[str, int]] = []

    def sayfa_oku(self, pdf_yolu: Path, sayfa_no: int) -> OcrSonucu:
        ad = Path(pdf_yolu).name
        self.cagrilar.append((ad, sayfa_no))
        return self.sonuclar[ad]

    def surum(self) -> str:
        return "5.3.4-sahte"


TARAMA_SONUCU = OcrSonucu("Lead content 1 ppm", (
    OcrKelime("Lead", 90.0), OcrKelime("content", 70.0), OcrKelime("1", 50.0), OcrKelime("ppm", 30.0),
))


@pytest.fixture
def bolunme_yolu(tmp_path) -> Path:
    yol = tmp_path / "bolunme.yaml"
    yol.write_text(BOLUNME, encoding="utf-8")
    b = bolunme_oku(yol)  # biçim geçerli olmalı
    assert b.test == [TEST_BELGE] and b.ocr_gerekli == [TARANMIS_BELGE]
    return yol


@pytest.fixture
def belgeler(tmp_path) -> list[tuple[str, Path]]:
    klasor = tmp_path / "pdfler"
    klasor.mkdir()
    return [
        (METIN_BELGE, pdf_yaz(klasor / f"{METIN_BELGE}.pdf", [{"metin": [PDF_SATIRI, EK_SATIR]}])),
        (TARANMIS_BELGE, pdf_yaz(klasor / f"{TARANMIS_BELGE}.pdf", [{"gorsel": True}, {"gorsel": True}])),
        (TEST_BELGE, pdf_yaz(klasor / f"{TEST_BELGE}.pdf", [{"gorsel": True}])),
    ]


@pytest.fixture
def motor() -> SahteMotor:
    return SahteMotor({
        f"{METIN_BELGE}.pdf": OcrSonucu(f"{OCR_SATIRI}\n{EK_SATIR}",
                                           tuple(OcrKelime(k, 90.0) for k in f"{OCR_SATIRI} {EK_SATIR}".split())),
        f"{TARANMIS_BELGE}.pdf": TARAMA_SONUCU,
        f"{TEST_BELGE}.pdf": TARAMA_SONUCU,
    })


def test_test_kumesindeki_belge_atlanir_ve_okunmaz(tmp_path, belgeler, motor, bolunme_yolu):
    rapor = olcum_yap(belgeler, motor, tmp_path / "cikti", bolunme_yolu)
    assert [a["belge"] for a in rapor["atlandi"]] == [TEST_BELGE]
    assert rapor["atlandi"][0]["neden"]
    assert all(ad != f"{TEST_BELGE}.pdf" for ad, _ in motor.cagrilar)
    satirlar = rapor["metin_tabanli"] + rapor["taranmis"]
    assert TEST_BELGE not in {s["belge"] for s in satirlar}


def test_bolunmede_olmayan_belge_atlanir(tmp_path, motor, bolunme_yolu):
    yol = pdf_yaz(tmp_path / "MIL-PRF-99999Z.pdf", [{"gorsel": True}])
    motor.sonuclar[yol.name] = TARAMA_SONUCU
    rapor = olcum_yap([("MIL-PRF-99999Z", yol)], motor, tmp_path / "cikti", bolunme_yolu)
    assert [a["belge"] for a in rapor["atlandi"]] == ["MIL-PRF-99999Z"]
    assert motor.cagrilar == []


def test_metin_ve_taranmis_belgeler_ayri_raporlanir(tmp_path, belgeler, motor, bolunme_yolu):
    rapor = olcum_yap(belgeler, motor, tmp_path / "cikti", bolunme_yolu)
    assert {"metin_tabanli", "taranmis", "atlandi", "motor"} <= set(rapor)
    assert [s["belge"] for s in rapor["metin_tabanli"]] == [METIN_BELGE]
    assert [s["belge"] for s in rapor["taranmis"]] == [TARANMIS_BELGE]
    assert isinstance(rapor["motor"], dict)


def test_metin_belgesi_sayfa_sayfa_ocrdan_gecer_ve_pdf_metniyle_karsilastirilir(tmp_path, belgeler, motor,
                                                                               bolunme_yolu):
    rapor = olcum_yap(belgeler, motor, tmp_path / "cikti", bolunme_yolu)
    assert (f"{METIN_BELGE}.pdf", 1) in motor.cagrilar
    (satir,) = rapor["metin_tabanli"]
    assert satir["sayfa_sayisi"] == 1
    # "16,000" -> "16" ",000": bir değiştirme + bir ekleme, referans 8 + 9 = 17 kelime.
    assert satir["wer"] == pytest.approx(2 / 17)
    # Sayı ölçümü OCR'ın koyduğu boşluklu virgülü tolere eder: 3.6.3, 6000, 16000 hepsi doğru.
    assert satir["sayi_f1"] == pytest.approx(1.0)
    assert satir["sure_s_sayfa_basi"] >= 0


def test_taranmis_belgede_guven_ve_dusuk_guvenli_oran_olculur(tmp_path, belgeler, motor, bolunme_yolu):
    rapor = olcum_yap(belgeler, motor, tmp_path / "cikti", bolunme_yolu)
    assert sorted(no for ad, no in motor.cagrilar if ad == f"{TARANMIS_BELGE}.pdf") == [1, 2]
    (satir,) = rapor["taranmis"]
    assert satir["sayfa_sayisi"] == 2
    assert satir["ortalama_guven"] == pytest.approx(60.0)       # (90+70+50+30)/4, iki sayfa aynı
    assert satir["dusuk_guvenli_oran"] == pytest.approx(0.5)    # 50 ve 30 eşiğin (60) altında
    assert satir["sure_s_sayfa_basi"] >= 0
    assert "wer" not in satir  # taranmış belgenin doğru metni yok


def test_hazir_ocr_katmanli_belge_taranmis_grubunda_olculur(tmp_path, motor, bolunme_yolu):
    yol = pdf_yaz(tmp_path / f"{KATMANLI_BELGE}.pdf",
                  [{"gorsel": True, "metin": [PDF_SATIRI, PDF_SATIRI, PDF_SATIRI]}])
    motor.sonuclar[yol.name] = TARAMA_SONUCU
    rapor = olcum_yap([(KATMANLI_BELGE, yol)], motor, tmp_path / "cikti", bolunme_yolu)
    assert [s["belge"] for s in rapor["taranmis"]] == [KATMANLI_BELGE]
    assert rapor["metin_tabanli"] == []


def test_markdown_raporu_ve_sayfa_csvsi_yazilir(tmp_path, belgeler, motor, bolunme_yolu):
    cikti = tmp_path / "cikti"
    olcum_yap(belgeler, motor, cikti, bolunme_yolu)
    md = (cikti / "ocr_olcumu.md").read_text(encoding="utf-8")
    assert "Metin tabanlı" in md and "Taranmış" in md
    assert md.index("Metin tabanlı") != md.index("Taranmış")
    assert METIN_BELGE in md and TARANMIS_BELGE in md
    with open(cikti / "sayfalar.csv", encoding="utf-8", newline="") as f:
        satirlar = list(csv.DictReader(f))
    assert len(satirlar) == 3  # metin belgesinin 1, taranmış belgenin 2 sayfası; test belgesi yok
    degerler = [" ".join(s.values()) for s in satirlar]
    assert sum(METIN_BELGE in d for d in degerler) == 1
    assert sum(TARANMIS_BELGE in d for d in degerler) == 2
    assert not any(TEST_BELGE in d for d in degerler)


def test_cikti_data_gold_altindaysa_reddedilir_ve_hicbir_sey_yazilmaz(belgeler, motor, bolunme_yolu):
    hedef = KOK / "data" / "gold" / "ocr_olcumu_deneme"
    with pytest.raises(ValueError):
        olcum_yap(belgeler, motor, hedef, bolunme_yolu)
    assert not hedef.exists()
    assert motor.cagrilar == []


# --- Komut satırı ve varsayılan belge listesi -----------------------------------------


def test_main_tesseract_yoksa_2_doner_ve_hicbir_sey_yazmaz(tmp_path, monkeypatch, capsys):
    from deney.ocr_olcumu import main

    bos = tmp_path / "bos_path"
    bos.mkdir()
    monkeypatch.setenv("PATH", str(bos))  # tesseract bulunamaz
    cikti = tmp_path / "cikti"
    assert main(["--cikti", str(cikti), "--belge", "MIL-PRF-23377K"]) == 2
    assert "tesseract" in capsys.readouterr().err.lower()
    assert not cikti.exists()


def test_varsayilan_belgeler_test_kumesinden_belge_icermez():
    from deney.ocr_olcumu import varsayilan_belgeler

    b = bolunme_oku()  # gerçek data/bolunme.yaml
    belgeler = varsayilan_belgeler()
    etiketler = [etiket for etiket, _ in belgeler]
    assert etiketler  # liste boş değil
    assert "MIL-A-46146B" not in etiketler
    assert not set(etiketler) & set(b.test)
    for etiket, yol in belgeler:
        assert b.kume(etiket) == "gelistirme", etiket
        assert not b.yol_kilitli_mi(yol), yol  # gerçek havacılık klasörü de yok
        assert "MIL-A-46146B" not in str(yol)


# --- Gözden geçirme düzeltmeleri ------------------------------------------------------------


@pytest.mark.parametrize(
    "metin, beklenen",
    [
        ("-40 °C", ["-40"]),
        ("−65", ["-65"]),                      # U+2212 eksi işareti
        ("100-500", ["100", "500"]),           # önünde rakam var: tire aralıktır
        ("range -54 to +93", ["-54", "93"]),   # artı işareti atılır
        ("16, 000", ["16000"]),                # virgülden sonra boşluk
        ("6,000-16 ,000", ["6000", "16000"]),  # mevcut davranış korunur
        ("from -65 to -40", ["-65", "-40"]),
    ],
    ids=["eksi_tire", "eksi_u2212", "aralik", "eksi_arti", "virgulden_sonra_bosluk", "bosluklu_virgul",
         "iki_eksi"],
)
def test_sayilari_bul_eksi_isaretini_ve_virgul_boslugunu_tanir(metin, beklenen):
    assert sayilari_bul(metin) == beklenen


def test_karsilastirma_metni_glif_kodunu_ve_filigrani_duser():
    from deney.ocr_olcumu import karsilastirma_metni

    metin = ("Downloaded from http://www.everyspec.com on 2012-02-21\n"
             "3.6.3 Temperature 49 (cid:114)3(cid:113) C\n"
             "MIL-PRF-23377K")
    sonuc = karsilastirma_metni(metin)
    assert "(cid:" not in sonuc
    assert "Downloaded from" not in sonuc and "everyspec" not in sonuc
    assert "49 ±3° C" in sonuc
    assert "MIL-PRF-23377K" in sonuc


def test_wer_ve_sayi_olcumu_filigrani_saymaz(tmp_path, motor, bolunme_yolu):
    # PDF'te EverySpec filigranı var, OCR çıktısında yok: normalleştirmeden sonra fark yok.
    yol = pdf_yaz(tmp_path / f"{METIN_BELGE}.pdf",
                  [{"metin": ["Downloaded from http://www.everyspec.com on 2012-02-21", PDF_SATIRI, EK_SATIR]}])
    motor.sonuclar[yol.name] = OcrSonucu(f"{PDF_SATIRI}\n{EK_SATIR}",
                                         tuple(OcrKelime(k, 90.0) for k in f"{PDF_SATIRI} {EK_SATIR}".split()))
    rapor = olcum_yap([(METIN_BELGE, yol)], motor, tmp_path / "cikti", bolunme_yolu)
    (satir,) = rapor["metin_tabanli"]
    assert satir["wer"] == pytest.approx(0.0)
    assert satir["sayi_f1"] == pytest.approx(1.0)


def test_kilitli_klasordeki_belge_atlanir_ve_motor_cagrilmaz(tmp_path, motor):
    bolunme = tmp_path / "bolunme_kilitli.yaml"
    bolunme.write_text(BOLUNME + "\nkilitli_klasorler:\n  - kilitli_klasor\n", encoding="utf-8")
    klasor = tmp_path / "kilitli_klasor"
    klasor.mkdir()
    yol = pdf_yaz(klasor / f"{METIN_BELGE}.pdf", [{"metin": [PDF_SATIRI, EK_SATIR]}])  # etiket geliştirmede
    motor.sonuclar[yol.name] = TARAMA_SONUCU
    rapor = olcum_yap([(METIN_BELGE, yol)], motor, tmp_path / "cikti", bolunme)
    assert [a["belge"] for a in rapor["atlandi"]] == [METIN_BELGE]
    assert rapor["metin_tabanli"] == [] and rapor["taranmis"] == []
    assert motor.cagrilar == []


def test_markdown_alan_f1_bolumunde_tablo_sinirliligi_yazar(tmp_path, belgeler, motor, bolunme_yolu):
    cikti = tmp_path / "cikti"
    olcum_yap(belgeler, motor, cikti, bolunme_yolu)
    md = (cikti / "ocr_olcumu.md").read_text(encoding="utf-8")
    assert "OCR sayfalarında tablo okunmaz" in md
    assert md.index("Alan F1") < md.index("OCR sayfalarında tablo okunmaz") < md.index("## Taranmış")


# --- İkinci gözden geçirme turu -------------------------------------------------------------

TABLO_II = [["Requirement", "Req para", "Test method", "Test para"],
            ["Viscosity", "3.6.3", "4.6.3", "ASTM D1200"],
            ["Lead content", "3.6.9", "4.6.9", "ASTM D3335"]]


def _iki_testli_sayfalar(etiket: str, gorsel: bool = False) -> list[dict]:
    """Kural çıkarıcının viscosity ve lead_content bulduğu iki sayfa (TABLE II'li)."""
    return [
        {"gorsel": gorsel, "metin": [etiket, "3.6.3 Viscosity. The maximum viscosity shall be",
                                     "40 seconds through a cup.",
                                     "3.6.9 Lead content. The lead content shall be not greater than 1 ppm."]},
        {"gorsel": gorsel, "metin": [etiket, "TABLE II. Tests"], "tablo": TABLO_II},
    ]


class SayfaSayfaMotor:
    """Her sayfa için PDF'in kendi metnini (hazır katman ya da metin) döner: OCR kusursuz."""

    dil, psm, dpi = "eng", 3, 300

    def __init__(self):
        self.cagrilar: list[tuple[str, int]] = []

    def sayfa_oku(self, pdf_yolu, sayfa_no):
        from malzeme_kabul.belge.pdf_okuyucu import pdf_oku

        self.cagrilar.append((Path(pdf_yolu).name, sayfa_no))
        metin = pdf_oku(pdf_yolu).sayfalar[sayfa_no - 1].metin
        return OcrSonucu(metin, tuple(OcrKelime(k, 90.0) for k in metin.split()))

    def surum(self):
        return "5.3.4-sahte"


def test_katman_uyumu_ve_katman_kural_sayisi_olculur(tmp_path, bolunme_yolu):
    yol = pdf_yaz(tmp_path / f"{KATMANLI_BELGE}.pdf", _iki_testli_sayfalar(KATMANLI_BELGE, gorsel=True))
    rapor = olcum_yap([(KATMANLI_BELGE, yol)], SayfaSayfaMotor(), tmp_path / "cikti", bolunme_yolu)
    (satir,) = rapor["taranmis"]
    assert satir["tur"] == "ocr_katmanlı"
    assert satir["katman_uyumu_wer"] == pytest.approx(0.0)  # OCR katmanla aynı metni okudu
    assert satir["kural_test_sayisi_katman"] == 2
    assert isinstance(satir["kural_test_sayisi_ocr"], int)


def test_metin_belgesinde_kural_sayisi_pdf_metninden_olculur(tmp_path, bolunme_yolu):
    yol = pdf_yaz(tmp_path / f"{METIN_BELGE}.pdf", _iki_testli_sayfalar(METIN_BELGE))
    rapor = olcum_yap([(METIN_BELGE, yol)], SayfaSayfaMotor(), tmp_path / "cikti", bolunme_yolu)
    (satir,) = rapor["metin_tabanli"]
    assert satir["wer"] == pytest.approx(0.0)
    assert satir["kural_test_sayisi_pdf"] == 2
    assert satir["alan_f1_pdf_metnine_gore"] is not None
    assert 0.0 <= satir["alan_f1_pdf_metnine_gore"] <= 1.0


def test_ayni_kural_ciktisinda_alan_f1_birdir(tmp_path, bolunme_yolu, monkeypatch):
    import malzeme_kabul.cikarim.kural_cikarici as kural_cikarici

    yol = pdf_yaz(tmp_path / f"{METIN_BELGE}.pdf", _iki_testli_sayfalar(METIN_BELGE))
    sabit = kural_cikarici.cikar(yol, "MIL-PRF-11111", "A")
    assert len(sabit.testler) == 2
    monkeypatch.setattr(kural_cikarici, "cikar", lambda *a, **k: sabit)
    rapor = olcum_yap([(METIN_BELGE, yol)], SayfaSayfaMotor(), tmp_path / "cikti", bolunme_yolu)
    (satir,) = rapor["metin_tabanli"]
    assert satir["alan_f1_pdf_metnine_gore"] == pytest.approx(1.0)
    assert satir["kural_test_sayisi_pdf"] == satir["kural_test_sayisi_ocr"] == 2


def test_kural_cikarici_hatasi_satira_yazilir_olcum_surer(tmp_path, belgeler, motor, bolunme_yolu, monkeypatch):
    import malzeme_kabul.cikarim.kural_cikarici as kural_cikarici

    def bozuk(*a, **k):
        raise RuntimeError("bozuk cikarici 4711")

    monkeypatch.setattr(kural_cikarici, "cikar", bozuk)
    rapor = olcum_yap(belgeler, motor, tmp_path / "cikti", bolunme_yolu)
    (metin,) = rapor["metin_tabanli"]
    (tarama,) = rapor["taranmis"]
    assert "bozuk cikarici 4711" in metin["kural_hatasi"]
    assert "bozuk cikarici 4711" in tarama["kural_hatasi"]
    assert metin["wer"] == pytest.approx(2 / 17)  # OCR ölçümü sürdü
    assert tarama["ortalama_guven"] == pytest.approx(60.0)
    assert (tmp_path / "cikti" / "ocr_olcumu.md").is_file()


def test_kural_cikarici_basariliysa_kural_hatasi_yoktur(tmp_path, bolunme_yolu):
    yol = pdf_yaz(tmp_path / f"{METIN_BELGE}.pdf", _iki_testli_sayfalar(METIN_BELGE))
    rapor = olcum_yap([(METIN_BELGE, yol)], SayfaSayfaMotor(), tmp_path / "cikti", bolunme_yolu)
    assert not rapor["metin_tabanli"][0].get("kural_hatasi")


class _SurumsuzMotor(SahteMotor):
    def surum(self):
        from malzeme_kabul.belge.ocr import OcrKullanilamaz

        raise OcrKullanilamaz("tesseract bulunamadı")


def test_surum_okunamazsa_motor_bilgisinde_none_ve_raporda_bilinmiyor(tmp_path, belgeler, motor, bolunme_yolu):
    surumsuz = _SurumsuzMotor(motor.sonuclar)
    rapor = olcum_yap(belgeler, surumsuz, tmp_path / "cikti", bolunme_yolu)
    assert rapor["motor"]["surum"] is None
    assert rapor["motor"]["dpi"] == 300
    assert "bilinmiyor" in (tmp_path / "cikti" / "ocr_olcumu.md").read_text(encoding="utf-8")


def test_surum_metodu_olmayan_motorda_surum_none(tmp_path, bolunme_yolu):
    class Yalin:
        def sayfa_oku(self, pdf_yolu, sayfa_no):
            return TARAMA_SONUCU

    yol = pdf_yaz(tmp_path / f"{TARANMIS_BELGE}.pdf", [{"gorsel": True}])
    rapor = olcum_yap([(TARANMIS_BELGE, yol)], Yalin(), tmp_path / "cikti", bolunme_yolu)
    assert rapor["motor"]["surum"] is None


@pytest.fixture
def ham_klasor(tmp_path) -> Path:
    kok = tmp_path / "ham"
    kok.mkdir()
    pdf_yaz(kok / f"{TEST_BELGE}.pdf", [{"metin": ["3.1 Test kumesi belgesi otuz uc bin uc yuz otuz uc."]}])
    return kok


def test_test_belgesinin_adsiz_kopyasi_atlanir_motor_cagrilmaz(tmp_path, motor, bolunme_yolu, ham_klasor):
    import shutil

    kopya = tmp_path / "girdi" / "x.pdf"
    kopya.parent.mkdir()
    shutil.copyfile(ham_klasor / f"{TEST_BELGE}.pdf", kopya)
    motor.sonuclar[kopya.name] = TARAMA_SONUCU
    rapor = olcum_yap([(METIN_BELGE, kopya)], motor, tmp_path / "cikti", bolunme_yolu, ham_klasor=ham_klasor)
    assert [a["belge"] for a in rapor["atlandi"]] == [METIN_BELGE]
    assert rapor["metin_tabanli"] == [] and rapor["taranmis"] == []
    assert motor.cagrilar == []


def test_adsiz_yeni_belge_verilen_etiketle_olculur(tmp_path, motor, bolunme_yolu, ham_klasor):
    yol = tmp_path / "girdi" / "x.pdf"
    yol.parent.mkdir()
    pdf_yaz(yol, [{"metin": [PDF_SATIRI, EK_SATIR]}])
    motor.sonuclar[yol.name] = motor.sonuclar[f"{METIN_BELGE}.pdf"]
    rapor = olcum_yap([(METIN_BELGE, yol)], motor, tmp_path / "cikti", bolunme_yolu, ham_klasor=ham_klasor)
    assert [s["belge"] for s in rapor["metin_tabanli"]] == [METIN_BELGE]


def test_main_ham_klasor_secenegini_kabul_eder(tmp_path, monkeypatch, ham_klasor):
    from deney.ocr_olcumu import main

    bos = tmp_path / "bos_path"
    bos.mkdir()
    monkeypatch.setenv("PATH", str(bos))  # tesseract yok: argümanlar çözüldükten sonra 2
    cikti = tmp_path / "cikti"
    assert main(["--cikti", str(cikti), "--ham-klasor", str(ham_klasor)]) == 2
    assert not cikti.exists()
