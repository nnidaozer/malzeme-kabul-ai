"""Kabul dokümanı çıktısında ürün tanımı, sonuç kaynağı ve yönü belirsiz sınır."""

from __future__ import annotations

from malzeme_kabul.arayuz.dokuman_uretici import bolumler, markdown_uret, sinir_metni
from malzeme_kabul.sozlesme.sema import KabulDokumani, Kaynak, Sinir, StandartBilgisi, TanimKaydi, UrunTanimi
from malzeme_kabul.sozlesme.sema import TestSarti as Sart


def kaynak(madde):
    return Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde=madde)


def dokuman():
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        urun_tanimi=UrunTanimi(siniflar=[TanimKaydi(kod="Class N", aciklama="Non-chromate", kaynak=kaynak("1.2.2"))]),
        testler=[
            Sart(
                id="krom", test_adi="Chromium content", kaynak=kaynak("3.4"), test_turleri={"kabul"},
                sinir=Sinir(kriter_turu="sayisal", ust=0.1, birim="%", orijinal_metin="0.1 % max"),
                uygulanabilirlik=["Class N"], sonuc_kaynagi="ic_laboratuvar",
            ),
        ],
    )


def test_urun_tanimi_ilk_bolumdur():
    b = bolumler(dokuman())[0]
    assert b.baslik == "Ürün tanımı"
    assert b.satirlar == [["Sınıf", "Class N", "Non-chromate", "MIL-PRF-23377K, 1.2.2"]]


def test_test_satirinda_sonuc_kaynagi_yazar():
    md = markdown_uret(dokuman())
    assert "| Sonuç kaynağı |" in md
    assert "| Chromium content | — | ≤ 0.1 % | Class N | İç laboratuvar | MIL-PRF-23377K, 3.4 |" in md


def test_yonu_belirsiz_sinir_karsilastirma_isareti_almaz():
    s = Sinir(kriter_turu="sayisal", alt=4, ust=4, birim="hour", yon="belirsiz", orijinal_metin="pot life of 4 hours")
    assert sinir_metni(s) == "4 hour (yön belirsiz, insan incelemeli)"


def test_urun_tanimi_yoksa_bolum_eklenmez():
    d = dokuman().model_copy(update={"urun_tanimi": None})
    assert all(b.baslik != "Ürün tanımı" for b in bolumler(d))
