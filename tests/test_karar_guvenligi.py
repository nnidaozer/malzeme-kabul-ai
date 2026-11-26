"""Karar motoru ve parti kuralında yanlış kabule yol açan durumlar (geriye dönük inceleme bulguları K1-K8).

Ortak ilke: emin olunmayan her durum insana bırakılır; hiçbir belirsizlik
"uygun" / "kabul" / "serbest" sonucuna dönüşmez.
"""

from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from malzeme_kabul.hat.katalog_karari import karari_duzelt, malzeme_koduyla_kontrol
from malzeme_kabul.katalog import veritabani
from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.kural.karar_motoru import (
    KararAyarlari,
    kod_normallestir,
    kontrol_et,
    parti_karari,
    sonucu_ayristir,
)
from malzeme_kabul.sozlesme.sema import (
    KabulDokumani,
    Kaynak,
    Sinir,
    StandartBilgisi,
    TanimKaydi,
    TestSarti,
    UrunTanimi,
)
from malzeme_kabul.sozlesme.sertifika import Sertifika, SertifikaSatiri
from tests.test_katalog_karari import _test, denetimli, dokuman, sertifika

_KAYNAK = Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde="1.2")


def _tanim(kod: str) -> TanimKaydi:
    return TanimKaydi(kod=kod, kaynak=_KAYNAK)


def urunlu_dokuman(tipler=("Type I", "Type II"), siniflar=("Class C1", "Class C2", "Class N")) -> KabulDokumani:
    """Ürün tanımı (tip/sınıf listeleri) olan kabul dokümanı; krom şartı yalnız Class N."""
    testler = [_test("voc", "VOC content", 340.0)]
    if "Class N" in siniflar:
        testler.append(_test("krom", "Chromium content", 0.1, ["Class N"], birim="percent"))
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        urun_tanimi=UrunTanimi(tipler=[_tanim(t) for t in tipler], siniflar=[_tanim(s) for s in siniflar]),
        testler=testler,
    )


def _ser(parti_no: str | None = "L1", **kw) -> Sertifika:
    """test_katalog_karari.sertifika + parti numarası."""
    return sertifika(**kw).model_copy(update={"parti_no": parti_no})


def _ek(sonuc, test_id: str):
    satirlar = [s for s in sonuc.ek_denetimler if s.test_id == test_id]
    assert len(satirlar) == 1, f"{test_id} ek denetimi tam bir kez olmalı: {[s.test_id for s in sonuc.ek_denetimler]}"
    return satirlar[0]


def _tip_sinif_satiri(sonuc):
    """Hat sonucunda tip/sınıf satırı: kontrol.tip_sinif ya da ek denetimlerde test_id='tip_sinif'."""
    adaylar = [sonuc.kontrol.tip_sinif] + [s for s in sonuc.ek_denetimler if s.test_id == "tip_sinif"]
    adaylar = [s for s in adaylar if s is not None]
    assert adaylar, "tip_sinif satırı yok"
    return adaylar


@pytest.fixture
def katalog():
    """test_katalog_karari'daki katalogla aynı; ek olarak ikinci onaylı tedarikçi."""
    k = Katalog()
    k.dokuman_onayla(dokuman(), "mp1")
    k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
    k.tedarikci_onayla("AST-N", "Ted A")
    k.tedarikci_onayla("AST-N", "Ted B")
    k.parti_ekle("L1", "AST-N", "Ted A", "K", "2026-06-01")
    yield k
    k.kapat()


@pytest.fixture
def urunlu_katalog():
    """Kabul dokümanı ürün tanımı (tip/sınıf listeleri) içeren katalog."""
    k = Katalog()
    k.dokuman_onayla(urunlu_dokuman(), "mp1")
    yield k
    k.kapat()


# --- K1: olumsuz sonuç metinleri geçti sayılmaz -------------------------------------

OLUMSUZ = [
    "Does not comply",
    "Doesn't comply",
    "Not passed",
    "Did not pass",
    "Not OK",
    "Not satisfactory",
    "Non-conforming",
    "Fail",
    "Kabul edilmedi",
    "Uygun değil",
    # İnceleme turu 2: kara liste bu biçimleri kaçırıyordu (bugün "gecti" ayrıştırılıyorlar).
    "Kabul edilmez",
    "Kabul edilemez",
    "Uygun bulunmadı",
    "Uygun olmayan",
    "Uygun görülmedi",
    "Kabul görmedi",
    "Hasn't passed",
    "Haven't passed",
    "Weren't satisfactory",
    "Couldn't pass",
    "Won't pass",
]
OLUMLU = ["Pass", "Conforms", "Complies", "Uygun", "OK"]

# Geliştirme kümesindeki olumlu yazımlar. data/sentetik/sertifikalar (MIL-PRF-23377K)
# geçti/kaldı satırlarında yalnız "Pass", "Conforms", "Uygun" kullanır; büyük/küçük
# harf ve boşluk farkı normalleştirmeyle aynı ifadeye iner.
GELISTIRME_OLUMLU = ["Pass", "Conforms", "Uygun", "PASS", "pass", "  Conforms  ", "UYGUN"]
# Beyaz listeye göre bilinen olumlu ifade olmayan serbest metinler: geçti sayılmaz.
# "Pass*", "Conforms*" dipnot işareti taşır (koşul dipnotta olabilir); geliştirme verisinde böyle yazım yok.
BILINMEYEN_SERBEST = ["see attached report", "Pass*", "Conforms*", "Pass - see note", "OK per report"]


def _gecti_kaldi_dokumani() -> KabulDokumani:
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        testler=[
            TestSarti(
                id="adhesion", test_adi="Adhesion",
                sinir=Sinir(kriter_turu="gecti_kaldi", orijinal_metin="no removal"),
                kaynak=Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde="3.7.1"),
                test_turleri={"kabul"},
            )
        ],
    )


def _gecti_kaldi_sertifikasi(sonuc: str) -> Sertifika:
    return Sertifika(
        sertifika_no="S", standart_atfi="MIL-PRF-23377K Type I Class N",
        satirlar=[SertifikaSatiri(test_adi="Adhesion", sonuc=sonuc)],
    )


@pytest.mark.parametrize("metin", OLUMSUZ)
def test_olumsuz_sonuc_metni_gecti_olarak_ayristirilmaz(metin):
    assert sonucu_ayristir(metin).tur != "gecti"


@pytest.mark.parametrize("metin", OLUMSUZ)
def test_olumsuz_sonuc_metni_gecti_kaldi_sartinda_uygun_karari_vermez(metin):
    k = kontrol_et(_gecti_kaldi_dokumani(), _gecti_kaldi_sertifikasi(metin))
    satir = next(s for s in k.satirlar if s.test_id == "adhesion")
    assert satir.karar != "uygun"
    assert k.belge_karari != "kabul"


@pytest.mark.parametrize("metin", OLUMLU)
def test_olumlu_sonuc_metni_gecti_olarak_kalir(metin):
    assert sonucu_ayristir(metin).tur == "gecti"
    k = kontrol_et(_gecti_kaldi_dokumani(), _gecti_kaldi_sertifikasi(metin))
    assert [s.karar for s in k.satirlar if s.test_id == "adhesion"] == ["uygun"]


@pytest.mark.parametrize("metin", GELISTIRME_OLUMLU)
def test_gelistirme_kumesindeki_olumlu_yazimlar_gecti_olarak_kalir(metin):
    assert sonucu_ayristir(metin).tur == "gecti"


@pytest.mark.parametrize("metin", BILINMEYEN_SERBEST)
def test_bilinen_olumlu_ifade_olmayan_serbest_metin_gecti_sayilmaz(metin):
    assert sonucu_ayristir(metin).tur != "gecti"


@pytest.mark.parametrize("metin", BILINMEYEN_SERBEST)
def test_bilinen_olumlu_ifade_olmayan_serbest_metin_uygun_karari_vermez(metin):
    k = kontrol_et(_gecti_kaldi_dokumani(), _gecti_kaldi_sertifikasi(metin))
    assert [s.karar for s in k.satirlar if s.test_id == "adhesion"] == ["insan_incelemeli"]
    assert k.belge_karari != "kabul"


# --- K2: makine parti durumunu yalnız daha kısıtlayıcı yöne değiştirir ----------------


def test_yeni_partinin_varsayilan_durumu_bekliyor(katalog):
    assert katalog.parti("AST-N", "L1").durum == "bekliyor"


def test_hic_karar_verilmemis_yeni_parti_uygun_coc_ile_serbest_olur(katalog):
    k = malzeme_koduyla_kontrol(katalog, "AST-N", _ser(), lot_no="L1", **denetimli(katalog))
    assert k.parti_karari == "kabul" and k.parti_durumu == "serbest"
    assert katalog.parti("AST-N", "L1").durum == "serbest"


def test_karantinadaki_parti_uygun_coc_ile_karantinada_kalir_ve_nedeni_gorunur(katalog):
    katalog.parti_ekle("L3", "AST-N", "Ted A", "K", "2026-06-01", durum="karantina")
    k = malzeme_koduyla_kontrol(katalog, "AST-N", _ser("L3"), lot_no="L3", **denetimli(katalog))
    assert katalog.parti("AST-N", "L3").durum == "karantina"
    assert k.parti_durumu == "karantina"
    assert k.parti_karari != "kabul"
    satir = _ek(k, "parti_durumu")
    assert satir.karar == "insan_incelemeli" and "karantina" in satir.gerekce


def test_insan_karantinaya_aldiysa_makinenin_kabul_karari_serbest_birakmaz(katalog):
    defter = DenetimKaydi(katalog.baglanti)
    karari_duzelt(katalog, defter, "mp1", "AST-N", "L1", "karantina", "numune şüpheli")
    k = malzeme_koduyla_kontrol(katalog, "AST-N", _ser(), lot_no="L1", defter=defter, kullanici="gk1")
    assert katalog.parti("AST-N", "L1").durum == "karantina"
    assert k.parti_durumu == "karantina" and k.parti_karari != "kabul"
    assert _ek(k, "parti_durumu").karar == "insan_incelemeli"


def test_insan_beklettiyse_makinenin_kabul_karari_serbest_birakmaz(katalog):
    # Yeni parti de "bekliyor"dur; fark, insanın bu durumu bilerek vermiş olmasıdır.
    defter = DenetimKaydi(katalog.baglanti)
    karari_duzelt(katalog, defter, "mp1", "AST-N", "L1", "bekliyor", "iç laboratuvar sonucu bekleniyor")
    k = malzeme_koduyla_kontrol(katalog, "AST-N", _ser(), lot_no="L1", defter=defter, kullanici="gk1")
    assert katalog.parti("AST-N", "L1").durum == "bekliyor"
    assert k.parti_durumu == "bekliyor" and k.parti_karari != "kabul"
    assert _ek(k, "parti_durumu").karar == "insan_incelemeli"


def test_insan_serbest_biraktiysa_makine_karantinaya_alabilir(katalog):
    defter = DenetimKaydi(katalog.baglanti)
    karari_duzelt(katalog, defter, "mp1", "AST-N", "L1", "serbest", "tekrar test uygun")
    k = malzeme_koduyla_kontrol(katalog, "AST-N", _ser(voc="400"), lot_no="L1", defter=defter, kullanici="gk1")
    assert k.parti_karari == "red" and k.parti_durumu == "karantina"
    assert katalog.parti("AST-N", "L1").durum == "karantina"


def test_makinenin_karantinaya_aldigi_parti_sonraki_uygun_coc_ile_serbest_olmaz(katalog):
    denetim = denetimli(katalog)
    malzeme_koduyla_kontrol(katalog, "AST-N", _ser(voc="400"), lot_no="L1", **denetim)
    k = malzeme_koduyla_kontrol(katalog, "AST-N", _ser(), lot_no="L1", **denetim)
    assert katalog.parti("AST-N", "L1").durum == "karantina"
    assert k.parti_durumu == "karantina" and k.parti_karari != "kabul"


def test_makinenin_beklettigi_parti_sonraki_uygun_coc_ile_serbest_olmaz(katalog):
    # Varsayım: "hiç karar verilmemiş" yalnız yeni eklenmiş partidir; makinenin
    # önceki "inceleme" kararı da karardır, serbest bırakmayı insan yapar.
    denetim = denetimli(katalog)
    malzeme_koduyla_kontrol(katalog, "AST-N", _ser(krom=None), lot_no="L1", **denetim)  # krom eksik -> inceleme
    assert katalog.parti("AST-N", "L1").durum == "bekliyor"
    k = malzeme_koduyla_kontrol(katalog, "AST-N", _ser(), lot_no="L1", **denetim)
    assert katalog.parti("AST-N", "L1").durum == "bekliyor"
    assert k.parti_durumu == "bekliyor" and k.parti_karari != "kabul"


# --- K2 göçü: durum_kaynagi sütunu olmayan eski veritabanı ---------------------------------


def _partiler_sutunlari(yol) -> set[str]:
    b = sqlite3.connect(yol)
    try:
        return {s[1] for s in b.execute("PRAGMA table_info(partiler)")}
    finally:
        b.close()


@pytest.fixture
def eski_katalog_yolu(tmp_path):
    """`partiler.durum_kaynagi` sütunundan önceki şemada, içinde "bekliyor" L1 partisi olan katalog dosyası.

    Katalog bugünkü kodla doldurulur, sonra sütun düşürülerek eski şema elde edilir.
    """
    yol = tmp_path / "eski_katalog.sqlite"
    k = Katalog(yol)
    k.dokuman_onayla(dokuman(), "mp1")
    k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
    k.tedarikci_onayla("AST-N", "Ted A")
    k.parti_ekle("L1", "AST-N", "Ted A", "K", "2026-06-01")
    k.kapat()
    b = sqlite3.connect(yol)
    b.execute("ALTER TABLE partiler DROP COLUMN durum_kaynagi")
    b.commit()
    b.close()
    assert "durum_kaynagi" not in _partiler_sutunlari(yol)
    return yol


def test_eski_veritabanindaki_partiye_goc_bilinmiyor_kaynagi_yazar(eski_katalog_yolu):
    with Katalog(eski_katalog_yolu) as k:
        assert "durum_kaynagi" in _partiler_sutunlari(eski_katalog_yolu)
        p = k.parti("AST-N", "L1")
        assert p.durum == "bekliyor" and p.durum_kaynagi == "bilinmiyor"
        assert p.karar_verildi


def test_eski_veritabanindaki_bekleyen_parti_makinenin_kabul_karariyla_serbest_olmaz(eski_katalog_yolu):
    with Katalog(eski_katalog_yolu) as k:
        sonuc = malzeme_koduyla_kontrol(k, "AST-N", _ser(), lot_no="L1", **denetimli(k))
        assert sonuc.parti_karari != "kabul"
        assert sonuc.parti_durumu == "bekliyor"
        assert k.parti("AST-N", "L1").durum == "bekliyor"
        assert _ek(sonuc, "parti_durumu").karar == "insan_incelemeli"


def test_goc_sonrasi_eklenen_yeni_parti_uygun_coc_ile_serbest_olur(eski_katalog_yolu):
    with Katalog(eski_katalog_yolu) as k:
        k.parti_ekle("L2", "AST-N", "Ted A", "K", "2026-06-02")
        assert k.parti("AST-N", "L2").durum_kaynagi is None  # göç doldurması yalnız eski satırlara
        sonuc = malzeme_koduyla_kontrol(k, "AST-N", _ser("L2"), lot_no="L2", **denetimli(k))
        assert sonuc.parti_karari == "kabul" and sonuc.parti_durumu == "serbest"
        assert k.parti("AST-N", "L2").durum == "serbest"
        assert k.parti("AST-N", "L1").durum == "bekliyor"  # eski parti etkilenmez


def test_goc_ikinci_acilista_yeni_partinin_bos_kaynagini_ezmez(eski_katalog_yolu):
    with Katalog(eski_katalog_yolu) as k:
        k.parti_ekle("L2", "AST-N", "Ted A", "K", "2026-06-02")
    with Katalog(eski_katalog_yolu) as k:
        assert k.parti("AST-N", "L2").durum_kaynagi is None
        assert k.parti("AST-N", "L1").durum_kaynagi == "bilinmiyor"


_GOC_ANAHTARI = ("partiler", "durum_kaynagi")
_BOZUK_DOLDURMA = "UPDATE partiler SET olmayan_sutun = 'bilinmiyor'"  # çalışınca OperationalError


def _bos_kaynakli_satirlar(yol) -> int | None:
    """durum_kaynagi NULL olan parti sayısı; sütun yoksa None."""
    if "durum_kaynagi" not in _partiler_sutunlari(yol):
        return None
    b = sqlite3.connect(yol)
    try:
        return b.execute("SELECT COUNT(*) FROM partiler WHERE durum_kaynagi IS NULL").fetchone()[0]
    finally:
        b.close()


def test_goc_doldurmasi_basarisiz_olursa_sutun_bos_kaynakla_kalmaz(eski_katalog_yolu, monkeypatch):
    # Sütun eklenir ama doldurma düşerse eski partiler "hiç karar verilmedi" (NULL) görünür.
    # Göç atomik olmalı: ya sütun hiç eklenmemiş (sonraki açılış yeniden dener) ya da satırlar dolu.
    monkeypatch.setitem(veritabani.GOC_DOLDURMA, _GOC_ANAHTARI, _BOZUK_DOLDURMA)
    with pytest.raises(Exception):  # hata yutulmaz; türü uygulamaya kalır
        Katalog(eski_katalog_yolu)
    assert _bos_kaynakli_satirlar(eski_katalog_yolu) in (None, 0)


def test_goc_doldurmasi_basarisiz_olduktan_sonra_eski_bekleyen_parti_serbest_olmaz(eski_katalog_yolu, monkeypatch):
    with monkeypatch.context() as m:
        m.setitem(veritabani.GOC_DOLDURMA, _GOC_ANAHTARI, _BOZUK_DOLDURMA)
        with pytest.raises(Exception):
            Katalog(eski_katalog_yolu)
    # Sonraki açılış doğru doldurmayla.
    with Katalog(eski_katalog_yolu) as k:
        assert k.parti("AST-N", "L1").durum_kaynagi == "bilinmiyor"
        sonuc = malzeme_koduyla_kontrol(k, "AST-N", _ser(), lot_no="L1", **denetimli(k))
        assert sonuc.parti_karari != "kabul"
        assert k.parti("AST-N", "L1").durum == "bekliyor"


# --- K2: durum_kaynagi değer kısıtı ve açık kaynak ------------------------------------


def _ham_parti_ekle(k: Katalog, lot: str, kaynak) -> None:
    k.baglanti.execute(
        "INSERT INTO partiler (lot_no, malzeme_kodu, tedarikci, siparis_revizyonu, uretim_tarihi, durum_kaynagi)"
        " VALUES (?, 'AST-N', 'Ted A', 'K', '2026-06-01', ?)",
        (lot, kaynak),
    )


@pytest.mark.parametrize("kaynak", ["xyz", "", "Makine", "INSAN"])
def test_yeni_semada_gecersiz_durum_kaynagi_eklenemez(katalog, kaynak):
    with pytest.raises(sqlite3.IntegrityError):
        _ham_parti_ekle(katalog, "LX", kaynak)


def test_yeni_semada_gecersiz_durum_kaynagi_guncellenemez(katalog):
    with pytest.raises(sqlite3.IntegrityError):
        katalog.baglanti.execute("UPDATE partiler SET durum_kaynagi = 'xyz' WHERE lot_no = 'L1'")


@pytest.mark.parametrize("kaynak", [None, "makine", "insan", "bilinmiyor"])
def test_yeni_semada_gecerli_durum_kaynaklari_eklenebilir(katalog, kaynak):
    _ham_parti_ekle(katalog, "LY", kaynak)
    assert katalog.parti("AST-N", "LY").durum_kaynagi == kaynak


def test_parti_durumu_ata_kaynak_verilmezse_hata_verir(katalog):
    with pytest.raises(TypeError):
        katalog.parti_durumu_ata("AST-N", "L1", "serbest")
    assert katalog.parti("AST-N", "L1").durum == "bekliyor"


# --- K3: parti numarası ve partinin tedarikçisi ------------------------------------------


@pytest.mark.parametrize("parti_no", ["L1", "l1", "  L1  "])
def test_sertifikadaki_parti_no_lot_ile_tutarsa_uygun(katalog, parti_no):
    k = malzeme_koduyla_kontrol(katalog, "AST-N", _ser(parti_no), lot_no="L1", **denetimli(katalog))
    assert _ek(k, "parti_no").karar == "uygun"


@pytest.mark.parametrize("parti_no", [None, "", "L2", "L10"])
def test_sertifikadaki_parti_no_yoksa_ya_da_tutmuyorsa_insan_incelemeli(katalog, parti_no):
    k = malzeme_koduyla_kontrol(katalog, "AST-N", _ser(parti_no), lot_no="L1", **denetimli(katalog))
    assert _ek(k, "parti_no").karar == "insan_incelemeli"
    assert k.parti_karari != "kabul" and katalog.parti("AST-N", "L1").durum != "serbest"


@pytest.mark.parametrize("tedarikci", ["Ted A", "ted a", "  TED   A "])
def test_sertifikadaki_tedarikci_partinin_tedarikcisiyle_tutarsa_uygun(katalog, tedarikci):
    k = malzeme_koduyla_kontrol(katalog, "AST-N", _ser(tedarikci=tedarikci), lot_no="L1", **denetimli(katalog))
    assert _ek(k, "parti_tedarikcisi").karar == "uygun"


def test_onayli_ama_partinin_tedarikcisi_olmayan_firma_insan_incelemeli(katalog):
    k = malzeme_koduyla_kontrol(katalog, "AST-N", _ser(tedarikci="Ted B"), lot_no="L1", **denetimli(katalog))
    assert _ek(k, "tedarikci").karar == "uygun"  # Ted B onaylı listede
    assert _ek(k, "parti_tedarikcisi").karar == "insan_incelemeli"  # ama L1'in tedarikçisi Ted A
    assert k.parti_karari != "kabul"


def test_lot_verilmezse_parti_denetimleri_eklenmez(katalog):
    k = malzeme_koduyla_kontrol(katalog, "AST-N", _ser())
    ids = [s.test_id for s in k.ek_denetimler]
    assert "parti_no" not in ids and "parti_tedarikcisi" not in ids


# --- K4: sertifikada tedarikçi yoksa ---------------------------------------------------


def test_sertifikada_tedarikci_yoksa_tedarikci_denetimi_insan_incelemeli(katalog):
    k = malzeme_koduyla_kontrol(katalog, "AST-N", _ser(tedarikci=None))
    satir = _ek(k, "tedarikci")
    assert satir.karar == "insan_incelemeli" and "sertifikada tedarikçi yok" in satir.gerekce
    assert k.parti_karari != "kabul"


# --- K5: katalogda tip/sınıf tanımsız ---------------------------------------------------


def test_katalogda_tip_ve_sinif_tanimsizsa_sertifikadaki_atfa_dusulmez(urunlu_katalog):
    urunlu_katalog.malzeme_ekle("AST-X", "MIL-PRF-23377", "K", tip=None, sinif=None)
    urunlu_katalog.tedarikci_onayla("AST-X", "Ted A")
    k = malzeme_koduyla_kontrol(urunlu_katalog, "AST-X", sertifika(atif="MIL-PRF-23377K Type I Class N"))
    satirlar = _tip_sinif_satiri(k)
    assert any(s.karar == "insan_incelemeli" and "katalogda tip/sınıf tanımsız" in s.gerekce for s in satirlar)
    assert k.parti_karari != "kabul"


def test_katalogda_yalniz_sinif_tanimsizsa_tip_sinif_insan_incelemeli(urunlu_katalog):
    urunlu_katalog.malzeme_ekle("AST-Y", "MIL-PRF-23377", "K", tip="I", sinif=None)
    urunlu_katalog.tedarikci_onayla("AST-Y", "Ted A")
    k = malzeme_koduyla_kontrol(urunlu_katalog, "AST-Y", sertifika(atif="MIL-PRF-23377K Type I Class N"))
    satirlar = _tip_sinif_satiri(k)
    assert any(s.karar == "insan_incelemeli" and "katalogda tip/sınıf tanımsız" in s.gerekce for s in satirlar)
    assert k.parti_karari != "kabul"


def test_kontrol_et_urun_tanimli_dokumanda_eksik_sinifi_insana_birakir():
    k = kontrol_et(urunlu_dokuman(), sertifika(atif="MIL-PRF-23377K Type I Class N"), tip="I", sinif=None)
    assert k.tip_sinif is not None and k.tip_sinif.karar == "insan_incelemeli"
    assert "katalogda tip/sınıf tanımsız" in k.tip_sinif.gerekce
    assert k.belge_karari != "kabul"


def _yalniz_voc_dokumani(urun_tanimi: UrunTanimi | None = None) -> KabulDokumani:
    """Hiçbir kabul testi tip ya da sınıfa bağlı değil."""
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        urun_tanimi=urun_tanimi,
        testler=[_test("voc", "VOC content", 340.0)],
    )


def _tipe_bagli_dokuman() -> KabulDokumani:
    """Ürün tanımı yok; bir kabul testi yalnız Type II için."""
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        testler=[
            _test("voc", "VOC content", 340.0),
            _test("krom", "Chromium content", 0.1, ["Type II"], birim="percent"),
        ],
    )


def test_urun_tanimi_yokken_sinifa_bagli_kabul_testi_varsa_tanimsiz_sinif_insan_incelemeli():
    # dokuman(): urun_tanimi yok, krom kabul testi yalnız Class N. Katalogda tip ve sınıf yok.
    with Katalog() as kat:
        kat.dokuman_onayla(dokuman(), "mp1")
        kat.malzeme_ekle("AST-Z", "MIL-PRF-23377", "K", tip=None, sinif=None)
        kat.tedarikci_onayla("AST-Z", "Ted A")
        k = malzeme_koduyla_kontrol(kat, "AST-Z", sertifika())
        assert any(s.karar == "insan_incelemeli" for s in _tip_sinif_satiri(k))
        assert k.parti_karari != "kabul"


def test_kontrol_et_urun_tanimi_yokken_sinifa_bagli_test_ve_tanimsiz_sinif_insan_incelemeli():
    k = kontrol_et(dokuman(), sertifika(), tip="I", sinif=None, katalogdan=True)
    assert k.tip_sinif is not None and k.tip_sinif.karar == "insan_incelemeli"
    assert k.belge_karari != "kabul"


def test_kontrol_et_urun_tanimi_yokken_tipe_bagli_test_ve_tanimsiz_tip_insan_incelemeli():
    k = kontrol_et(_tipe_bagli_dokuman(), sertifika(atif="MIL-PRF-23377K Type II Class N"), tip=None, sinif="N",
                   katalogdan=True)
    assert k.tip_sinif is not None and k.tip_sinif.karar == "insan_incelemeli"
    assert k.belge_karari != "kabul"


def test_tanimsiz_tip_sinifa_bagli_test_olmayan_boyutta_ise_uygun_kalir():
    # krom yalnız sınıfa bağlı; katalogda tip yok ama hiçbir test tipe bağlı değil.
    k = kontrol_et(dokuman(), sertifika(), tip=None, sinif="N", katalogdan=True)
    assert k.tip_sinif is not None and k.tip_sinif.karar == "uygun"
    assert k.belge_karari == "kabul"


def test_sinifa_bagli_test_yalniz_yeterlilik_testiyse_tanimsiz_sinif_uygun_kalir():
    yeterlilik = _test("krom", "Chromium content", 0.1, ["Class N"], birim="percent").model_copy(
        update={"test_turleri": {"yeterlilik"}}
    )
    d = KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        testler=[_test("voc", "VOC content", 340.0), yeterlilik],
    )
    k = kontrol_et(d, sertifika(krom=None), tip="I", sinif=None, katalogdan=True)
    assert k.tip_sinif is not None and k.tip_sinif.karar == "uygun"
    assert k.belge_karari == "kabul"


def test_urun_tanimi_yok_ve_hicbir_test_tip_sinifa_bagli_degilse_tanimsiz_tip_sinif_uygun():
    with Katalog() as kat:
        kat.dokuman_onayla(_yalniz_voc_dokumani(), "mp1")
        kat.malzeme_ekle("AST-Z", "MIL-PRF-23377", "K", tip=None, sinif=None)
        kat.tedarikci_onayla("AST-Z", "Ted A")
        k = malzeme_koduyla_kontrol(kat, "AST-Z", sertifika(krom=None))
        assert all(s.karar == "uygun" for s in _tip_sinif_satiri(k))
        assert k.parti_karari == "kabul"


def test_urun_tanimi_listeleri_bos_ve_hicbir_test_tip_sinifa_bagli_degilse_tanimsiz_tip_sinif_uygun():
    with Katalog() as kat:
        kat.dokuman_onayla(_yalniz_voc_dokumani(UrunTanimi()), "mp1")
        kat.malzeme_ekle("AST-Z", "MIL-PRF-23377", "K", tip=None, sinif=None)
        kat.tedarikci_onayla("AST-Z", "Ted A")
        k = malzeme_koduyla_kontrol(kat, "AST-Z", sertifika(krom=None))
        assert all(s.karar == "uygun" for s in _tip_sinif_satiri(k))
        assert k.parti_karari == "kabul"


# --- K6: boş karar listesi ve uygulanan test yok -----------------------------------------


def test_bos_karar_listesi_kabul_degil_inceleme():
    assert parti_karari([]) == "inceleme"


@pytest.mark.parametrize("bilinmeyen", ["bilinmeyen", "", "kabul", "UYGUN"])
def test_bilinmeyen_karar_degeri_kabul_vermez(bilinmeyen):
    assert parti_karari(["uygun", bilinmeyen]) != "kabul"


def test_uygulanan_kabul_testi_yoksa_belge_karari_inceleme():
    d = KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        testler=[_test("krom", "Chromium content", 0.1, ["Class N"], birim="percent")],
    )
    k = kontrol_et(d, sertifika(atif="MIL-PRF-23377K Type I Class C2", krom=None), tip="I", sinif="C2")
    assert k.belge_karari == "inceleme"
    assert any(s.karar == "insan_incelemeli" and "uygulanan kabul testi yok" in s.gerekce for s in k.satirlar)


def test_kabul_testi_hic_olmayan_dokumanla_belge_karari_inceleme():
    d = KabulDokumani(standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"), testler=[])
    k = kontrol_et(d, sertifika())
    assert k.belge_karari == "inceleme"
    assert any(s.karar == "insan_incelemeli" and "uygulanan kabul testi yok" in s.gerekce for s in k.satirlar)


# --- K7: katalogdaki kod kabul dokümanının listesinde yok -------------------------------


@pytest.mark.parametrize("sinif", ["C", "X"])
def test_katalogdaki_sinif_dokumanin_listesinde_yoksa_insan_incelemeli(sinif):
    k = kontrol_et(urunlu_dokuman(), sertifika(atif="MIL-PRF-23377K", krom=None), tip="I", sinif=sinif)
    assert k.tip_sinif is not None and k.tip_sinif.karar == "insan_incelemeli"
    assert k.belge_karari != "kabul"


def test_katalogdaki_tip_dokumanin_listesinde_yoksa_insan_incelemeli():
    k = kontrol_et(urunlu_dokuman(), sertifika(atif="MIL-PRF-23377K"), tip="III", sinif="N")
    assert k.tip_sinif.karar == "insan_incelemeli" and k.belge_karari != "kabul"


def test_tanimsiz_sinifli_malzemenin_partisi_serbest_olmaz(urunlu_katalog):
    urunlu_katalog.malzeme_ekle("AST-C", "MIL-PRF-23377", "K", tip="I", sinif="C")
    urunlu_katalog.tedarikci_onayla("AST-C", "Ted A")
    urunlu_katalog.parti_ekle("L9", "AST-C", "Ted A", "K", "2026-06-01")
    k = malzeme_koduyla_kontrol(urunlu_katalog, "AST-C", _ser("L9", atif="MIL-PRF-23377K", krom=None), lot_no="L9", **denetimli(urunlu_katalog))
    assert k.parti_karari != "kabul" and urunlu_katalog.parti("AST-C", "L9").durum != "serbest"


@pytest.mark.parametrize(
    "tip, sinif, krom_aranir",
    [("1", "n", True), ("i", "N", True), ("I", "c2", False), ("2", "C1", False),
     ("I", "Class N", True), ("Type I", "class n", True), ("Type II", "Class C2", False)],
)
def test_gecerli_kod_donusumleri_listede_bulunur(tip, sinif, krom_aranir):
    s = sertifika(atif="MIL-PRF-23377K", krom="0.05" if krom_aranir else None)
    k = kontrol_et(urunlu_dokuman(), s, tip=tip, sinif=sinif)
    assert k.tip_sinif.karar == "uygun"
    assert ("krom" in [x.test_id for x in k.satirlar]) is krom_aranir
    assert k.belge_karari == "kabul"


# --- K7 (tur 3): ürün tanımı olmayan dokümanda biçimsiz katalog kodları -------------------
# data/cikti/MIL-PRF-23377K_kabul_dokumani.json'da urun_tanimi yok; kod listesi denetimi
# çalışmaz. Katalogdaki "Class N" bugün "CLASS N" olur, {"N"} içinde bulunmaz ve krom
# şartı sessizce düşer. dokuman(): urun_tanimi yok, krom yalnız Class N.


@pytest.mark.parametrize(
    "ham, beklenen",
    [
        ("Class N", "N"), ("class n", "N"), ("CLASS  N", "N"), (" Class N ", "N"),
        ("C 2", "C2"), ("Class C 2", "C2"), ("c1", "C1"),
        ("Type I", "I"), ("type 1", "I"), ("Type II", "II"), ("TYPE 2", "II"),
    ],
)
def test_katalog_kodundaki_type_class_oneki_ve_bosluklar_atilir(ham, beklenen):
    assert kod_normallestir(ham) == beklenen


@pytest.mark.parametrize("ham, beklenen", [("1", "I"), ("2", "II"), ("n", "N"), ("C2", "C2"), (None, None), ("  ", None)])
def test_katalog_kodunun_mevcut_normallestirmesi_korunur(ham, beklenen):
    assert kod_normallestir(ham) == beklenen


@pytest.mark.parametrize("sinif", ["Class N", "class n", "CLASS N"])
def test_onekli_sinif_kodunda_sinifa_bagli_test_uygulanir(sinif):
    k = kontrol_et(dokuman(), sertifika(atif="MIL-PRF-23377K"), tip="I", sinif=sinif, katalogdan=True)
    assert "krom" in [x.test_id for x in k.satirlar]
    assert k.tip_sinif is not None and k.tip_sinif.karar == "uygun"
    assert k.belge_karari == "kabul"


def test_onekli_sinif_kodunda_sinir_disi_krom_red_verir():
    k = kontrol_et(dokuman(), sertifika(atif="MIL-PRF-23377K", krom="0.5"), tip="I", sinif="Class N", katalogdan=True)
    assert [x.karar for x in k.satirlar if x.test_id == "krom"] == ["uygun_degil"]
    assert k.belge_karari == "red"


def test_onekli_sinif_kodunda_eksik_krom_sonucu_kabul_vermez(katalog):
    katalog.malzeme_ekle("AST-P", "MIL-PRF-23377", "K", tip="Type I", sinif="Class N")
    katalog.tedarikci_onayla("AST-P", "Ted A")
    katalog.parti_ekle("L5", "AST-P", "Ted A", "K", "2026-06-01")
    k = malzeme_koduyla_kontrol(katalog, "AST-P", _ser("L5", krom=None), lot_no="L5", **denetimli(katalog))
    assert "krom" in [x.test_id for x in k.kontrol.satirlar]
    assert k.parti_karari != "kabul" and katalog.parti("AST-P", "L5").durum != "serbest"


@pytest.mark.parametrize("sinif", ["C 2", "Class C2", "C1"])
def test_gecerli_sinif_kodunda_yalniz_class_n_testi_uygulanmaz(sinif):
    k = kontrol_et(dokuman(), sertifika(atif="MIL-PRF-23377K", krom=None), tip="I", sinif=sinif, katalogdan=True)
    assert "krom" not in [x.test_id for x in k.satirlar]
    assert k.tip_sinif is not None and k.tip_sinif.karar == "uygun"
    assert k.belge_karari == "kabul"


@pytest.mark.parametrize("sinif", ["X", "Z9", "C3", "Class X"])
def test_urun_tanimi_yokken_bilinmeyen_sinif_kodu_insan_incelemeli(sinif):
    k = kontrol_et(dokuman(), sertifika(atif="MIL-PRF-23377K", krom=None), tip="I", sinif=sinif, katalogdan=True)
    assert k.tip_sinif is not None and k.tip_sinif.karar == "insan_incelemeli"
    assert k.belge_karari != "kabul"


@pytest.mark.parametrize("tip", ["Type III", "III", "IV"])
def test_urun_tanimi_yokken_bilinmeyen_tip_kodu_insan_incelemeli(tip):
    k = kontrol_et(dokuman(), sertifika(atif="MIL-PRF-23377K"), tip=tip, sinif="N", katalogdan=True)
    assert k.tip_sinif is not None and k.tip_sinif.karar == "insan_incelemeli"
    assert k.belge_karari != "kabul"


@pytest.mark.parametrize("tip", ["I", "II", "Type II"])
def test_urun_tanimi_yokken_bilinen_tip_kodu_uygun(tip):
    k = kontrol_et(dokuman(), sertifika(atif="MIL-PRF-23377K"), tip=tip, sinif="N", katalogdan=True)
    assert k.tip_sinif is not None and k.tip_sinif.karar == "uygun"
    assert k.belge_karari == "kabul"


def test_urun_tanimi_yokken_bilinmeyen_sinifli_malzemenin_partisi_serbest_olmaz(katalog):
    katalog.malzeme_ekle("AST-X", "MIL-PRF-23377", "K", tip="I", sinif="X")
    katalog.tedarikci_onayla("AST-X", "Ted A")
    katalog.parti_ekle("L6", "AST-X", "Ted A", "K", "2026-06-01")
    k = malzeme_koduyla_kontrol(katalog, "AST-X", _ser("L6", krom=None), lot_no="L6", **denetimli(katalog))
    assert any(s.karar == "insan_incelemeli" for s in _tip_sinif_satiri(k))
    assert k.parti_karari != "kabul" and katalog.parti("AST-X", "L6").durum != "serbest"


# --- K8: politika ayarları "uygun" olamaz ---------------------------------------------


@pytest.mark.parametrize("alan", ["eksik_test", "yanlis_revizyon"])
def test_karar_ayarinda_uygun_reddedilir(alan):
    with pytest.raises(ValidationError):
        KararAyarlari(**{alan: "uygun"})


@pytest.mark.parametrize("alan", ["eksik_test", "yanlis_revizyon"])
@pytest.mark.parametrize("deger", ["insan_incelemeli", "uygun_degil"])
def test_karar_ayarinda_kisitlayici_degerler_kabul_edilir(alan, deger):
    assert getattr(KararAyarlari(**{alan: deger}), alan) == deger
