"""pdfplumber ile metin ve tablo çıkaran modülün testleri."""

from __future__ import annotations

import pytest

from pdf_uretici import pdf_yaz

from malzeme_kabul.pdf_okuyucu import Belge, pdf_oku

TABLO = [
    ["Characteristic", "Requirement", "Paragraph"],
    ["Viscosity", "20 - 30 s", "3.5.1"],
    ["Pot life", "4 hours", "3.5.2"],
]


@pytest.fixture
def ornek_pdf(tmp_path):
    return pdf_yaz(
        tmp_path / "ornek.pdf",
        [
            {"metin": ["3.4 Shelf life. The primer shall meet requirements", "after 12 months storage."]},
            {"metin": ["TABLE I. Requirements"], "tablo": TABLO},
        ],
    )


def test_pdf_sayfa_sayfa_okunur(ornek_pdf):
    belge = pdf_oku(ornek_pdf)
    assert isinstance(belge, Belge)
    assert [s.no for s in belge.sayfalar] == [1, 2]
    assert "3.4 Shelf life." in belge.sayfalar[0].metin
    assert "after 12 months storage." in belge.sayfalar[0].metin


def test_tablolar_hucre_hucre_cikarilir(ornek_pdf):
    belge = pdf_oku(ornek_pdf)
    assert belge.sayfalar[0].tablolar == []
    assert belge.sayfalar[1].tablolar == [TABLO]


def test_tam_metin_sayfalari_sirayla_birlestirir(ornek_pdf):
    metin = pdf_oku(ornek_pdf).tam_metin
    assert metin.index("Shelf life") < metin.index("TABLE I")


def test_satirlar_sayfa_numarasiyla_gelir(ornek_pdf):
    satirlar = pdf_oku(ornek_pdf).satirlar()
    assert (1, "3.4 Shelf life. The primer shall meet requirements") in satirlar
    assert (2, "TABLE I. Requirements") in satirlar
    assert all(metin.strip() for _, metin in satirlar)


def test_tum_tablolar_sayfa_numarasiyla_gelir(ornek_pdf):
    assert pdf_oku(ornek_pdf).tablolar() == [(2, TABLO)]


def test_bos_hucreler_bos_metin_olur(tmp_path):
    yol = pdf_yaz(tmp_path / "b.pdf", [{"tablo": [["A", "B"], ["1", ""]]}])
    assert pdf_oku(yol).sayfalar[0].tablolar == [[["A", "B"], ["1", ""]]]


def test_metinsiz_taranmis_sayfa_bos_metin_doner(tmp_path):
    yol = pdf_yaz(tmp_path / "t.pdf", [{"gorsel": True}])
    sayfa = pdf_oku(yol).sayfalar[0]
    assert sayfa.metin == ""
    assert sayfa.tablolar == []


def test_olmayan_dosya_hata_verir(tmp_path):
    with pytest.raises(FileNotFoundError):
        pdf_oku(tmp_path / "yok.pdf")


def test_pdf_olmayan_dosya_valueerror_verir(tmp_path):
    yol = tmp_path / "x.pdf"
    yol.write_text("pdf değil")
    with pytest.raises(ValueError):
        pdf_oku(yol)
