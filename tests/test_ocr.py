"""Yerel Tesseract OCR katmanının testleri (malzeme_kabul.belge.ocr, docs/ocr.md).

TSV çözümleme ve güven hesapları sahte TSV metniyle, hata yolları sahte
(kabuk betiği) ya da olmayan komutla sınanır. Gerçek tesseract gerektiren
testler, tesseract kurulu değilse atlanır (CI'da olmayabilir). Ağ kullanılmaz.
"""

from __future__ import annotations

import os
import shutil
import stat
import time
from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from malzeme_kabul.belge.ocr import (
    DUSUK_GUVEN_ESIGI,
    OcrKelime,
    OcrKullanilamaz,
    OcrSonucu,
    TesseractMotoru,
    tesseract_var_mi,
    tsv_coz,
)

BASLIK = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
OLMAYAN = "olmayan-komut-xyz"

tesseract_yok = pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract kurulu değil")
posix_degil = pytest.mark.skipif(os.name == "nt", reason="sahte komut kabuk betiğidir")


def _satir(level, block, par, line, word, conf, text) -> str:
    return "\t".join(str(x) for x in (level, 1, block, par, line, word, 10, 20, 30, 40, conf, text))


def _tsv(*satirlar: str, son: str = "\n") -> str:
    return "\n".join([BASLIK, *satirlar]) + son


def _sonuc(*guvenler: float) -> OcrSonucu:
    return OcrSonucu(
        metin=" ".join(f"k{i}" for i in range(len(guvenler))),
        kelimeler=tuple(OcrKelime(f"k{i}", g) for i, g in enumerate(guvenler)),
    )


# --- TSV çözümleme ------------------------------------------------------------------


def test_ayni_satirdaki_kelimeler_tek_bosluklu_birlesir():
    sonuc = tsv_coz(_tsv(
        _satir(5, 1, 1, 1, 1, 96.5, "Viscosity"),
        _satir(5, 1, 1, 1, 2, 91, "100-500"),
        _satir(5, 1, 1, 1, 3, 90, "poises"),
    ))
    assert sonuc.metin == "Viscosity 100-500 poises"


def test_farkli_satirlar_gorunus_sirasiyla_yeni_satirla_birlesir():
    sonuc = tsv_coz(_tsv(
        _satir(5, 1, 1, 1, 1, 90, "3.6.3"),
        _satir(5, 1, 1, 1, 2, 90, "Viscosity."),
        _satir(5, 1, 1, 2, 1, 90, "40"),
        _satir(5, 1, 1, 2, 2, 90, "seconds"),
        _satir(5, 1, 2, 1, 1, 90, "Lead"),   # aynı line_num, farklı paragraf: ayrı satır
        _satir(5, 2, 1, 1, 1, 90, "TABLE"),  # aynı line_num, farklı blok: ayrı satır
    ))
    assert sonuc.metin == "3.6.3 Viscosity.\n40 seconds\nLead\nTABLE"


def test_ust_seviye_satirlar_kelime_sayilmaz():
    sonuc = tsv_coz(_tsv(
        _satir(1, 0, 0, 0, 0, -1, ""),
        _satir(2, 1, 0, 0, 0, -1, ""),
        _satir(3, 1, 1, 0, 0, -1, ""),
        _satir(4, 1, 1, 1, 0, -1, ""),
        _satir(5, 1, 1, 1, 1, 88, "Odor"),
    ))
    assert sonuc.metin == "Odor"
    assert sonuc.kelimeler == (OcrKelime("Odor", 88.0),)


def test_guveni_eksi_bir_olan_kelime_atlanir():
    sonuc = tsv_coz(_tsv(_satir(5, 1, 1, 1, 1, -1, "hayalet"), _satir(5, 1, 1, 1, 2, 70, "gercek")))
    assert sonuc.metin == "gercek"
    assert [k.metin for k in sonuc.kelimeler] == ["gercek"]


def test_guveni_sifir_olan_kelime_tutulur():
    sonuc = tsv_coz(_tsv(_satir(5, 1, 1, 1, 1, 0, "zor")))
    assert sonuc.kelimeler == (OcrKelime("zor", 0.0),)


def test_bos_ya_da_bosluk_metinli_kelime_atlanir():
    sonuc = tsv_coz(_tsv(
        _satir(5, 1, 1, 1, 1, 95, ""),
        _satir(5, 1, 1, 1, 2, 95, "   "),
        _satir(5, 1, 1, 1, 3, 95, "dolu"),
    ))
    assert sonuc.metin == "dolu"
    assert len(sonuc.kelimeler) == 1


def test_kelime_guveni_ondalik_sayi_olarak_tutulur():
    (kelime,) = tsv_coz(_tsv(_satir(5, 1, 1, 1, 1, "96.123456", "cP"))).kelimeler
    assert kelime.metin == "cP"
    assert kelime.guven == pytest.approx(96.123456)
    assert isinstance(kelime.guven, float)


@pytest.mark.parametrize("tsv", ["", "\n", BASLIK, BASLIK + "\n", BASLIK + "\r\n"],
                         ids=["bos", "yeni_satir", "yalniz_baslik", "baslik_yeni_satir", "baslik_crlf"])
def test_bos_tsv_bos_sonuc_verir(tsv):
    sonuc = tsv_coz(tsv)
    assert sonuc.metin == ""
    assert sonuc.kelimeler == ()


def test_crlf_ve_sondaki_bos_satirlar_tolere_edilir():
    lf = _tsv(_satir(5, 1, 1, 1, 1, 90, "a"), _satir(5, 1, 1, 2, 1, 80, "b"), son="\n\n\n")
    crlf = lf.replace("\n", "\r\n")
    assert tsv_coz(crlf) == tsv_coz(lf)
    assert tsv_coz(crlf).metin == "a\nb"
    assert [k.metin for k in tsv_coz(crlf).kelimeler] == ["a", "b"]


# --- Sonuç nesneleri ve güven -----------------------------------------------------


def test_sonuc_ve_kelime_degistirilemez():
    kelime = OcrKelime("a", 90.0)
    sonuc = OcrSonucu("a", (kelime,))
    with pytest.raises(AttributeError):
        kelime.guven = 10.0  # type: ignore[misc]
    with pytest.raises(AttributeError):
        sonuc.metin = "b"  # type: ignore[misc]


def test_dusuk_guven_esigi_60tir():
    assert DUSUK_GUVEN_ESIGI == 60.0


def test_ortalama_guven_kelime_guvenlerinin_ortalamasidir():
    assert _sonuc(90, 60, 30).ortalama_guven == pytest.approx(60.0)


def test_kelime_yoksa_ortalama_guven_none():
    assert OcrSonucu("", ()).ortalama_guven is None


def test_dusuk_guvenli_oran_esige_esit_kelimeyi_dusuk_saymaz():
    # 59.9 eşiğin hemen altı (düşük), 60.0 tam eşik (düşük değil), 60.1 hemen üstü.
    assert _sonuc(59.9, 60.0, 60.1, 95.0).dusuk_guvenli_oran() == pytest.approx(0.25)


def test_dusuk_guvenli_oran_verilen_esigi_kullanir():
    sonuc = _sonuc(59.9, 60.0, 60.1, 95.0)
    assert sonuc.dusuk_guvenli_oran(esik=95.0) == pytest.approx(0.75)
    assert sonuc.dusuk_guvenli_oran(esik=0.0) == pytest.approx(0.0)


def test_kelime_yoksa_dusuk_guvenli_oran_sifirdir():
    assert OcrSonucu("", ()).dusuk_guvenli_oran() == 0.0


# --- Motor ayarları ve hata yolları (tesseract gerekmez) ----------------------------


@pytest.mark.parametrize("deger", [0, -1, -0.5])
def test_zaman_asimi_pozitif_olmali(deger):
    with pytest.raises(ValueError):
        TesseractMotoru(zaman_asimi_s=deger)


@pytest.mark.parametrize("deger", [0, -300])
def test_dpi_pozitif_olmali(deger):
    with pytest.raises(ValueError):
        TesseractMotoru(dpi=deger)


def test_varsayilan_motor_ayarlari_plandakiyle_ayni():
    motor = TesseractMotoru()
    assert (motor.dil, motor.psm, motor.dpi, motor.zaman_asimi_s) == ("eng", 3, 300, 120)


@pytest.fixture
def png(tmp_path) -> Path:
    yol = tmp_path / "sayfa.png"
    Image.new("RGB", (200, 100), "white").save(yol)
    return yol


def test_olmayan_komutla_resim_okumak_ocr_kullanilamaz_verir(png):
    with pytest.raises(OcrKullanilamaz):
        TesseractMotoru(komut=OLMAYAN).resim_oku(png)


def test_ocr_kullanilamaz_runtime_error_turundendir_filenotfound_degildir():
    assert issubclass(OcrKullanilamaz, RuntimeError)
    assert not issubclass(OcrKullanilamaz, FileNotFoundError)


def test_olmayan_komutla_surum_ocr_kullanilamaz_verir():
    with pytest.raises(OcrKullanilamaz):
        TesseractMotoru(komut=OLMAYAN).surum()


def test_olmayan_komut_icin_tesseract_yok_denir():
    assert tesseract_var_mi(komut=OLMAYAN) is False


def _sahte_komut(klasor: Path, govde: str) -> str:
    yol = klasor / "sahte-tesseract"
    yol.write_text("#!/bin/sh\n" + govde + "\n", encoding="utf-8")
    yol.chmod(yol.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(yol)


@posix_degil
def test_hata_koduyla_biten_komut_ocr_kullanilamaz_verir(tmp_path, png):
    komut = _sahte_komut(tmp_path, 'echo "bozuk resim" >&2\nexit 1')
    with pytest.raises(OcrKullanilamaz):
        TesseractMotoru(komut=komut).resim_oku(png)


@posix_degil
def test_zaman_asiminda_ocr_kullanilamaz_verir_ve_beklemez(tmp_path, png):
    komut = _sahte_komut(tmp_path, "sleep 10")
    baslangic = time.monotonic()
    with pytest.raises(OcrKullanilamaz):
        TesseractMotoru(komut=komut, zaman_asimi_s=0.5).resim_oku(png)
    assert time.monotonic() - baslangic < 5


# --- Gerçek tesseract ---------------------------------------------------------------


def _buyuk_puntolu_pdf(yol: Path) -> Path:
    c = canvas.Canvas(str(yol), pagesize=A4)
    c.setFont("Helvetica", 36)
    c.drawString(60, A4[1] - 150, "Viscosity 100-500 poises")
    c.showPage()
    c.save()
    return yol


@tesseract_yok
def test_tesseract_kuruluysa_var_denir():
    assert tesseract_var_mi() is True


@tesseract_yok
def test_gercek_tesseract_pdf_sayfasini_okur(tmp_path):
    pdf = _buyuk_puntolu_pdf(tmp_path / "buyuk.pdf")
    sonuc = TesseractMotoru().sayfa_oku(pdf, 1)
    assert isinstance(sonuc, OcrSonucu)
    assert "Viscosity" in sonuc.metin
    assert "100-500" in sonuc.metin
    assert sonuc.ortalama_guven is not None and sonuc.ortalama_guven > 60


@tesseract_yok
def test_gercek_tesseract_surumu_doner():
    surum = TesseractMotoru().surum()
    assert isinstance(surum, str)
    assert surum.startswith(("5.", "4."))


@tesseract_yok
@pytest.mark.parametrize("sayfa_no", [0, -1, 2])
def test_sayfa_numarasi_aralik_disindaysa_valueerror(tmp_path, sayfa_no):
    pdf = _buyuk_puntolu_pdf(tmp_path / "tek.pdf")
    with pytest.raises(ValueError):
        TesseractMotoru().sayfa_oku(pdf, sayfa_no)


@tesseract_yok
def test_gercek_tesseract_bozuk_resimde_ocr_kullanilamaz_verir(tmp_path):
    bozuk = tmp_path / "bozuk.png"
    bozuk.write_bytes(b"resim degil")
    with pytest.raises(OcrKullanilamaz):
        TesseractMotoru().resim_oku(bozuk)


@tesseract_yok
def test_gercek_tesseract_olmayan_resim_yolunda_ocr_kullanilamaz_verir(tmp_path):
    with pytest.raises(OcrKullanilamaz):
        TesseractMotoru().resim_oku(tmp_path / "yok.png")


# --- Sürüm dizisi (sahte komut) ----------------------------------------------------------


@posix_degil
@pytest.mark.parametrize(
    "cikti, beklenen",
    [
        ("tesseract v5.3.0.20221214\\n leptonica-1.82.0\\n", "5.3.0.20221214"),  # Windows (UB-Mannheim)
        ("tesseract 5.3.4\\n leptonica-1.82.0\\n", "5.3.4"),                     # Linux
    ],
    ids=["v_onekli", "oneksiz"],
)
def test_surum_bastaki_v_harfini_atar(tmp_path, cikti, beklenen):
    komut = _sahte_komut(tmp_path, f'printf "{cikti}"')
    assert TesseractMotoru(komut=komut).surum() == beklenen


# --- Piksel sınırı (render ve tesseract çağrısından önce) --------------------------------


def _kucuk_pdf(yol: Path, genislik: int = 100, yukseklik: int = 200) -> Path:
    c = canvas.Canvas(str(yol), pagesize=(genislik, yukseklik))
    c.drawString(10, 100, "x")
    c.showPage()
    c.save()
    return yol


@pytest.fixture
def isaretli_komut(tmp_path):
    """Çağrılırsa işaret dosyası bırakan, boş TSV dönen sahte tesseract."""
    isaret = tmp_path / "cagrildi"
    return _sahte_komut(tmp_path, f'touch "{isaret}"\nexit 0'), isaret


def test_en_cok_piksel_varsayilani_yuz_milyondur():
    assert TesseractMotoru().en_cok_piksel == 100_000_000


@pytest.mark.parametrize("deger", [0, -1])
def test_en_cok_piksel_pozitif_olmali(deger):
    with pytest.raises(ValueError):
        TesseractMotoru(en_cok_piksel=deger)


@posix_degil
@pytest.mark.parametrize("dpi, piksel", [(72, 100 * 200), (144, 100 * 200 * 4)], ids=["dpi72", "dpi144"])
def test_piksel_siniri_asilinca_render_ve_tesseract_olmadan_reddedilir(tmp_path, monkeypatch, isaretli_komut,
                                                                        dpi, piksel):
    import pypdfium2

    komut, isaret = isaretli_komut
    pdf = _kucuk_pdf(tmp_path / "kucuk.pdf")

    def render_edilmemeli(*a, **k):
        raise AssertionError("sayfa render edilmemeliydi")

    monkeypatch.setattr(pypdfium2.PdfPage, "render", render_edilmemeli)
    with pytest.raises(OcrKullanilamaz):
        TesseractMotoru(komut=komut, dpi=dpi, en_cok_piksel=piksel - 1).sayfa_oku(pdf, 1)  # hemen altı
    assert not isaret.exists()


@posix_degil
@pytest.mark.parametrize("dpi, piksel", [(72, 100 * 200), (144, 100 * 200 * 4)], ids=["dpi72", "dpi144"])
def test_piksel_siniri_tam_esitse_sayfa_okunur(tmp_path, isaretli_komut, dpi, piksel):
    komut, isaret = isaretli_komut
    pdf = _kucuk_pdf(tmp_path / "kucuk.pdf")
    sonuc = TesseractMotoru(komut=komut, dpi=dpi, en_cok_piksel=piksel).sayfa_oku(pdf, 1)
    assert sonuc.kelimeler == ()
    assert isaret.exists()  # sınır aşılmadı: tesseract çağrıldı


# --- Açılamayan PDF -------------------------------------------------------------------------


@pytest.mark.parametrize("icerik", [b"\x00\x13rastgele baytlar\xff" * 20, b""], ids=["rastgele", "bos"])
def test_acilamayan_pdf_ocr_kullanilamaz_verir(tmp_path, icerik):
    yol = tmp_path / "bozuk.pdf"
    yol.write_bytes(icerik)
    with pytest.raises(OcrKullanilamaz):
        TesseractMotoru().sayfa_oku(yol, 1)

