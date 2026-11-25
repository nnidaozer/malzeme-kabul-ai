"""Standart tarafında hibrit birleştirme: kural öncelikli, dil modeli tamamlar.

Kural çıktısı aynen kalır. Dil modelinin kuralla eşleşmeyen testleri yalnız
özgün metinleri belgenin söylenen sayfasında bulunursa alınır; sınırları
modelden değil, kurallarla (`sinir_cikar`) yeniden hesaplanır.
"""

from __future__ import annotations

import json

import pytest

from malzeme_kabul.belge.pdf_okuyucu import Belge, Sayfa
from malzeme_kabul.sozlesme.sema import (
    KabulDokumani, Kaynak, Kosul, NumuneHazirlama, RafOmru, Sinir, StandartBilgisi, TanimKaydi, UrunTanimi,
)
from malzeme_kabul.sozlesme.sema import TestSarti as Sart

BELGE_NO, REV = "MIL-PRF-23377", "K"

VISKOZITE_METNI = "The maximum viscosity shall be 40 seconds through a cup."
KURSUN_METNI = "The lead content shall be not greater than 1 ppm."
KOKU_METNI = "The odor shall not be objectionable."


def _hibrit():
    from deney import hibrit_standart

    return hibrit_standart


def kaynak(madde, sayfa=None):
    return Kaynak(belge_no=BELGE_NO, revizyon=REV, madde=madde, sayfa=sayfa)


def sart(id, ad, sinir, madde, sayfa=None, turler=("kabul",), uygulanabilirlik=(), numune=None, metot=None):
    return Sart(
        id=id, test_adi=ad, test_metodu=metot, sinir=sinir, kaynak=kaynak(madde, sayfa),
        test_turleri=set(turler), uygulanabilirlik=list(uygulanabilirlik), numune_hazirlama_id=numune,
    )


def sayisal(metin, alt=None, ust=None, birim=None, **kw):
    return Sinir(kriter_turu="sayisal", alt=alt, ust=ust, birim=birim, orijinal_metin=metin, **kw)


def dok(testler=(), **kw):
    return KabulDokumani(standart=StandartBilgisi(belge_no=BELGE_NO, revizyon=REV), testler=list(testler), **kw)


def belge() -> Belge:
    return Belge(
        dosya="MIL-PRF-23377K.pdf",
        sayfalar=[
            Sayfa(1, "MIL-PRF-23377K\n3.6.3 Viscosity. The maximum viscosity shall be\n40 seconds through a cup."),
            Sayfa(2, f"MIL-PRF-23377K\n3.6.9 Lead content. {KURSUN_METNI}\n3.6.10 Odor. {KOKU_METNI}"),
        ],
    )


def kural_dokumani() -> KabulDokumani:
    """Kural çıktısı: test, raf ömrü, koşul, numune ve ürün tanımı dolu."""
    viskozite = sart("viscosity", "Viscosity", sayisal(VISKOZITE_METNI, ust=40, birim="s"), "3.6.3", 1,
                     turler=("kabul", "yeterlilik"), numune="panel_A", metot="ASTM D1200")
    return dok(
        [viskozite],
        urun_tanimi=UrunTanimi(tipler=[TanimKaydi(kod="Type I", kaynak=kaynak("1.2.1"))]),
        raf_omurleri=[RafOmru(sure=1, birim="year", kaynak=kaynak("3.10"))],
        kosullar=[Kosul(kategori="depolama", ad="Depolama sıcaklığı",
                        sinir=sayisal("4 to 38 °C", alt=4, ust=38, birim="°C"), kaynak=kaynak("3.10"))],
        numune_hazirlama=[NumuneHazirlama(id="panel_A", kupon_malzemesi="2024-T3", kaynak=kaynak("TABLE I"))],
    )


def koku(id="odor", sinir=None, sayfa=2, madde="3.6.10"):
    return sart(id, "Odor", sinir or Sinir(kriter_turu="metinsel", orijinal_metin=KOKU_METNI), madde, sayfa,
                uygulanabilirlik=("Type I",))


def kursun(id="lead_content", sinir=None, sayfa=2):
    sinir = sinir or sayisal(KURSUN_METNI, alt=0.001, birim="ppm", ust_dahil=False)
    return sart(id, "Lead content", sinir, "3.6.9", sayfa, turler=("kabul", "yeterlilik"))


# --- Kural öncelikli -----------------------------------------------------------------


def test_kural_kayitlari_aynen_korunur():
    kural = kural_dokumani()
    hibrit, _ = _hibrit().hibrit_birlestir(kural, dok([koku()]), belge())
    assert hibrit.standart == kural.standart
    assert hibrit.urun_tanimi == kural.urun_tanimi
    assert hibrit.raf_omurleri == kural.raf_omurleri
    assert hibrit.kosullar == kural.kosullar
    assert hibrit.numune_hazirlama == kural.numune_hazirlama
    assert hibrit.testler[: len(kural.testler)] == kural.testler


def test_kuralla_ayni_kimlikli_dil_modeli_testi_alinmaz_kural_degerleri_kalir():
    """Eşleşen dil modeli testi ayrıca eklenmez; sayılar kuraldan kalır (anlaşmazlık ayrıca işaretlenir)."""
    kural = kural_dokumani()
    dil_viskozite = sart("viscosity", "Viscosity", sayisal(VISKOZITE_METNI, ust=60, birim="s"), "3.6.3", 1)
    hibrit, rapor = _hibrit().hibrit_birlestir(kural, dok([dil_viskozite]), belge())
    assert [t.id for t in hibrit.testler] == ["viscosity"]
    assert (hibrit.testler[0].sinir.alt, hibrit.testler[0].sinir.ust, hibrit.testler[0].sinir.birim) == (None, 40, "s")
    assert rapor.kuralla_eslesen == ["viscosity"]
    assert rapor.eklenen == []


def test_kuralla_ad_benzerligiyle_eslesen_dil_modeli_testi_alinmaz():
    kural = kural_dokumani()
    dil = sart("viscosity_ford_cup", "Viscosity", sayisal(VISKOZITE_METNI, ust=60, birim="s"), "3.6.3", 1)
    hibrit, rapor = _hibrit().hibrit_birlestir(kural, dok([dil]), belge())
    assert [t.id for t in hibrit.testler] == ["viscosity"]
    assert rapor.kuralla_eslesen == ["viscosity_ford_cup"]  # dil modeli kimliği


# --- Kanıt -------------------------------------------------------------------------


def test_eslesmeyen_kanitli_dil_modeli_testi_eklenir():
    kural = kural_dokumani()
    hibrit, rapor = _hibrit().hibrit_birlestir(kural, dok([koku()]), belge())
    assert [t.id for t in hibrit.testler] == ["viscosity", "odor"]
    assert rapor.eklenen == ["odor"]
    assert rapor.kanitsiz == []


def test_ozgun_metni_sayfada_olmayan_test_alinmaz():
    uydurma = koku(sinir=Sinir(kriter_turu="metinsel", orijinal_metin="The odor shall be pleasant and mild."))
    hibrit, rapor = _hibrit().hibrit_birlestir(kural_dokumani(), dok([uydurma]), belge())
    assert [t.id for t in hibrit.testler] == ["viscosity"]
    assert [id_ for id_, _ in rapor.kanitsiz] == ["odor"]
    assert rapor.eklenen == []


def test_ozgun_metin_baska_sayfadaysa_test_alinmaz():
    """Metin belgede var ama modelin söylediği sayfada yok: kanıt sayılmaz."""
    hibrit, rapor = _hibrit().hibrit_birlestir(kural_dokumani(), dok([koku(sayfa=1)]), belge())
    assert [t.id for t in hibrit.testler] == ["viscosity"]
    assert [id_ for id_, _ in rapor.kanitsiz] == ["odor"]


@pytest.mark.parametrize("sayfa", [None, 99], ids=["sayfa_yok", "belgede_olmayan_sayfa"])
def test_sayfasi_bilinmeyen_test_alinmaz(sayfa):
    hibrit, rapor = _hibrit().hibrit_birlestir(kural_dokumani(), dok([koku(sayfa=sayfa)]), belge())
    assert [t.id for t in hibrit.testler] == ["viscosity"]
    assert [id_ for id_, _ in rapor.kanitsiz] == ["odor"]
    neden = dict((i, n) for i, n in rapor.kanitsiz)["odor"]
    assert isinstance(neden, str) and neden


def test_kanit_bosluk_ve_harf_buyuklugunden_bagimsizdir():
    """Kanıt `metin_sayfada_mi` ile aranır: satır sonu ve büyük/küçük harf farkı kanıtı bozmaz."""
    metin = "the maximum VISCOSITY shall be 40 seconds   through a cup."
    dil = sart("viscosity_thinned", "Thinned viscosity", Sinir(kriter_turu="metinsel", orijinal_metin=metin),
               "3.6.5", 1)
    hibrit, rapor = _hibrit().hibrit_birlestir(dok(), dok([dil]), belge())
    assert rapor.eklenen == ["viscosity_thinned"]


# --- Sınır kuraldan gelir -------------------------------------------------------------


def test_kabul_edilen_testin_siniri_modelden_degil_kuraldan_gelir():
    """Model 'not greater than 1 ppm' için alt=0.001 yazdı; kural üst sınır 1 ppm bulur."""
    hibrit, rapor = _hibrit().hibrit_birlestir(dok(), dok([kursun()]), belge())
    t = {t.id: t for t in hibrit.testler}["lead_content"]
    assert t.sinir.kriter_turu == "sayisal"
    assert (t.sinir.alt, t.sinir.ust, t.sinir.birim) == (None, 1, "ppm")
    assert t.sinir.ust_dahil is True
    assert rapor.sayi_atildi == []


def test_sinir_tam_esikte_kuraldan_gelir_birim_modelden_alinmaz():
    """Model birimi 'percent' diye karıştırsa da kural metindeki 'ppm'i yazar."""
    sinir = sayisal(KURSUN_METNI, ust=1, birim="percent")
    hibrit, _ = _hibrit().hibrit_birlestir(dok(), dok([kursun(sinir=sinir)]), belge())
    t = {t.id: t for t in hibrit.testler}["lead_content"]
    assert (t.sinir.ust, t.sinir.birim) == (1, "ppm")


def test_model_sayisal_dedi_metinde_sayi_yok_ise_metinsel_olur_ve_raporlanir():
    sinir = sayisal(KOKU_METNI, ust=5, birim="ppm")
    hibrit, rapor = _hibrit().hibrit_birlestir(dok(), dok([koku(sinir=sinir)]), belge())
    t = {t.id: t for t in hibrit.testler}["odor"]
    assert t.sinir.kriter_turu == "metinsel"
    assert t.sinir.alt is None and t.sinir.ust is None and t.sinir.birim is None
    assert rapor.sayi_atildi == ["odor"]


def test_model_metinsel_dedi_metinsel_kaldi_ise_sayi_atildi_sayilmaz():
    hibrit, rapor = _hibrit().hibrit_birlestir(dok(), dok([koku()]), belge())
    assert rapor.sayi_atildi == []


def test_kabul_edilen_testin_adi_kaynagi_turleri_ve_uygulanabilirligi_modelden_numune_bos():
    kural = kural_dokumani()  # panel_A numunesi var; yine de eklenen teste bağlanmaz
    dil_koku = koku()
    dil_koku = dil_koku.model_copy(update={"numune_hazirlama_id": "panel_A"})
    hibrit, _ = _hibrit().hibrit_birlestir(kural, dok([dil_koku], numune_hazirlama=list(kural.numune_hazirlama)),
                                           belge())
    t = {t.id: t for t in hibrit.testler}["odor"]
    assert t.test_adi == "Odor"
    assert (t.kaynak.madde, t.kaynak.sayfa) == ("3.6.10", 2)
    assert t.test_turleri == {"kabul"}
    assert t.uygulanabilirlik == ["Type I"]
    assert t.numune_hazirlama_id is None


# --- Kimlik çakışması ve rapor -----------------------------------------------------------


def test_kural_testiyle_cakisan_kimlige_dm_eklenir(monkeypatch):
    """Eşleştirici iki kaydı eşleştirmese bile aynı kimlik iki kez yazılmaz: dil modelininkine '_dm' eklenir."""
    hs = _hibrit()
    monkeypatch.setattr(hs, "kaydi_eslestir", lambda a, b: [])
    dil_ayni_kimlik = koku(id="viscosity")
    hibrit, rapor = hs.hibrit_birlestir(kural_dokumani(), dok([dil_ayni_kimlik]), belge())
    assert [t.id for t in hibrit.testler] == ["viscosity", "viscosity_dm"]
    assert hibrit.testler[0] == kural_dokumani().testler[0]
    assert rapor.eklenen == ["viscosity_dm"]


def test_rapor_sayilari_ve_json_sozlugu():
    hs = _hibrit()
    kural = kural_dokumani()
    dil_viskozite = sart("viscosity", "Viscosity", sayisal(VISKOZITE_METNI, ust=60, birim="s"), "3.6.3", 1)
    uydurma = sart("adhesion", "Adhesion", Sinir(kriter_turu="metinsel", orijinal_metin="No removal of coating."),
                   "3.6.11", 2)
    sayili_koku = koku(sinir=sayisal(KOKU_METNI, ust=5, birim="ppm"))
    hibrit, rapor = hs.hibrit_birlestir(kural, dok([dil_viskozite, uydurma, sayili_koku, kursun()]), belge())

    assert isinstance(rapor, hs.HibritRaporu)
    assert rapor.kural_test_sayisi == 1
    assert sorted(rapor.eklenen) == ["lead_content", "odor"]
    assert rapor.kuralla_eslesen == ["viscosity"]
    assert [id_ for id_, _ in rapor.kanitsiz] == ["adhesion"]
    assert rapor.sayi_atildi == ["odor"]
    assert len(hibrit.testler) == 3

    ozet = rapor.sozluk()
    geri = json.loads(json.dumps(ozet, ensure_ascii=False))
    assert geri["kural_test_sayisi"] == 1
    assert sorted(geri["eklenen"]) == ["lead_content", "odor"]
    assert geri["kuralla_eslesen"] == ["viscosity"]
    assert [k[0] for k in geri["kanitsiz"]] == ["adhesion"]
    assert geri["sayi_atildi"] == ["odor"]


def test_hibrit_dokumani_gecerli_kabul_dokumanidir():
    hibrit, _ = _hibrit().hibrit_birlestir(kural_dokumani(), dok([koku(), kursun()]), belge())
    KabulDokumani.model_validate_json(hibrit.model_dump_json())


# --- Kural–model anlaşmazlığı (EK, A maddesi) ----------------------------------------------


def _alanlar(rapor, test_id):
    return sorted(k["alan"] for k in rapor.anlasmazliklar if k["test_id"] == test_id)


def test_ust_sinir_farkli_ise_anlasmazlik_kaydi_olusur():
    """Kural üst 40 s, model üst 30 s: 'ust' anlaşmazlığı, iki değer de metin olarak kayıtta."""
    dil = sart("viscosity", "Viscosity", sayisal(VISKOZITE_METNI, ust=30, birim="s"), "3.6.3", 1)
    _, rapor = _hibrit().hibrit_birlestir(kural_dokumani(), dok([dil]), belge())
    assert len(rapor.anlasmazliklar) == 1
    kayit = rapor.anlasmazliklar[0]
    assert set(kayit) == {"test_id", "model_id", "alan", "kural", "model", "kural_madde", "model_madde"}
    assert kayit["kural_madde"] == kayit["model_madde"] == "3.6.3"
    assert (kayit["test_id"], kayit["model_id"], kayit["alan"]) == ("viscosity", "viscosity", "ust")
    assert isinstance(kayit["kural"], str) and isinstance(kayit["model"], str)
    assert "40" in kayit["kural"] and "30" in kayit["model"]


def test_anlasmazlikli_sayisal_kural_testi_hibritte_yon_belirsiz_olur_sayilar_korunur():
    dil = sart("viscosity", "Viscosity", sayisal(VISKOZITE_METNI, ust=30, birim="s"), "3.6.3", 1)
    hibrit, rapor = _hibrit().hibrit_birlestir(kural_dokumani(), dok([dil]), belge())
    t = hibrit.testler[0]
    assert t.sinir.yon == "belirsiz"
    assert (t.sinir.kriter_turu, t.sinir.alt, t.sinir.ust, t.sinir.birim) == ("sayisal", None, 40, "s")
    assert t.sinir.orijinal_metin == VISKOZITE_METNI
    assert rapor.isaretlenemeyen == []


def test_model_ayni_degeri_bulursa_anlasmazlik_yok_ve_kural_testi_degismez():
    kural = kural_dokumani()
    dil = sart("viscosity", "Viscosity", sayisal(VISKOZITE_METNI, ust=40.0, birim="s"), "3.6.3", 1)
    hibrit, rapor = _hibrit().hibrit_birlestir(kural, dok([dil]), belge())
    assert rapor.anlasmazliklar == []
    assert rapor.anlasmazlik_sayisi == 0 and rapor.anlasmazlikli_test_sayisi == 0
    assert hibrit.testler[0] == kural.testler[0]
    assert hibrit.testler[0].sinir.yon is None


def test_s_ile_second_ayni_birim_sayilir():
    """Birim pint ile karşılaştırılır: 's' ile 'second' aynı birimdir, anlaşmazlık değildir."""
    dil = sart("viscosity", "Viscosity", sayisal(VISKOZITE_METNI, ust=40, birim="second"), "3.6.3", 1)
    hibrit, rapor = _hibrit().hibrit_birlestir(kural_dokumani(), dok([dil]), belge())
    assert rapor.anlasmazliklar == []
    assert hibrit.testler[0].sinir.yon is None


def test_farkli_birim_anlasmazlik_sayilir():
    """Aynı sayı, başka birim (40 s ile 40 minute) birim karışıklığıdır: 'birim' anlaşmazlığı."""
    dil = sart("viscosity", "Viscosity", sayisal(VISKOZITE_METNI, ust=40, birim="minute"), "3.6.3", 1)
    hibrit, rapor = _hibrit().hibrit_birlestir(kural_dokumani(), dok([dil]), belge())
    assert _alanlar(rapor, "viscosity") == ["birim"]
    assert hibrit.testler[0].sinir.yon == "belirsiz"


def test_yon_farki_tek_yon_kaydi_uretir():
    """Kural üst=1 ppm (en çok), model alt=1 ppm (en az): tek hata tek kayıt, yalnız 'yon'."""
    kural = dok([kursun(sinir=sayisal(KURSUN_METNI, ust=1, birim="ppm"))])
    dil = dok([kursun(sinir=sayisal(KURSUN_METNI, alt=1, birim="ppm"))])
    hibrit, rapor = _hibrit().hibrit_birlestir(kural, dil, belge())
    assert _alanlar(rapor, "lead_content") == ["yon"]
    assert rapor.anlasmazlik_sayisi == 1
    assert rapor.anlasmazlikli_test_sayisi == 1
    t = hibrit.testler[0]
    assert (t.sinir.alt, t.sinir.ust, t.sinir.yon) == (None, 1, "belirsiz")


def test_kural_metinsel_model_sayisal_ise_tek_kriter_turu_kaydi_ve_isaretlenemeyen():
    """Kural testi sayısal değil: yalnız 'kriter_turu' kaydı; yön işaretlenemez, doküman değişmez."""
    kural = dok([koku()])
    dil = dok([koku(sinir=sayisal(KOKU_METNI, ust=5, birim="ppm"))])
    hibrit, rapor = _hibrit().hibrit_birlestir(kural, dil, belge())
    assert _alanlar(rapor, "odor") == ["kriter_turu"]
    assert rapor.anlasmazlik_sayisi == 1
    assert rapor.anlasmazlikli_test_sayisi == 1
    assert rapor.isaretlenemeyen == ["odor"]
    assert hibrit.testler == kural.testler


def test_kanitsiz_eslesme_anlasmazlik_uretmez():
    """Eşleşen dil modeli testinin özgün metni sayfasında yoksa anlaşmazlık sayılmaz, kanıtsız yazılır."""
    kural = kural_dokumani()
    uydurma = sart("viscosity", "Viscosity",
                   sayisal("The viscosity shall be not greater than 30 seconds.", ust=30, birim="s"), "3.6.3", 1)
    hibrit, rapor = _hibrit().hibrit_birlestir(kural, dok([uydurma]), belge())
    assert rapor.anlasmazliklar == []
    assert rapor.anlasmazlik_sayisi == 0
    assert "viscosity" in [id_ for id_, _ in rapor.kanitsiz]
    assert hibrit.testler[0] == kural.testler[0]


def test_anlasmazlik_sayilari_kayit_ve_test_bazinda_ayri_sayilir():
    kural = dok([
        sart("viscosity", "Viscosity", sayisal(VISKOZITE_METNI, ust=40, birim="s"), "3.6.3", 1),
        kursun(sinir=sayisal(KURSUN_METNI, ust=1, birim="ppm")),
    ])
    dil = dok([
        sart("viscosity", "Viscosity", sayisal(VISKOZITE_METNI, ust=30, birim="s"), "3.6.3", 1),  # 1 kayıt
        kursun(sinir=sayisal(KURSUN_METNI, alt=1, birim="ppm")),  # yön farkı: 1 kayıt
    ])
    _, rapor = _hibrit().hibrit_birlestir(kural, dil, belge())
    assert rapor.anlasmazlik_sayisi == 2
    assert rapor.anlasmazlikli_test_sayisi == 2
    geri = json.loads(json.dumps(rapor.sozluk(), ensure_ascii=False))
    assert len(geri["anlasmazliklar"]) == 2
    assert geri["isaretlenemeyen"] == []


def test_ayni_yonde_alt_ve_ust_farki_ayri_kayitlardir():
    """Kriter türü ve yön aynı (aralık): alt ve üst ayrı ayrı farklıysa iki kayıt."""
    kural = dok([sart("viscosity", "Viscosity", sayisal(VISKOZITE_METNI, alt=15, ust=40, birim="s"), "3.6.3", 1)])
    dil = dok([sart("viscosity", "Viscosity", sayisal(VISKOZITE_METNI, alt=20, ust=30, birim="s"), "3.6.3", 1)])
    _, rapor = _hibrit().hibrit_birlestir(kural, dil, belge())
    assert _alanlar(rapor, "viscosity") == ["alt", "ust"]
    assert rapor.anlasmazlikli_test_sayisi == 1


def test_model_tarafinda_yon_dogrulamasinin_koydugu_belirsiz_yon_farki_sayilmaz():
    """Model testi yonu_guvenli_yap'tan 'belirsiz' gelmiş ama sayıları kuralla aynı: anlaşmazlık yok."""
    kural = dok([kursun(sinir=sayisal(KURSUN_METNI, ust=1, birim="ppm"))])
    dil = dok([kursun(sinir=sayisal(KURSUN_METNI, ust=1, birim="ppm", yon="belirsiz"))])
    hibrit, rapor = _hibrit().hibrit_birlestir(kural, dil, belge())
    assert rapor.anlasmazliklar == []
    assert hibrit.testler == kural.testler


def test_model_belirsiz_yonlu_ve_sayisi_farkliysa_yalniz_sayi_kaydi():
    """Belirsiz yön yerine modelin alt/üst'ünden türetilen yön (en çok) kullanılır: yalnız 'ust' farkı."""
    kural = dok([kursun(sinir=sayisal(KURSUN_METNI, ust=1, birim="ppm"))])
    dil = dok([kursun(sinir=sayisal(KURSUN_METNI, ust=2, birim="ppm", yon="belirsiz"))])
    _, rapor = _hibrit().hibrit_birlestir(kural, dil, belge())
    assert _alanlar(rapor, "lead_content") == ["ust"]


# --- Madde farkı (D5) -----------------------------------------------------------------


def test_madde_farkliysa_anlasmazlik_sayilmaz_model_testi_kanit_yoluna_gider():
    """Aynı kimlik, başka madde: çift eşleşmemiş sayılır; kanıtlı model testi '_dm' ile eklenir."""
    kural = kural_dokumani()
    dil = sart("viscosity", "Viscosity", sayisal(VISKOZITE_METNI, ust=30, birim="s"), "3.6.5", 1)
    hibrit, rapor = _hibrit().hibrit_birlestir(kural, dok([dil]), belge())
    assert rapor.anlasmazliklar == []
    assert rapor.kuralla_eslesen == []
    assert rapor.eklenen == ["viscosity_dm"]
    assert [t.id for t in hibrit.testler] == ["viscosity", "viscosity_dm"]
    assert hibrit.testler[0] == kural.testler[0]  # kural testi işaretlenmez
    eklenen = hibrit.testler[1]
    assert eklenen.kaynak.madde == "3.6.5"
    assert (eklenen.sinir.ust, eklenen.sinir.birim) == (40, "s")  # sınır yine kuraldan


def test_madde_farkli_ve_kanitsiz_model_testi_alinmaz():
    kural = kural_dokumani()
    dil = sart("viscosity", "Viscosity",
               sayisal("The viscosity shall be not greater than 30 seconds.", ust=30, birim="s"), "3.6.5", 1)
    hibrit, rapor = _hibrit().hibrit_birlestir(kural, dok([dil]), belge())
    assert rapor.anlasmazliklar == []
    assert [id_ for id_, _ in rapor.kanitsiz] == ["viscosity"]
    assert hibrit.testler == kural.testler
