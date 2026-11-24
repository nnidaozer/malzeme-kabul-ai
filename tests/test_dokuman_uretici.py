"""Kabul dokümanını Markdown ve Word olarak üreten modülün testleri."""

from __future__ import annotations

import pytest
from docx import Document

from malzeme_kabul.arayuz.dokuman_uretici import markdown_uret, sinir_metni, word_uret
from malzeme_kabul.sozlesme.sema import (
    KabulDokumani,
    Kaynak,
    Kosul,
    NumuneHazirlama,
    RafOmru,
    Sinir,
    StandartBilgisi,
)
from malzeme_kabul.sozlesme.sema import TestSarti as Sart


def kaynak(madde):
    return Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde=madde)


@pytest.fixture
def dokuman():
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K", baslik="Primer coatings: epoxy"),
        testler=[
            Sart(
                id="voc", test_adi="VOC content", test_metodu="ASTM D 3960",
                sinir=Sinir(kriter_turu="sayisal", ust=340, birim="g/L", orijinal_metin="340 g/L max"), kaynak=kaynak("3.4.1"),
                test_turleri={"kabul", "omur_uzatma"},
            ),
            Sart(
                id="esneklik", test_adi="Flexibility", test_metodu="ASTM D 522",
                sinir=Sinir(kriter_turu="metinsel", orijinal_metin="No cracking"), kaynak=kaynak("3.6.4"),
                test_turleri={"yeterlilik"}, numune_hazirlama_id="panel",
            ),
        ],
        raf_omurleri=[RafOmru(sure=12, birim="month", baslangic="üretim tarihinden itibaren",
                         kosul=Sinir(kriter_turu="sayisal", alt=4, ust=38, birim="°C", orijinal_metin="4 to 38 °C"),
                         kaynak=kaynak("3.7"))],
        kosullar=[
            Kosul(kategori="depolama", ad="Depolama sıcaklığı",
                  sinir=Sinir(kriter_turu="sayisal", alt=40, ust=100, birim="°F", orijinal_metin="40 to 100 °F"), kaynak=kaynak("3.7.1")),
            Kosul(kategori="kullanim", ad="Kap ömrü", aciklama="En az 4 saat", kaynak=kaynak("3.5.2")),
        ],
        numune_hazirlama=[
            NumuneHazirlama(id="panel", kupon_malzemesi="2024-T3", kurlenme="7 gün", kaynak=kaynak("4.5.2")),
        ],
    )


def _s(kriter="sayisal", metin="orijinal", **ek):
    return Sinir(kriter_turu=kriter, orijinal_metin=metin, **ek)


@pytest.mark.parametrize(
    "sinir, beklenen",
    [
        (_s(alt=20, ust=30, birim="s"), "20 – 30 s"),
        (_s(alt=4, birim="hour"), "≥ 4 hour"),
        (_s(alt=4, alt_dahil=False, birim="hour"), "> 4 hour"),
        (_s(ust=340, birim="g/L"), "≤ 340 g/L"),
        (_s(ust=0.5, ust_dahil=False), "< 0.5"),
        (_s(alt=7, ust=7), "= 7"),
        (_s(alt=0.6, ust=0.9, birim="mil"), "0.6 – 0.9 mil"),
        (_s("metinsel", "No blistering"), "No blistering"),
        (_s("gecti_kaldi", "Shall pass"), "Geçti/kaldı: Shall pass"),
    ],
)
def test_sinir_metni(sinir, beklenen):
    assert sinir_metni(sinir) == beklenen


def test_markdown_baslik_ve_taslak_uyarisi_icerir(dokuman):
    md = markdown_uret(dokuman)
    assert md.startswith("# Kabul Dokümanı: MIL-PRF-23377K")
    assert "TASLAK" in md


def test_markdown_her_sartin_yaninda_madde_numarasi_var(dokuman):
    md = markdown_uret(dokuman)
    satir = next(s for s in md.splitlines() if "VOC content" in s and s.startswith("|"))
    assert "≤ 340 g/L" in satir and "3.4.1" in satir and "ASTM D 3960" in satir
    for madde in ("3.7", "3.7.1", "3.5.2", "4.5.2", "3.6.4"):
        assert madde in md


def test_markdown_testleri_turune_gore_bolumlere_ayirir(dokuman):
    md = markdown_uret(dokuman)
    kabul = md.index("## Kabul testleri")
    omur = md.index("## Ömür uzatma testleri")
    yeterlilik = md.index("## Yeterlilik testleri")
    assert kabul < omur < yeterlilik
    # VOC hem kabul hem ömür uzatma testi: iki bölümde de görünür.
    assert md.count("VOC content") == 2
    assert "Flexibility" in md[yeterlilik:]


def test_markdown_raf_omru_depolama_kullanim_numune_bolumleri(dokuman):
    md = markdown_uret(dokuman)
    assert "12 month (üretim tarihinden itibaren), 4 – 38 °C" in md
    assert "40 – 100 °F" in md
    assert "En az 4 saat" in md
    assert "2024-T3" in md


def test_bos_bolum_yazilmaz():
    d = KabulDokumani(standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"))
    md = markdown_uret(d)
    assert "## Kabul testleri" not in md
    assert "Raf ömrü" not in md


def test_tablo_hucresindeki_dikey_cizgi_kacirilir():
    d = KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        testler=[Sart(id="a", test_adi="A | B", sinir=Sinir(kriter_turu="metinsel", orijinal_metin="x"),
                      kaynak=kaynak("3.1"), test_turleri={"kabul"})],
    )
    assert "A \\| B" in markdown_uret(d)


def test_word_dosyasi_tablolar_ve_madde_numaralariyla_yazilir(dokuman, tmp_path):
    yol = word_uret(dokuman, tmp_path / "kabul.docx")
    belge = Document(str(yol))
    metin = "\n".join(p.text for p in belge.paragraphs)
    assert "Kabul Dokümanı: MIL-PRF-23377K" in metin
    assert "TASLAK" in metin
    hucreler = [h.text for t in belge.tables for s in t.rows for h in s.cells]
    assert "VOC content" in hucreler
    assert "MIL-PRF-23377K, 3.4.1" in hucreler
    assert "≤ 340 g/L" in hucreler


def test_musteri_sartnamesine_dayanan_sartin_kaynagi_ayri_gosterilir(dokuman):
    musteri = Sart(
        id="musteri_voc", test_adi="VOC (müşteri)", sinir=Sinir(kriter_turu="sayisal", ust=250, birim="g/L", orijinal_metin="250 g/L max"),
        kaynak=Kaynak(belge_no="MUSTERI-SPEC-001", revizyon="B", madde="2.1"), test_turleri={"kabul"},
    )
    d = dokuman.model_copy(update={"testler": dokuman.testler + [musteri]})
    assert "MUSTERI-SPEC-001 Rev. B, 2.1" in markdown_uret(d)


def test_raf_omru_kap_turuyle_ayri_satirlarda_yazilir():
    d = KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        raf_omurleri=[RafOmru(kap_turu="metal", sure=1, birim="year", kaynak=kaynak("3.5.3")),
                      RafOmru(kap_turu="plastik", sure=6, birim="month", kaynak=kaynak("3.5.3"))],
    )
    md = markdown_uret(d)
    assert "| metal | 1 year | MIL-PRF-23377K, 3.5.3 |" in md
    assert "| plastik | 6 month | MIL-PRF-23377K, 3.5.3 |" in md
