"""pdf_oku'nun OCR motoruyla çalışması (docs/ocr.md, tasarım 2).

Sahte motor kullanılır; tesseract gerekmez. Yalnız taranmış ya da hazır OCR
katmanlı sayfalar motora gider; metin sayfaları ve boş sayfalar gitmez.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pdf_uretici import pdf_yaz

from malzeme_kabul.belge.ocr import OcrKelime, OcrSonucu
from malzeme_kabul.belge.pdf_okuyucu import (
    KAYNAK_METIN,
    KAYNAK_OCR,
    PdfSiniri,
    PdfSiniriAsildi,
    Sayfa,
    pdf_oku,
)

UZUN = "3.4.2 Viscosity. The admixed primer shall have a viscosity within limits."
OCR_METNI = "3.6.3 Viscosity. The maximum viscosity\nshall be 40 seconds."
SAHTE_SONUC = OcrSonucu(
    metin=OCR_METNI,
    kelimeler=(OcrKelime("3.6.3", 95.0), OcrKelime("Viscosity.", 85.0), OcrKelime("40", 45.0)),
)
SAHTE_ORTALAMA = (95.0 + 85.0 + 45.0) / 3


class SahteMotor:
    """sayfa_oku çağrılarını kaydeder, her sayfa için aynı sonucu döner."""

    def __init__(self, sonuc: OcrSonucu = SAHTE_SONUC, saat: list[float] | None = None, adim: float = 0.0):
        self.sonuc = sonuc
        self.cagrilar: list[tuple[Path, int]] = []
        self._saat = saat
        self._adim = adim

    def sayfa_oku(self, pdf_yolu: Path, sayfa_no: int) -> OcrSonucu:
        self.cagrilar.append((Path(pdf_yolu), sayfa_no))
        if self._saat is not None:
            self._saat[0] += self._adim  # OCR zaman alır
        return self.sonuc


@pytest.fixture
def metin_pdf(tmp_path):
    return pdf_yaz(tmp_path / "metin.pdf", [{"metin": [UZUN, UZUN]}, {"metin": [UZUN]}])


@pytest.fixture
def karma_pdf(tmp_path):
    """1. sayfa metin, 2. sayfa yalnız resim (taranmış), 3. sayfa metin."""
    return pdf_yaz(tmp_path / "karma.pdf", [{"metin": [UZUN, UZUN]}, {"gorsel": True}, {"metin": [UZUN]}])


def test_kaynak_sabitleri():
    assert KAYNAK_METIN == "metin"
    assert KAYNAK_OCR == "ocr"


def test_sayfa_varsayilan_kaynagi_metin_ve_guveni_yok():
    sayfa = Sayfa(no=1, metin="a")
    assert sayfa.kaynak == KAYNAK_METIN
    assert sayfa.ocr_guveni is None


def test_metin_pdfinde_motor_hic_cagrilmaz(metin_pdf):
    motor = SahteMotor()
    belge = pdf_oku(metin_pdf, ocr=motor)
    assert motor.cagrilar == []
    assert [s.kaynak for s in belge.sayfalar] == [KAYNAK_METIN, KAYNAK_METIN]
    assert all(s.ocr_guveni is None for s in belge.sayfalar)
    assert belge.ocr_sayfalari == []


def test_karma_pdfte_motor_yalniz_resim_sayfasi_icin_cagrilir(karma_pdf):
    motor = SahteMotor()
    pdf_oku(karma_pdf, ocr=motor)
    assert [no for _, no in motor.cagrilar] == [2]  # sayfa numarası 1'den başlar
    assert motor.cagrilar[0][0].resolve() == karma_pdf.resolve()


def test_resim_sayfasi_ocr_metni_ve_guveniyle_gelir(karma_pdf):
    sayfa = pdf_oku(karma_pdf, ocr=SahteMotor()).sayfalar[1]
    assert sayfa.no == 2
    assert sayfa.metin == OCR_METNI
    assert sayfa.kaynak == KAYNAK_OCR
    assert sayfa.ocr_guveni == pytest.approx(SAHTE_ORTALAMA)
    assert sayfa.tablolar == []


def test_karma_pdfte_metin_sayfalari_ocrdan_etkilenmez(karma_pdf):
    ocrsuz = pdf_oku(karma_pdf)
    ocrlu = pdf_oku(karma_pdf, ocr=SahteMotor())
    for i in (0, 2):
        assert ocrlu.sayfalar[i].metin == ocrsuz.sayfalar[i].metin
        assert ocrlu.sayfalar[i].tablolar == ocrsuz.sayfalar[i].tablolar
        assert ocrlu.sayfalar[i].kaynak == KAYNAK_METIN
        assert ocrlu.sayfalar[i].ocr_guveni is None


def test_ocr_sayfalari_ocrdan_gecen_sayfa_numaralaridir(karma_pdf):
    assert pdf_oku(karma_pdf, ocr=SahteMotor()).ocr_sayfalari == [2]


def test_ocr_satirlari_kaynak_sayfa_numarasiyla_gelir(karma_pdf):
    satirlar = pdf_oku(karma_pdf, ocr=SahteMotor()).satirlar()
    assert (2, "3.6.3 Viscosity. The maximum viscosity") in satirlar
    assert (2, "shall be 40 seconds.") in satirlar


def test_hazir_ocr_katmanli_sayfa_yeniden_ocrdan_gecer(tmp_path):
    # Resmin üstünde görünmez metin katmanı (eski tarama); katmanın kalitesi bilinmez.
    yol = pdf_yaz(tmp_path / "katman.pdf", [{"gorsel": True, "metin": [UZUN, UZUN]}])
    motor = SahteMotor()
    sayfa = pdf_oku(yol, ocr=motor).sayfalar[0]
    assert [no for _, no in motor.cagrilar] == [1]
    assert sayfa.metin == OCR_METNI and sayfa.kaynak == KAYNAK_OCR


def test_bos_sayfa_ocrdan_gecmez(tmp_path):
    yol = pdf_yaz(tmp_path / "bos.pdf", [{"metin": [UZUN]}, {"metin": ["7"]}])  # 2. sayfa: yalnız sayfa no
    motor = SahteMotor()
    belge = pdf_oku(yol, ocr=motor)
    assert motor.cagrilar == []
    assert belge.ocr_sayfalari == []


def test_ocr_verilmezse_resim_sayfasi_eskisi_gibi_bos_metin_doner(karma_pdf):
    belge = pdf_oku(karma_pdf)
    sayfa = belge.sayfalar[1]
    assert sayfa.metin == ""
    assert sayfa.kaynak == KAYNAK_METIN
    assert sayfa.ocr_guveni is None
    assert belge.ocr_sayfalari == []


def test_ocr_sayfasinda_kelime_yoksa_guven_none(tmp_path):
    yol = pdf_yaz(tmp_path / "t.pdf", [{"gorsel": True}])
    sayfa = pdf_oku(yol, ocr=SahteMotor(OcrSonucu("", ()))).sayfalar[0]
    assert sayfa.kaynak == KAYNAK_OCR
    assert sayfa.metin == ""
    assert sayfa.ocr_guveni is None


def test_ocr_sayfalarinda_da_sure_siniri_denetlenir(tmp_path):
    yol = pdf_yaz(tmp_path / "tarama.pdf", [{"gorsel": True}, {"gorsel": True}, {"gorsel": True}])
    saat = [0.0]
    motor = SahteMotor(saat=saat, adim=20.0)  # her OCR sayfası 20 s sürer
    # OCR sayfa başı ek bütçe 1 s: bütçe en çok 30 + 3 * 1 = 33 s.
    with pytest.raises(PdfSiniriAsildi, match="süre"):
        pdf_oku(yol, sinirlar=PdfSiniri(en_cok_sure_s=30, ocr_sayfa_basi_s=1), saat=lambda: saat[0], ocr=motor)
    assert len(motor.cagrilar) == 2  # 2. sayfadan sonra 40 s > 33 s: 3. sayfa okunmaz


def test_ocr_sure_siniri_icinde_kalinca_okuma_tamamlanir(tmp_path):
    yol = pdf_yaz(tmp_path / "tarama.pdf", [{"gorsel": True}, {"gorsel": True}])
    saat = [0.0]
    motor = SahteMotor(saat=saat, adim=15.0)  # 2 x 15 s = 30 s
    # Bütçe 20 + 2 x 5 = 30 s: toplam süre bütçeye tam eşit, sınır aşılmaz.
    belge = pdf_oku(yol, sinirlar=PdfSiniri(en_cok_sure_s=20, ocr_sayfa_basi_s=5), saat=lambda: saat[0], ocr=motor)
    assert belge.ocr_sayfalari == [1, 2]


def test_ocr_sure_butcesi_hemen_asilinca_iki_sayfada_durur(tmp_path):
    yol = pdf_yaz(tmp_path / "tarama.pdf", [{"gorsel": True}, {"gorsel": True}])
    saat = [0.0]
    motor = SahteMotor(saat=saat, adim=15.0)  # 2 x 15 s = 30 s
    # Bütçe 20 + 2 x 4.99 = 29.98 s < 30 s.
    with pytest.raises(PdfSiniriAsildi, match="süre"):
        pdf_oku(yol, sinirlar=PdfSiniri(en_cok_sure_s=20, ocr_sayfa_basi_s=4.99), saat=lambda: saat[0], ocr=motor)


# --- OCR süre bütçesi (PdfSiniri.ocr_sayfa_basi_s) ---------------------------------------


def test_ocr_sayfa_basi_varsayilani_30_saniyedir():
    assert PdfSiniri().ocr_sayfa_basi_s == 30.0


@pytest.mark.parametrize("deger", [0, -1.0])
def test_ocr_sayfa_basi_pozitif_olmali(deger):
    with pytest.raises(ValueError):
        PdfSiniri(ocr_sayfa_basi_s=deger)


def _uc_tarama(tmp_path):
    return pdf_yaz(tmp_path / "tarama.pdf", [{"gorsel": True}, {"gorsel": True}, {"gorsel": True}])


def test_ocr_sayfalari_sure_butcesini_buyutur_tam_sinirda_okunur(tmp_path):
    # 3 OCR sayfası x 20 s = 60 s; bütçe 30 + 3 x 10 = 60 s (tam sınır, aşılmaz).
    saat = [0.0]
    motor = SahteMotor(saat=saat, adim=20.0)
    belge = pdf_oku(_uc_tarama(tmp_path), sinirlar=PdfSiniri(en_cok_sure_s=30, ocr_sayfa_basi_s=10),
                    saat=lambda: saat[0], ocr=motor)
    assert belge.ocr_sayfalari == [1, 2, 3]


def test_ocr_butcesi_hemen_asilinca_okuma_durur(tmp_path):
    # Bütçe 30 + 3 x 9.99 = 59.97 s < 60 s.
    saat = [0.0]
    motor = SahteMotor(saat=saat, adim=20.0)
    with pytest.raises(PdfSiniriAsildi, match="süre"):
        pdf_oku(_uc_tarama(tmp_path), sinirlar=PdfSiniri(en_cok_sure_s=30, ocr_sayfa_basi_s=9.99),
                saat=lambda: saat[0], ocr=motor)
    assert len(motor.cagrilar) == 3


def test_varsayilan_ocr_butcesi_iki_yavas_ocr_sayfasina_yeter(tmp_path):
    # 40 s'lik iki OCR sayfası: varsayılan bütçe 30 + 2 x 30 = 90 s >= 80 s, okunur.
    yol = pdf_yaz(tmp_path / "iki.pdf", [{"gorsel": True}, {"gorsel": True}])
    saat = [0.0]
    motor = SahteMotor(saat=saat, adim=40.0)
    belge = pdf_oku(yol, sinirlar=PdfSiniri(en_cok_sure_s=30), saat=lambda: saat[0], ocr=motor)
    assert belge.ocr_sayfalari == [1, 2]


def test_motor_verilse_de_metin_sayfalari_ek_butce_almaz(metin_pdf):
    # OCR'a giden sayfa yok: bütçe yalnız en_cok_sure_s (30 s); saat her çağrıda 20 s ilerler.
    zaman = [0.0]

    def saat():
        zaman[0] += 20.0
        return zaman[0]

    motor = SahteMotor()
    with pytest.raises(PdfSiniriAsildi, match="süre"):
        pdf_oku(metin_pdf, sinirlar=PdfSiniri(en_cok_sure_s=30), saat=saat, ocr=motor)
    assert motor.cagrilar == []


# --- OCR katmanlı sayfada tablolar --------------------------------------------------------

TABLO = [["Requirement", "Req para", "Test method"], ["Viscosity", "3.6.3", "ASTM D1200"]]


def test_ocr_katmanli_sayfada_pdf_tablolari_korunur(tmp_path):
    yol = pdf_yaz(tmp_path / "katman_tablo.pdf", [{"gorsel": True, "metin": [UZUN, UZUN], "tablo": TABLO}])
    ocrsuz = pdf_oku(yol).sayfalar[0]
    assert ocrsuz.tablolar == [TABLO]  # sayfa kurulumu: pdfplumber tabloyu görüyor
    sayfa = pdf_oku(yol, ocr=SahteMotor()).sayfalar[0]
    assert sayfa.kaynak == KAYNAK_OCR
    assert sayfa.metin == OCR_METNI       # metin OCR'dan
    assert sayfa.tablolar == [TABLO]      # tablo hazır katmandan


def test_taranmis_sayfada_tablo_bos_kalir(karma_pdf):
    sayfa = pdf_oku(karma_pdf, ocr=SahteMotor()).sayfalar[1]
    assert sayfa.kaynak == KAYNAK_OCR
    assert sayfa.tablolar == []
