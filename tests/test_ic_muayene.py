"""İç muayene sonucu: katalogda saklanması, hatta girilmesi ve parti kararına bağlanması.

Onaylı karar (proje sahibi): iç muayene sonucu girilmemişse parti "bekliyor"
olur; eksik bilgi hiçbir zaman "uygun" sonucuna yol açmaz. Bkz.
docs/gece_kararlari.md, "81733D / 85285E etiketleme kararlarının uygulanması"
madde 1.

Yeni API henüz yokken bu modülün toplanması (collection) düşmesin diye yeni
adlar test içinde modülden alınır (`kk.ic_muayene_gir`,
`veritabani.IcMuayeneSonucu`); böylece her test kendi sebebiyle başarısız olur.
"""

from __future__ import annotations

import sqlite3

import pytest

from malzeme_kabul.hat import katalog_karari as kk
from malzeme_kabul.hat.katalog_karari import malzeme_koduyla_kontrol
from malzeme_kabul.katalog import veritabani
from malzeme_kabul.katalog.ornek_veri import ornek_yukle
from malzeme_kabul.katalog.veritabani import Katalog, KatalogHatasi
from malzeme_kabul.kayit.denetim_kaydi import DenetimHatasi, DenetimKaydi
from malzeme_kabul.sozlesme.sema import KabulDokumani, Kaynak, Sinir, TestSarti
from tests.conftest import KOK
from tests.test_katalog_karari import dokuman, sertifika

GIRILMEDI = "iç muayene sonucu girilmedi"
KAYIT_HATALARI = (sqlite3.DatabaseError, DenetimHatasi, KatalogHatasi)


def muayene_sarti(id_: str, ad: str, madde: str = "5.3", uyg=()) -> TestSarti:
    return TestSarti(
        id=id_, test_adi=ad,
        sinir=Sinir(kriter_turu="metinsel", orijinal_metin=f"{ad} 5.3'e uygun olmalı"),
        kaynak=Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde=madde),
        test_turleri={"muayene"}, uygulanabilirlik=list(uyg),
    )


def muayeneli_dokuman(*muayeneler: TestSarti) -> KabulDokumani:
    """test_katalog_karari.dokuman() (voc, krom) + verilen muayene şartları."""
    temel = dokuman()
    return temel.model_copy(update={"testler": [*temel.testler, *muayeneler]})


ETIKETLEME = muayene_sarti("etiketleme", "Etiketleme", "5.3")
AMBALAJ = muayene_sarti("ambalaj", "Ambalaj", "5.2")
C2_KAP_ISARETI = muayene_sarti("kap_isareti_c2", "Kap işareti (Class C2)", "5.3.1", ["Class C2"])
UYGULANAN = ("etiketleme", "ambalaj")  # AST-N (Type I Class N) için


@pytest.fixture
def katalog():
    """Muayene şartlı kabul dokümanı onaylı katalog: AST-N (I/N), lotlar L1 ve L2 bekliyor."""
    k = Katalog()
    k.dokuman_onayla(muayeneli_dokuman(ETIKETLEME, AMBALAJ, C2_KAP_ISARETI), "mp1")
    k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
    k.tedarikci_onayla("AST-N", "Ted A")
    k.parti_ekle("L1", "AST-N", "Ted A", "K", "2026-06-01")
    k.parti_ekle("L2", "AST-N", "Ted A", "K", "2026-06-02")
    yield k
    k.kapat()


@pytest.fixture
def defter(katalog):
    return DenetimKaydi(katalog.baglanti)


def uygun_sertifika(lot: str = "L1"):
    """Her bakımdan uygun sertifika (VOC, krom, tedarikçi, parti numarası)."""
    return sertifika().model_copy(update={"parti_no": lot})


def satir_sayisi(k: Katalog) -> int:
    return k.baglanti.execute("SELECT COUNT(*) FROM ic_muayene_sonuclari").fetchone()[0]


def muayene_satirlari(sonuc) -> dict:
    adlar = {"etiketleme", "ambalaj", "kap_isareti_c2"}
    return {s.test_id: s for s in sonuc.ek_denetimler if s.test_id in adlar}


def karar_ver(k: Katalog, d: DenetimKaydi, lot: str | None = "L1", ser=None):
    return malzeme_koduyla_kontrol(
        k, "AST-N", ser or uygun_sertifika(lot or "L1"), lot_no=lot, defter=d, kullanici="gk1"
    )


# --- A. katalog: ic_muayene_sonuclari tablosu ---------------------------------------------------


def test_ic_muayene_sonucu_girilir_ve_alanlariyla_okunur(katalog):
    katalog.ic_muayene_sonucu_gir("AST-N", "L1", "etiketleme", "uygun", "gk1", not_="etiket okunaklı")
    sonuclar = katalog.ic_muayene_sonuclari("AST-N", "L1")
    assert list(sonuclar) == ["etiketleme"]
    s = sonuclar["etiketleme"]
    assert isinstance(s, veritabani.IcMuayeneSonucu)
    assert (s.test_id, s.sonuc, s.kullanici, s.not_) == ("etiketleme", "uygun", "gk1", "etiket okunaklı")
    assert isinstance(s.zaman, str) and s.zaman


def test_not_verilmezse_bos_kalir(katalog):
    katalog.ic_muayene_sonucu_gir("AST-N", "L1", "etiketleme", "uygun_degil", "gk1")
    assert katalog.ic_muayene_sonuclari("AST-N", "L1")["etiketleme"].not_ is None


def test_hic_sonuc_girilmemis_partide_bos_sozluk_doner(katalog):
    assert katalog.ic_muayene_sonuclari("AST-N", "L1") == {}


def test_ayni_test_yeniden_girilirse_son_giris_gecerli_eski_satir_silinmez(katalog):
    katalog.ic_muayene_sonucu_gir("AST-N", "L1", "etiketleme", "uygun", "gk1")
    katalog.ic_muayene_sonucu_gir("AST-N", "L1", "etiketleme", "uygun_degil", "gk2", not_="etiket yırtık")
    son = katalog.ic_muayene_sonuclari("AST-N", "L1")["etiketleme"]
    assert (son.sonuc, son.kullanici, son.not_) == ("uygun_degil", "gk2", "etiket yırtık")
    assert satir_sayisi(katalog) == 2  # geçmiş korunur


def test_sonuclar_parti_bazinda_ayrilir(katalog):
    katalog.ic_muayene_sonucu_gir("AST-N", "L1", "etiketleme", "uygun", "gk1")
    assert katalog.ic_muayene_sonuclari("AST-N", "L2") == {}


@pytest.mark.parametrize("sonuc", ["gecti", "Uygun", "UYGUN_DEGIL", "insan_incelemeli", "", None])
def test_bilinmeyen_sonuc_reddedilir_ve_hicbir_sey_yazilmaz(katalog, sonuc):
    with pytest.raises(KatalogHatasi):
        katalog.ic_muayene_sonucu_gir("AST-N", "L1", "etiketleme", sonuc, "gk1")
    assert satir_sayisi(katalog) == 0


@pytest.mark.parametrize("kullanici", ["", "   ", None])
def test_bos_kullanici_reddedilir_ve_hicbir_sey_yazilmaz(katalog, kullanici):
    with pytest.raises(KatalogHatasi):
        katalog.ic_muayene_sonucu_gir("AST-N", "L1", "etiketleme", "uygun", kullanici)
    assert satir_sayisi(katalog) == 0


@pytest.mark.parametrize("malzeme, lot", [("AST-N", "YOK"), ("YOK", "L1")])
def test_katalogda_olmayan_parti_reddedilir_ve_hicbir_sey_yazilmaz(katalog, malzeme, lot):
    with pytest.raises(KatalogHatasi):
        katalog.ic_muayene_sonucu_gir(malzeme, lot, "etiketleme", "uygun", "gk1")
    assert satir_sayisi(katalog) == 0


@pytest.mark.parametrize("test_id", ["voc", "krom", "yok", ""])
def test_muayene_turunde_olmayan_test_id_reddedilir_ve_hicbir_sey_yazilmaz(katalog, test_id):
    # voc ve krom kabul testidir; sonuçları CoC'den gelir, iç muayeneyle girilemez.
    with pytest.raises(KatalogHatasi):
        katalog.ic_muayene_sonucu_gir("AST-N", "L1", test_id, "uygun", "gk1")
    assert satir_sayisi(katalog) == 0


def test_yalniz_eski_surumdeki_muayene_sarti_icin_sonuc_reddedilir(katalog):
    # Geçerli doküman en son onaylı sürümdür; v2'de ambalaj şartı yok.
    katalog.dokuman_onayla(muayeneli_dokuman(ETIKETLEME), "mp2")
    with pytest.raises(KatalogHatasi):
        katalog.ic_muayene_sonucu_gir("AST-N", "L1", "ambalaj", "uygun", "gk1")
    assert satir_sayisi(katalog) == 0


def test_eski_veritabani_acilinca_tablo_olusur_veri_korunur(tmp_path):
    db = tmp_path / "eski.sqlite"
    k = Katalog(db)
    k.dokuman_onayla(muayeneli_dokuman(ETIKETLEME), "mp1")
    k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
    k.tedarikci_onayla("AST-N", "Ted A")
    k.parti_ekle("L1", "AST-N", "Ted A", "K", "2026-06-01")
    k.baglanti.execute("DROP TABLE IF EXISTS ic_muayene_sonuclari")  # tablodan önceki veritabanı
    k.baglanti.commit()
    k.kapat()
    with Katalog(db) as yeni:
        assert yeni.parti("AST-N", "L1").durum == "bekliyor"
        assert yeni.ic_muayene_sonuclari("AST-N", "L1") == {}
        yeni.ic_muayene_sonucu_gir("AST-N", "L1", "etiketleme", "uygun", "gk1")
        assert yeni.ic_muayene_sonuclari("AST-N", "L1")["etiketleme"].sonuc == "uygun"


# --- B. hat: ic_muayene_gir ---------------------------------------------------------------------


def test_ic_muayene_gir_sonucu_yazar_ve_karar_kaydi_dusurur(katalog, defter):
    kk.ic_muayene_gir(katalog, defter, "gk1", "AST-N", "L1", "etiketleme", "uygun", "etiket tam", rol="giris_kalite")
    assert katalog.ic_muayene_sonuclari("AST-N", "L1")["etiketleme"].kullanici == "gk1"
    (kayit,) = defter.kayitlar("karar")
    assert (kayit.kullanici, kayit.malzeme_kodu, kayit.lot_no) == ("gk1", "AST-N", "L1")
    assert kayit.veri == {"ic_muayene": {"test_id": "etiketleme", "sonuc": "uygun", "not": "etiket tam",
                                         "rol": "giris_kalite"}}


def test_ic_muayene_gir_mp_rolunu_de_kabul_eder(katalog, defter):
    kk.ic_muayene_gir(katalog, defter, "mp1", "AST-N", "L1", "ambalaj", "uygun_degil", rol="mp")
    (kayit,) = defter.kayitlar("karar")
    assert kayit.veri["ic_muayene"] == {"test_id": "ambalaj", "sonuc": "uygun_degil", "not": None, "rol": "mp"}


@pytest.mark.parametrize("rol", ["admin", "", "MP", "giris kalite", None])
def test_ic_muayene_gir_bilinmeyen_rolu_hicbir_sey_yazmadan_reddeder(katalog, defter, rol):
    with pytest.raises(KatalogHatasi):
        kk.ic_muayene_gir(katalog, defter, "gk1", "AST-N", "L1", "etiketleme", "uygun", rol=rol)
    assert satir_sayisi(katalog) == 0 and defter.kayitlar() == []


def test_ic_muayene_gir_rol_anahtar_kelimeyle_zorunlu(katalog, defter):
    with pytest.raises(TypeError):
        kk.ic_muayene_gir(katalog, defter, "gk1", "AST-N", "L1", "etiketleme", "uygun")


def test_ic_muayene_gir_ayri_baglantili_defteri_yazmadan_reddeder(katalog):
    with DenetimKaydi() as baska:
        with pytest.raises(KatalogHatasi, match="aynı bağlantı"):
            kk.ic_muayene_gir(katalog, baska, "gk1", "AST-N", "L1", "etiketleme", "uygun", rol="giris_kalite")
        assert baska.kayitlar() == []
    assert satir_sayisi(katalog) == 0


def test_ic_muayene_kaydi_yazilamazsa_sonuc_da_yazilmaz(katalog, defter):
    katalog.ic_muayene_sonuclari("AST-N", "L1")  # tablo var (yöntem yoksa burada düşer)
    katalog.baglanti.execute(
        "CREATE TRIGGER test_kayit_yazilamaz BEFORE INSERT ON denetim_kaydi "
        "BEGIN SELECT RAISE(ABORT, 'test: denetim kaydı yazılamadı'); END"
    )
    with pytest.raises(KAYIT_HATALARI):
        kk.ic_muayene_gir(katalog, defter, "gk1", "AST-N", "L1", "etiketleme", "uygun", rol="giris_kalite")
    assert satir_sayisi(katalog) == 0


def test_ic_muayene_gir_katalog_reddederse_kayit_yazilmaz(katalog, defter):
    with pytest.raises(KatalogHatasi):
        kk.ic_muayene_gir(katalog, defter, "gk1", "AST-N", "L1", "voc", "uygun", rol="giris_kalite")
    assert defter.kayitlar() == []


@pytest.mark.parametrize("sonuc", ["uygun", "uygun_degil"])
def test_ic_muayene_gir_parti_durumunu_degistirmez(katalog, defter, sonuc):
    kk.ic_muayene_gir(katalog, defter, "gk1", "AST-N", "L1", "etiketleme", sonuc, rol="giris_kalite")
    p = katalog.parti("AST-N", "L1")
    assert p.durum == "bekliyor" and not p.karar_verildi


# --- C. karar: muayene şartları parti kararına girer ---------------------------------------------


def test_her_uygulanan_muayene_sarti_icin_ek_denetim_satiri_eklenir(katalog, defter):
    sonuc = karar_ver(katalog, defter)
    satirlar = muayene_satirlari(sonuc)
    assert set(satirlar) == set(UYGULANAN)
    assert (satirlar["etiketleme"].test_adi, satirlar["etiketleme"].madde) == ("Etiketleme", "5.3")
    assert (satirlar["ambalaj"].test_adi, satirlar["ambalaj"].madde) == ("Ambalaj", "5.2")


def test_sonuc_girilmemisse_muayene_satiri_insan_incelemeli(katalog, defter):
    satirlar = muayene_satirlari(karar_ver(katalog, defter))
    assert set(satirlar) == set(UYGULANAN)
    for s in satirlar.values():
        assert s.karar == "insan_incelemeli" and GIRILMEDI in s.gerekce


def test_sertifika_uygun_olsa_da_muayene_girilmemisse_parti_bekliyor_kalir(katalog, defter):
    sonuc = karar_ver(katalog, defter)
    assert all(s.karar == "uygun" for s in sonuc.kontrol.satirlar)  # sertifika her bakımdan uygun
    assert (sonuc.parti_karari, sonuc.parti_durumu) == ("inceleme", "bekliyor")
    p = katalog.parti("AST-N", "L1")
    assert p.durum == "bekliyor"  # serbest yazılmaz


def test_lot_verilmezse_muayene_satiri_insan_incelemeli_ve_kabul_cikmaz(katalog):
    sonuc = malzeme_koduyla_kontrol(katalog, "AST-N", uygun_sertifika())
    satirlar = muayene_satirlari(sonuc)
    assert set(satirlar) == set(UYGULANAN)
    assert all(s.karar == "insan_incelemeli" and GIRILMEDI in s.gerekce for s in satirlar.values())
    assert sonuc.parti_karari == "inceleme"


def test_lot_verilmezse_baska_lota_girilen_sonuc_kullanilmaz(katalog):
    for t in UYGULANAN:
        katalog.ic_muayene_sonucu_gir("AST-N", "L1", t, "uygun", "gk1")
    sonuc = malzeme_koduyla_kontrol(katalog, "AST-N", uygun_sertifika())
    assert {s.karar for s in muayene_satirlari(sonuc).values()} == {"insan_incelemeli"}
    assert sonuc.parti_karari == "inceleme"


def test_muayenelerden_biri_girilmemisse_parti_bekliyor(katalog, defter):
    katalog.ic_muayene_sonucu_gir("AST-N", "L1", "etiketleme", "uygun", "gk1")
    sonuc = karar_ver(katalog, defter)
    satirlar = muayene_satirlari(sonuc)
    assert satirlar["etiketleme"].karar == "uygun"
    assert satirlar["ambalaj"].karar == "insan_incelemeli" and GIRILMEDI in satirlar["ambalaj"].gerekce
    assert (sonuc.parti_karari, sonuc.parti_durumu) == ("inceleme", "bekliyor")
    assert katalog.parti("AST-N", "L1").durum == "bekliyor"


def test_hepsi_uygun_girilmisse_parti_kabul_ve_serbest(katalog, defter):
    for t in UYGULANAN:
        katalog.ic_muayene_sonucu_gir("AST-N", "L1", t, "uygun", "ayse.gk")
    sonuc = karar_ver(katalog, defter)
    for s in muayene_satirlari(sonuc).values():
        assert s.karar == "uygun" and "ayse.gk" in s.gerekce
    assert (sonuc.parti_karari, sonuc.parti_durumu) == ("kabul", "serbest")
    assert katalog.parti("AST-N", "L1").durum == "serbest"


def test_biri_uygun_degil_girilmisse_parti_red_ve_karantina(katalog, defter):
    katalog.ic_muayene_sonucu_gir("AST-N", "L1", "etiketleme", "uygun", "gk1")
    katalog.ic_muayene_sonucu_gir("AST-N", "L1", "ambalaj", "uygun_degil", "gk2")
    sonuc = karar_ver(katalog, defter)
    ambalaj = muayene_satirlari(sonuc)["ambalaj"]
    assert ambalaj.karar == "uygun_degil" and "gk2" in ambalaj.gerekce
    assert (sonuc.parti_karari, sonuc.parti_durumu) == ("red", "karantina")
    assert katalog.parti("AST-N", "L1").durum == "karantina"


def test_uygun_degil_girilmis_muayene_eksik_muayeneye_ragmen_red_verir(katalog, defter):
    katalog.ic_muayene_sonucu_gir("AST-N", "L1", "etiketleme", "uygun_degil", "gk1")  # ambalaj girilmedi
    sonuc = karar_ver(katalog, defter)
    assert (sonuc.parti_karari, sonuc.parti_durumu) == ("red", "karantina")


def test_son_giris_karari_belirler(katalog, defter):
    for t in UYGULANAN:
        katalog.ic_muayene_sonucu_gir("AST-N", "L1", t, "uygun", "gk1")
    katalog.ic_muayene_sonucu_gir("AST-N", "L1", "etiketleme", "uygun_degil", "gk2")
    sonuc = karar_ver(katalog, defter)
    assert muayene_satirlari(sonuc)["etiketleme"].karar == "uygun_degil"
    assert sonuc.parti_karari == "red"


def test_baska_partiye_girilen_sonuc_bu_partiyi_kabul_ettirmez(katalog, defter):
    for t in UYGULANAN:
        katalog.ic_muayene_sonucu_gir("AST-N", "L2", t, "uygun", "gk1")
    sonuc = karar_ver(katalog, defter, lot="L1")
    assert {s.karar for s in muayene_satirlari(sonuc).values()} == {"insan_incelemeli"}
    assert (sonuc.parti_karari, sonuc.parti_durumu) == ("inceleme", "bekliyor")


def test_uygulanmayan_sinifa_ait_muayene_sarti_satir_uretmez(katalog, defter):
    # kap_isareti_c2 yalnız Class C2 için; AST-N Class N.
    for t in UYGULANAN:
        katalog.ic_muayene_sonucu_gir("AST-N", "L1", t, "uygun", "gk1")
    sonuc = karar_ver(katalog, defter)
    assert "kap_isareti_c2" not in {s.test_id for s in sonuc.ek_denetimler}
    assert sonuc.parti_karari == "kabul"


def test_sinifi_bilinmeyen_malzemede_sinifa_bagli_muayene_sarti_aranir(katalog):
    # uygulanir_mi None (bilinmiyor) → şart uygulanmıyor sayılmaz (is not False).
    katalog.malzeme_ekle("AST-X", "MIL-PRF-23377", "K")  # tip/sınıf yok
    sonuc = malzeme_koduyla_kontrol(katalog, "AST-X", sertifika(atif="MIL-PRF-23377K"))
    satirlar = {s.test_id: s for s in sonuc.ek_denetimler}
    assert satirlar["kap_isareti_c2"].karar == "insan_incelemeli"
    assert sonuc.parti_karari != "kabul"


def test_muayene_satirlari_karar_kaydina_girer(katalog, defter):
    karar_ver(katalog, defter)
    (kayit,) = defter.kayitlar("karar")
    idler = {s["test_id"] for s in kayit.veri["ek_denetimler"]}
    assert set(UYGULANAN) <= idler


def test_her_cagrida_guncel_sonuc_okunur(katalog):
    ilk = malzeme_koduyla_kontrol(katalog, "AST-N", uygun_sertifika(), lot_no="L1", durumu_yaz=False)
    assert ilk.parti_karari == "inceleme"
    for t in UYGULANAN:
        katalog.ic_muayene_sonucu_gir("AST-N", "L1", t, "uygun", "gk1")
    ikinci = malzeme_koduyla_kontrol(katalog, "AST-N", uygun_sertifika(), lot_no="L1", durumu_yaz=False)
    assert ikinci.parti_karari == "kabul"
    assert katalog.parti("AST-N", "L1").durum == "bekliyor"  # durumu_yaz kapalı


# --- regresyon: muayene şartı olmayan doküman ----------------------------------------------------


def test_muayene_sarti_olmayan_dokumanda_davranis_degismez():
    with Katalog() as k:
        k.dokuman_onayla(dokuman(), "mp1")
        k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
        k.tedarikci_onayla("AST-N", "Ted A")
        k.parti_ekle("L1", "AST-N", "Ted A", "K", "2026-06-01")
        sonuc = malzeme_koduyla_kontrol(k, "AST-N", uygun_sertifika(), lot_no="L1",
                                        defter=DenetimKaydi(k.baglanti), kullanici="gk1")
        assert [s.test_id for s in sonuc.ek_denetimler] == [
            "tedarikci", "siparis_revizyonu", "parti_no", "parti_tedarikcisi"]
        assert (sonuc.parti_karari, sonuc.parti_durumu) == ("kabul", "serbest")
        assert k.parti("AST-N", "L1").durum == "serbest"


def test_ornek_23377k_dokumaninda_muayene_satiri_yok():
    with Katalog() as k:
        ornek_yukle(k, KOK / "data/ornek/katalog.json", KOK)
        dok = k.gecerli_dokuman("AST-001").dokuman
        assert not any(t.muayene_sarti for t in dok.testler)  # örnek veri muayene şartı taşımıyor
        sonuc = malzeme_koduyla_kontrol(k, "AST-001", sertifika(atif="MIL-PRF-23377K Type I Class N"))
        assert [s.test_id for s in sonuc.ek_denetimler] == ["tedarikci"]


# --- D. kural modundaki hibrit hat ----------------------------------------------------------------


def test_kural_modu_sertifika_hatti_muayene_satirini_tasir():
    from malzeme_kabul.hat.hibrit_hat import sertifika_hatti

    with Katalog() as k:
        ornek_yukle(k, KOK / "data/ornek/katalog.json", KOK)
        k.tedarikci_onayla("AST-001", "Kurgu Coatings Inc. (kurgusal)")
        dok = k.gecerli_dokuman("AST-001").dokuman
        k.dokuman_onayla(dok.model_copy(update={"testler": [*dok.testler, ETIKETLEME]}), "mp1")
        pdf = KOK / "data/sentetik/sertifikalar/MIL-PRF-23377K/pdf/S-001.pdf"
        karar, _ = sertifika_hatti(k, "AST-001", pdf, mod="kural")
    etiket = [s for s in karar.ek_denetimler if s.test_id == "etiketleme"]
    assert len(etiket) == 1
    assert etiket[0].karar == "insan_incelemeli" and GIRILMEDI in etiket[0].gerekce
    assert etiket[0].madde == "5.3"
    assert karar.parti_karari != "kabul"
