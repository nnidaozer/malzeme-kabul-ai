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


# --- Güvenlik sınırları (docs/guvenlik.md, tehdit 2) ---------------------------

from malzeme_kabul.pdf_okuyucu import VARSAYILAN_SINIRLAR, PdfSiniri, PdfSiniriAsildi  # noqa: E402


def _uc_sayfa(tmp_path):
    return pdf_yaz(tmp_path / "uc.pdf", [{"metin": [f"Sayfa {i}"]} for i in range(1, 4)])


def test_varsayilan_sinirlar_gercek_standartlara_yeter():
    # data/raw altındaki en büyük standart 2,4 MB ve 34 sayfa.
    assert VARSAYILAN_SINIRLAR.en_cok_bayt >= 10 * 1024 * 1024
    assert VARSAYILAN_SINIRLAR.en_cok_sayfa >= 100
    assert VARSAYILAN_SINIRLAR.en_cok_sure_s >= 60


def test_sinir_asimi_valueerror_turundendir():
    # Okunamayan PDF'i ValueError ile yakalayan mevcut çağıranlar bozulmasın.
    assert issubclass(PdfSiniriAsildi, ValueError)


def test_buyuk_dosya_acilmadan_reddedilir(tmp_path, monkeypatch):
    yol = _uc_sayfa(tmp_path)
    acildi = []
    monkeypatch.setattr("malzeme_kabul.pdf_okuyucu.pdfplumber.open", lambda *a, **k: acildi.append(1))
    with pytest.raises(PdfSiniriAsildi, match="boyut"):
        pdf_oku(yol, sinirlar=PdfSiniri(en_cok_bayt=100))
    assert acildi == []


def test_cok_sayfali_belge_reddedilir(tmp_path):
    with pytest.raises(PdfSiniriAsildi, match="sayfa"):
        pdf_oku(_uc_sayfa(tmp_path), sinirlar=PdfSiniri(en_cok_sayfa=2))


def test_sayfa_siniri_tam_esitse_okunur(tmp_path):
    belge = pdf_oku(_uc_sayfa(tmp_path), sinirlar=PdfSiniri(en_cok_sayfa=3))
    assert len(belge.sayfalar) == 3


def test_sure_asilinca_okuma_durur(tmp_path):
    zaman = iter([0.0, 1.0, 50.0, 100.0, 200.0])
    with pytest.raises(PdfSiniriAsildi, match="süre"):
        pdf_oku(_uc_sayfa(tmp_path), sinirlar=PdfSiniri(en_cok_sure_s=30), saat=lambda: next(zaman))


def test_sure_icinde_okuma_tamamlanir(tmp_path):
    belge = pdf_oku(_uc_sayfa(tmp_path), sinirlar=PdfSiniri(en_cok_sure_s=30), saat=lambda: 0.0)
    assert [s.no for s in belge.sayfalar] == [1, 2, 3]


def test_varsayilan_sinirla_normal_okuma(ornek_pdf):
    assert len(pdf_oku(ornek_pdf).sayfalar) == 2


@pytest.mark.parametrize("alan", ["en_cok_bayt", "en_cok_sayfa", "en_cok_sure_s"])
def test_sinirlar_pozitif_olmali(alan):
    with pytest.raises(ValueError):
        PdfSiniri(**{alan: 0})
