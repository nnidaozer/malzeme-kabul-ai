"""Kabul dokümanını Markdown ve Word olarak üreten modülün testleri."""

from __future__ import annotations

import pytest
from docx import Document

from malzeme_kabul.dokuman_uretici import markdown_uret, sinir_metni, word_uret
from malzeme_kabul.sema import (
    KabulDokumani,
    Kaynak,
    Kosul,
    NumuneHazirlama,
    RafOmru,
    Sinir,
    StandartBilgisi,
)
from malzeme_kabul.sema import TestSarti as Sart


def kaynak(madde):
    return Kaynak(standart="MIL-PRF-23377", revizyon="K", madde=madde)


@pytest.fixture
def dokuman():
    return KabulDokumani(
        standart=StandartBilgisi(standart="MIL-PRF-23377", revizyon="K", baslik="Primer coatings: epoxy"),
        testler=[
            Sart(
                id="voc", test_adi="VOC content", test_metodu="ASTM D 3960",
                sinir=Sinir(tur="en_cok", ust=340, birim="g/L"), kaynak=kaynak("3.4.1"),
                test_turleri={"kabul", "omur_uzatma"},
            ),
            Sart(
                id="esneklik", test_adi="Flexibility", test_metodu="ASTM D 522",
                sinir=Sinir(tur="nitel", ifade="No cracking"), kaynak=kaynak("3.6.4"),
                test_turleri={"yeterlilik"}, numune_hazirlama_id="panel",
            ),
        ],
        raf_omru=RafOmru(sure=12, birim="ay", baslangic="üretim tarihinden itibaren", kaynak=kaynak("3.7")),
        kosullar=[
            Kosul(kategori="depolama", ad="Depolama sıcaklığı",
                  sinir=Sinir(tur="aralik", alt=40, ust=100, birim="°F"), kaynak=kaynak("3.7.1")),
            Kosul(kategori="kullanim", ad="Kap ömrü", aciklama="En az 4 saat", kaynak=kaynak("3.5.2")),
        ],
        numune_hazirlama=[
            NumuneHazirlama(id="panel", kupon_malzemesi="2024-T3", kurlenme="7 gün", kaynak=kaynak("4.5.2")),
        ],
    )


@pytest.mark.parametrize(
    "sinir, beklenen",
    [
        (Sinir(tur="aralik", alt=20, ust=30, birim="s"), "20 – 30 s"),
        (Sinir(tur="en_az", alt=4, birim="saat"), "≥ 4 saat"),
        (Sinir(tur="en_az", alt=4, alt_dahil=False, birim="saat"), "> 4 saat"),
        (Sinir(tur="en_cok", ust=340, birim="g/L"), "≤ 340 g/L"),
        (Sinir(tur="en_cok", ust=0.5, ust_dahil=False), "< 0.5"),
        (Sinir(tur="esit", alt=7), "= 7"),
        (Sinir(tur="nitel", ifade="No blistering"), "No blistering"),
        (Sinir(tur="aralik", alt=0.6, ust=0.9, birim="mil"), "0.6 – 0.9 mil"),
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
    assert "12 ay (üretim tarihinden itibaren)" in md
    assert "40 – 100 °F" in md
    assert "En az 4 saat" in md
    assert "2024-T3" in md


def test_bos_bolum_yazilmaz():
    d = KabulDokumani(standart=StandartBilgisi(standart="MIL-PRF-23377", revizyon="K"))
    md = markdown_uret(d)
    assert "## Kabul testleri" not in md
    assert "Raf ömrü" not in md


def test_tablo_hucresindeki_dikey_cizgi_kacirilir():
    d = KabulDokumani(
        standart=StandartBilgisi(standart="MIL-PRF-23377", revizyon="K"),
        testler=[Sart(id="a", test_adi="A | B", sinir=Sinir(tur="nitel", ifade="x"),
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
