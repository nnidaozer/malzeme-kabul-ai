"""Denetim kaydı güvenliği: retro incelemesindeki bulgular (B1-B10, karar motoru S4).

Her test bir bulguyu tarif eder; bulgu kodu docstring'dedir. Kayıt yazılamama
durumu, denetim tablosuna testte eklenen ve her INSERT'i reddeden bir
tetikleyiciyle (gerçek bir veritabanı hatası) üretilir.
"""

from __future__ import annotations

import functools
import importlib
import os
import sqlite3
import subprocess
import sys
import threading
import warnings
from types import SimpleNamespace
from unittest import mock

import pytest

from malzeme_kabul.arayuz import ekran_verisi as ev
from malzeme_kabul.hat.katalog_karari import dokuman_onayla, karari_duzelt, malzeme_koduyla_kontrol
from malzeme_kabul.hat.revizyon_etkisi import mp_incelemesini_kapat, yeni_revizyon_yukle
from malzeme_kabul.katalog.veritabani import Katalog, KatalogHatasi
from malzeme_kabul.kayit.denetim_kaydi import DenetimHatasi, DenetimKaydi
from malzeme_kabul.sozlesme.sema import KabulDokumani, StandartBilgisi
from tests.conftest import KOK, betik_yukle
from tests.test_katalog_karari import dokuman, sertifika

KAYIT_HATALARI = (sqlite3.DatabaseError, DenetimHatasi, KatalogHatasi)


def _kayit_yazilamaz(baglanti: sqlite3.Connection) -> None:
    """Bundan sonra denetim kaydına yazılan her kayıt veritabanında reddedilir."""
    baglanti.execute(
        "CREATE TRIGGER test_kayit_yazilamaz BEFORE INSERT ON denetim_kaydi "
        "BEGIN SELECT RAISE(ABORT, 'test: denetim kaydı yazılamadı'); END"
    )
    baglanti.commit()


@pytest.fixture
def katalog_ve_defter():
    k = Katalog()
    d = DenetimKaydi(k.baglanti)
    dokuman_onayla(k, d, dokuman(), "mp1", "ilk onay")
    k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
    k.tedarikci_onayla("AST-N", "Ted A")
    k.parti_ekle("L1", "AST-N", "Ted A", "K", "2026-06-01")  # durum: bekliyor
    yield k, d
    k.kapat()


def _dok(belge_no="MIL-PRF-23377", rev="J"):
    return KabulDokumani(standart=StandartBilgisi(belge_no=belge_no, revizyon=rev))


@pytest.fixture
def mp_katalog():
    """AST-J, J revizyonunda; K yüklenmiş, M&P incelemesi bekliyor."""
    k = Katalog()
    d = DenetimKaydi(k.baglanti)
    k.dokuman_onayla(_dok(rev="J"), "mp1")
    k.malzeme_ekle("AST-J", "MIL-PRF-23377", "J", tip="I", sinif="N")
    k.tedarikci_onayla("AST-J", "Ted A")
    k.parti_ekle("L1", "AST-J", "Ted A", "J", "2026-01-01", durum="serbest")
    yeni_revizyon_yukle(k, "MIL-PRF-23377", "K", "mp1")
    assert k.malzeme("AST-J").mp_inceleme
    yield k, d
    k.kapat()


# --- B1: durum değişimi ve kaydı tek işlem ------------------------------------------------------


def test_karar_kaydi_yazilamazsa_parti_durumu_degismez(katalog_ve_defter):
    """B1: malzeme_koduyla_kontrol durumu yazar ama kayıt yazılamazsa durum geri alınır."""
    k, d = katalog_ve_defter
    _kayit_yazilamaz(k.baglanti)
    with pytest.raises(KAYIT_HATALARI):
        # VOC sınır dışı: red, makine partiyi karantinaya almak ister (daha kısıtlayıcı yön)
        malzeme_koduyla_kontrol(k, "AST-N", sertifika(voc="400"), lot_no="L1", defter=d, kullanici="gk1")
    assert k.parti("AST-N", "L1").durum == "bekliyor"


def test_duzeltme_kaydi_yazilamazsa_parti_durumu_degismez(katalog_ve_defter):
    """B1: karari_duzelt'te kayıt yazılamazsa parti durumu değişmez."""
    k, d = katalog_ve_defter
    _kayit_yazilamaz(k.baglanti)
    with pytest.raises(KAYIT_HATALARI):
        karari_duzelt(k, d, "mp1", "AST-N", "L1", "serbest", "tekrar test uygun", rol="mp")
    assert k.parti("AST-N", "L1").durum == "bekliyor"


def test_karari_duzelt_bos_kullaniciyi_yazmadan_once_reddeder(katalog_ve_defter):
    """B1: karari_duzelt kullanıcıyı hiçbir şey yazmadan önce doğrular (" " ile durum değişmez)."""
    k, d = katalog_ve_defter
    with pytest.raises((DenetimHatasi, KatalogHatasi), match="kullanıcı"):
        karari_duzelt(k, d, " ", "AST-N", "L1", "serbest", "tekrar test uygun", rol="mp")
    assert k.parti("AST-N", "L1").durum == "bekliyor"
    assert [x.tur for x in d.kayitlar()] == ["onay"]


def test_onay_kaydi_yazilamazsa_dokuman_surumu_olusmaz(katalog_ve_defter):
    """B1: dokuman_onayla'da kayıt yazılamazsa yeni onaylı sürüm oluşmaz."""
    k, d = katalog_ve_defter
    _kayit_yazilamaz(k.baglanti)
    with pytest.raises(KAYIT_HATALARI):
        dokuman_onayla(k, d, dokuman(voc_ust=330.0), "mp1", "ikinci onay")
    assert [s.surum for s in k.dokuman_surumleri("MIL-PRF-23377", "K")] == [1]


def test_ekle_acik_islemin_icinde_calisir_ve_islemle_geri_alinir(katalog_ve_defter):
    """B1: bağlantıda açık işlem varken ekle SAVEPOINT ile katılır; işlem geri alınınca kayıt da gider."""
    k, d = katalog_ve_defter
    b = k.baglanti
    b.execute("BEGIN")
    b.execute("UPDATE partiler SET durum = 'serbest' WHERE lot_no = 'L1'")
    d.ekle("duzeltme", "mp1", {"yeni_durum": "serbest"}, malzeme_kodu="AST-N", lot_no="L1")
    assert b.in_transaction  # ekle dış işlemi kendi başına bitirmez
    b.rollback()
    assert k.parti("AST-N", "L1").durum == "bekliyor"
    assert [x.tur for x in d.kayitlar()] == ["onay"]
    assert d.zinciri_dogrula().gecerli


# --- S4 (B1'in parçası): taslak ve M&P kapatma ---------------------------------------------------


def test_taslak_duzeltme_kaydi_yazilamazsa_taslak_degismez():
    """S4: taslak_duzelt'te kayıt yazılamazsa taslağın içeriği eski kalır."""
    k = Katalog()
    d = DenetimKaydi(k.baglanti)
    t = k.taslak_kaydet(dokuman(voc_ust=340.0), "mp1")
    _kayit_yazilamaz(k.baglanti)
    with pytest.raises(KAYIT_HATALARI):
        ev.taslak_duzelt(k, d, t.id, dokuman(voc_ust=330.0), "mp1")
    voc = next(x for x in k.taslak(t.id).dokuman.testler if x.id == "voc")
    assert voc.sinir.ust == 340.0
    k.kapat()


def test_taslak_onay_kaydi_yazilamazsa_taslak_acik_kalir_surum_olusmaz():
    """S4: taslak_onayla'da kayıt yazılamazsa taslak açık kalır ve onaylı sürüm oluşmaz."""
    k = Katalog()
    d = DenetimKaydi(k.baglanti)
    t = k.taslak_kaydet(dokuman(), "mp1")
    _kayit_yazilamaz(k.baglanti)
    with pytest.raises(KAYIT_HATALARI):
        ev.taslak_onayla(k, d, t.id, "mp1", "onay")
    assert k.taslak(t.id).durum == "taslak"
    assert k.dokuman_surumleri("MIL-PRF-23377", "K") == []
    k.kapat()


def test_mp_kapatma_kaydi_yazilamazsa_inceleme_isareti_kalir(mp_katalog):
    """S4: mp_incelemesini_kapat (gerek_yok) kayıt yazılamazsa M&P işareti kaldırılmaz."""
    k, d = mp_katalog
    isaret = k.malzeme("AST-J").mp_inceleme
    _kayit_yazilamaz(k.baglanti)
    with pytest.raises(KAYIT_HATALARI):
        mp_incelemesini_kapat(k, d, "AST-J", "mp1", "gerek_yok", "etkilemiyor")
    assert k.malzeme("AST-J").mp_inceleme == isaret
    assert all(p.mp_inceleme == isaret for p in k.partiler("AST-J"))


def test_mp_yeni_revizyon_kaydi_yazilamazsa_revizyon_ve_isaret_degismez(mp_katalog):
    """S4: mp_incelemesini_kapat (yeni_revizyona_gec) kayıt yazılamazsa revizyon da işaret de eski kalır."""
    k, d = mp_katalog
    k.dokuman_onayla(_dok(rev="K"), "mp1")
    isaret = k.malzeme("AST-J").mp_inceleme
    _kayit_yazilamaz(k.baglanti)
    with pytest.raises(KAYIT_HATALARI):
        mp_incelemesini_kapat(k, d, "AST-J", "mp1", "yeni_revizyona_gec", yeni_revizyon="K")
    m = k.malzeme("AST-J")
    assert m.revizyon == "J" and m.mp_inceleme == isaret


# --- B2: INSERT OR REPLACE tetikleyicileri atlatamaz -------------------------------------------


@pytest.fixture
def dosyadaki_defter(tmp_path):
    yol = tmp_path / "k.sqlite"
    with DenetimKaydi(yol) as d:
        d.ekle("onay", "mp1", {"dokuman": "v1"})
        d.ekle("karar", "gk1", {"karar": "kabul"}, malzeme_kodu="AST-001", lot_no="L1")
        d.ekle("duzeltme", "gk2", {"yeni": "red"}, malzeme_kodu="AST-001")
        kayitlar = d.kayitlar()
    return yol, kayitlar


def _satirlar(yol):
    b = sqlite3.connect(yol)
    try:
        return b.execute("SELECT sira, kullanici, ozet FROM denetim_kaydi ORDER BY sira").fetchall()
    finally:
        b.close()


def test_insert_or_replace_ile_var_olan_kayit_degistirilemez(dosyadaki_defter):
    """B2: aynı sıra numarasıyla INSERT OR REPLACE, ham bağlantıdan bile kaydı değiştiremez."""
    yol, k = dosyadaki_defter
    once = _satirlar(yol)
    b = sqlite3.connect(yol)
    with pytest.raises(sqlite3.DatabaseError):
        b.execute(
            "INSERT OR REPLACE INTO denetim_kaydi (sira, zaman, tur, kullanici, icerik, onceki_ozet, ozet)"
            " VALUES (2, ?, 'karar', 'sahte', '{\"karar\":\"red\"}', ?, ?)",
            (k[1].zaman, k[0].ozet, "a" * 64),
        )
        b.commit()
    b.close()
    assert _satirlar(yol) == once


def test_insert_or_replace_ozet_cakismasiyla_kayit_silemez(dosyadaki_defter):
    """B2: zincirin sonuna eklenir gibi görünen ama eski bir kaydın özetini taşıyan REPLACE, o kaydı silemez."""
    yol, k = dosyadaki_defter
    once = _satirlar(yol)
    b = sqlite3.connect(yol)
    with pytest.raises(sqlite3.DatabaseError):
        b.execute(
            "INSERT OR REPLACE INTO denetim_kaydi (sira, zaman, tur, kullanici, icerik, onceki_ozet, ozet)"
            " VALUES (4, ?, 'karar', 'sahte', '{}', ?, ?)",
            (k[2].zaman, k[2].ozet, k[1].ozet),
        )
        b.commit()
    b.close()
    assert _satirlar(yol) == once


# --- B3: denetim_dogrula salt okunur ve eksik tabloyu bozuk sayar -------------------------------


def _sema_nesneleri(yol):
    b = sqlite3.connect(yol)
    try:
        return sorted(b.execute("SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall())
    finally:
        b.close()


def test_dogrula_silinmis_tabloyu_bozuk_sayar_ve_yeniden_kurmaz(dosyadaki_defter, capsys):
    """B3: DROP TABLE sonrası "0 kayıt sağlam" denmez; doğrulayıcı şemayı yeniden kurmaz."""
    yol, _ = dosyadaki_defter
    b = sqlite3.connect(yol)
    b.execute("DROP TABLE denetim_kaydi")
    b.commit()
    b.close()
    once = _sema_nesneleri(yol)
    sonuc = betik_yukle("scripts/denetim_dogrula.py").main(["--db", str(yol)])
    cikti = capsys.readouterr().out
    assert sonuc == 1 and "sağlam" not in cikti
    assert _sema_nesneleri(yol) == once


def test_dogrula_bosaltilmis_tabloyu_bozuk_sayar_ve_tetikleyiciyi_geri_kurmaz(dosyadaki_defter, capsys):
    """B3: silme tetikleyicisi kaldırılıp tablo boşaltılırsa zincir sağlam sayılmaz; tetikleyici yeniden kurulmaz."""
    yol, _ = dosyadaki_defter
    b = sqlite3.connect(yol)
    b.execute("DROP TRIGGER denetim_kaydi_silinemez")
    b.execute("DELETE FROM denetim_kaydi")
    b.commit()
    b.close()
    once = _sema_nesneleri(yol)
    sonuc = betik_yukle("scripts/denetim_dogrula.py").main(["--db", str(yol)])
    cikti = capsys.readouterr().out
    assert sonuc == 1 and "sağlam" not in cikti
    assert _sema_nesneleri(yol) == once


# --- B5: durum yazan karar denetimsiz olamaz ----------------------------------------------------


def test_lot_durumu_yazan_karar_defter_olmadan_reddedilir(katalog_ve_defter):
    """B5: lot_no verilip durumu_yaz açıkken defter=None ise karar verilmez, parti durumu değişmez."""
    k, _ = katalog_ve_defter
    with pytest.raises(KatalogHatasi):
        malzeme_koduyla_kontrol(k, "AST-N", sertifika(voc="400"), lot_no="L1")
    assert k.parti("AST-N", "L1").durum == "bekliyor"


def _uygun_sertifika():
    """Her testi uygun, parti no'su L1: denetimli kararda parti serbest bırakılırdı."""
    return sertifika().model_copy(update={"parti_no": "L1"})


def test_b5_reddi_hicbir_sey_yazmadan_once_verilir(katalog_ve_defter):
    """B5: defter=None ile reddedilen karar katalogda tek satır değiştirmez; parti durumu ve kaynağı aynı kalır."""
    k, d = katalog_ve_defter
    once = k.parti("AST-N", "L1")
    degisiklik = k.baglanti.total_changes
    with pytest.raises(KatalogHatasi, match="defter"):
        malzeme_koduyla_kontrol(k, "AST-N", _uygun_sertifika(), lot_no="L1")
    sonra = k.parti("AST-N", "L1")
    assert (sonra.durum, sonra.durum_kaynagi) == (once.durum, once.durum_kaynagi) == ("bekliyor", None)
    assert k.baglanti.total_changes == degisiklik
    assert [x.tur for x in d.kayitlar()] == ["onay"]
    # Aynı çağrı defterle verilseydi durum yazılırdı: yukarıdaki "değişmedi" boş bir sonuç değil.
    malzeme_koduyla_kontrol(k, "AST-N", _uygun_sertifika(), lot_no="L1", defter=d, kullanici="gk1")
    assert k.parti("AST-N", "L1").durum == "serbest"


def test_baska_bellek_baglantisindaki_defter_yazmadan_once_reddedilir(katalog_ve_defter):
    """B5/B1: katalogla bağlantı paylaşmayan defter reddedilir; parti durumu ve iki kayıt da değişmez."""
    k, d = katalog_ve_defter
    degisiklik = k.baglanti.total_changes
    with DenetimKaydi() as baska:  # kendi :memory: bağlantısı
        with pytest.raises(KatalogHatasi, match="bağlantı"):
            malzeme_koduyla_kontrol(k, "AST-N", _uygun_sertifika(), lot_no="L1", defter=baska, kullanici="gk1")
        assert baska.kayitlar() == []
    assert k.parti("AST-N", "L1").durum == "bekliyor"
    assert k.baglanti.total_changes == degisiklik
    assert [x.tur for x in d.kayitlar()] == ["onay"]


def test_ayni_dosyanin_ayri_baglantisindaki_defter_yazmadan_once_reddedilir(tmp_path):
    """B5/B1: aynı veritabanı dosyası ama ayrı sqlite bağlantısı da tek işlem sayılmaz; hiçbir şey yazılmaz."""
    yol = tmp_path / "k.sqlite"
    with Katalog(yol) as k:
        d = DenetimKaydi(k.baglanti)
        dokuman_onayla(k, d, dokuman(), "mp1", "ilk onay")
        k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
        k.tedarikci_onayla("AST-N", "Ted A")
        k.parti_ekle("L1", "AST-N", "Ted A", "K", "2026-06-01")
        with DenetimKaydi(yol) as baska:
            assert baska.baglanti is not k.baglanti
            with pytest.raises(KatalogHatasi, match="bağlantı"):
                malzeme_koduyla_kontrol(k, "AST-N", _uygun_sertifika(), lot_no="L1", defter=baska, kullanici="gk1")
            assert [x.tur for x in baska.kayitlar()] == ["onay"]
        assert k.parti("AST-N", "L1").durum == "bekliyor"


def test_with_katalog_cikista_baglantiyi_kapatir():
    """with Katalog() bloğundan çıkınca SQLite bağlantısı kapanır; kapalı bağlantı kullanılamaz."""
    with Katalog() as k:
        baglanti = k.baglanti
        baglanti.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        baglanti.execute("SELECT 1")


def test_with_katalog_hata_olsa_da_baglantiyi_kapatir():
    """with Katalog() bloğu hatayla bitse de bağlantı kapanır ve hata yutulmaz."""
    with pytest.raises(RuntimeError, match="blok içi"):
        with Katalog() as k:
            baglanti = k.baglanti
            raise RuntimeError("blok içi")
    with pytest.raises(sqlite3.ProgrammingError):
        baglanti.execute("SELECT 1")


# --- B6: metin olmayan alanlar sahte kurcalama alarmı vermez ------------------------------------


@pytest.mark.parametrize("alan", ["malzeme_kodu", "lot_no", "dokuman_surumu", "model", "istem_surumu"])
def test_metin_olmayan_alan_sahte_kurcalama_alarmi_vermez(alan):
    """B6: int bir alan (ör. lot_no=12345) ya reddedilir ya metne çevrilir; zincir sahte yere bozuk görünmez."""
    with DenetimKaydi() as d:
        try:
            k = d.ekle("karar", "gk1", {"a": 1}, **{alan: 12345})
        except DenetimHatasi:
            assert d.kayitlar() == []
            return
        assert d.zinciri_dogrula().gecerli
        assert getattr(k, alan) == "12345"
        assert d.kayitlar() == [k]


# --- B7: zaman parametresi doğrulanır ve geri gitmez --------------------------------------------


@pytest.mark.parametrize("zaman", ["dün", "2026-13-45T00:00:00+00:00", ""])
def test_gecersiz_zaman_reddedilir(zaman):
    """B7: ISO 8601 olmayan zaman kayda giremez. (Boş metin sessizce "şimdi" sayılmaz.)"""
    with DenetimKaydi() as d:
        with pytest.raises(DenetimHatasi, match="zaman"):
            d.ekle("karar", "gk1", {}, zaman=zaman)
        assert d.kayitlar() == []


def test_saat_dilimsiz_zaman_reddedilir():
    """B7: saat dilimi olmayan zaman (UTC ile karşılaştırılamaz) reddedilir."""
    with DenetimKaydi() as d:
        with pytest.raises(DenetimHatasi, match="zaman"):
            d.ekle("karar", "gk1", {}, zaman="2026-06-01T10:00:00")


def test_onceki_kayittan_eski_zaman_reddedilir():
    """B7: zaman monoton; bir önceki kayıttan eski zamanla kayıt eklenemez."""
    with DenetimKaydi() as d:
        d.ekle("karar", "gk1", {}, zaman="2026-06-01T10:00:00+00:00")
        with pytest.raises(DenetimHatasi, match="zaman"):
            d.ekle("karar", "gk1", {}, zaman="2026-06-01T09:59:59.999999+00:00")
        assert len(d.kayitlar()) == 1


# --- B8: içerik katı ve kararlı JSON -------------------------------------------------------------


@pytest.mark.parametrize("deger", [float("nan"), float("inf"), float("-inf")])
def test_nan_ve_sonsuz_icerik_reddedilir(deger):
    """B8: NaN/Infinity geçerli JSON değildir (allow_nan); kayıt eklenmez."""
    with DenetimKaydi() as d:
        with pytest.raises(ValueError):
            d.ekle("karar", "gk1", {"sonuc": deger})
        assert d.kayitlar() == []


_KUME_BETIGI = """
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
d = DenetimKaydi()
try:
    k = d.ekle("karar", "gk1", {"testler": {"voc", "krom", "yogunluk", "viskozite", "kuruma"}},
               zaman="2026-06-01T10:00:00+00:00")
    print(k.icerik)
except Exception as hata:
    print("HATA", type(hata).__name__)
"""


def test_kume_iceren_icerik_hash_tohumundan_bagimsiz_yazilir():
    """B8: default=str bir kümeyi hash tohumuna bağlı sırayla yazar; aynı içerik her çalıştırmada aynı kaydı vermeli."""
    ciktilar = set()
    for tohum in range(8):
        ortam = dict(os.environ, PYTHONHASHSEED=str(tohum))
        s = subprocess.run([sys.executable, "-c", _KUME_BETIGI], capture_output=True, text=True, env=ortam, cwd=KOK, check=True)
        ciktilar.add(s.stdout.strip())
    assert len(ciktilar) == 1, ciktilar


# --- B9: eşzamanlı iki yazıcı -------------------------------------------------------------------


def test_iki_eszamanli_yazici_zinciri_bozmaz(tmp_path):
    """B9: aynı dosyaya ayrı bağlantılarla aynı anda yazan iki yazıcıdan sonra zincir sağlam ve eksiksizdir."""
    yol = tmp_path / "k.sqlite"
    DenetimKaydi(yol).kapat()
    adet = 40
    engel = threading.Barrier(2)
    hatalar: list[BaseException] = []

    def yaz(ad):
        try:
            with DenetimKaydi(yol) as d:
                engel.wait()
                for i in range(adet):
                    d.ekle("karar", ad, {"i": i})
        except BaseException as hata:  # noqa: BLE001
            hatalar.append(hata)

    iplikler = [threading.Thread(target=yaz, args=(ad,)) for ad in ("gk1", "gk2")]
    for t in iplikler:
        t.start()
    for t in iplikler:
        t.join()
    assert hatalar == []
    with DenetimKaydi(yol) as d:
        s = d.zinciri_dogrula()
        assert s.gecerli and s.kayit_sayisi == 2 * adet
        assert sorted(k.kullanici for k in d.kayitlar()).count("gk1") == adet


# --- B10 ve uygulama.py:232: arayüz (sahte streamlit ile) ---------------------------------------


def _sahte_streamlit():
    st = mock.MagicMock(name="streamlit")
    st.session_state = {}
    st.form_submit_button.return_value = False
    st.button.return_value = False

    def onbellek(f=None, **_):
        if f is None:
            return lambda g: functools.cache(g)
        return functools.cache(f)

    st.cache_resource = onbellek
    st.cache_data = onbellek
    return st


@pytest.fixture
def uygulama(tmp_path, monkeypatch):
    db = tmp_path / "k.sqlite"
    Katalog(db).kapat()
    monkeypatch.setenv("MALZEME_KABUL_DB", str(db))
    monkeypatch.setenv("MALZEME_KABUL_YUKLEME", str(tmp_path / "yuklenen"))
    st = _sahte_streamlit()
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.delitem(sys.modules, "malzeme_kabul.arayuz.uygulama", raising=False)
    modul = importlib.import_module("malzeme_kabul.arayuz.uygulama")
    yield SimpleNamespace(modul=modul, st=st, db=db)
    sys.modules.pop("malzeme_kabul.arayuz.uygulama", None)


def test_uygulama_her_calismada_baglanti_sizdirmaz(uygulama):
    """B10: main() her yeniden çalıştırmada açtığı SQLite bağlantısını kapatmadan bırakmaz (ResourceWarning yok)."""
    import gc

    with warnings.catch_warnings(record=True) as uyarilar:
        warnings.simplefilter("always")
        for _ in range(3):
            uygulama.modul.main()
        gc.collect()
    sizinti = [u for u in uyarilar if issubclass(u.category, ResourceWarning) and "sqlite3" in str(u.message)]
    assert sizinti == [], [str(u.message) for u in sizinti]


def test_duzeltme_formu_denetim_hatasini_kullaniciya_gosterir(uygulama, monkeypatch):
    """B1 (uygulama.py:232): düzeltme formu DenetimHatasi'nı yakalar ve ekranda hata olarak gösterir."""
    st = uygulama.st
    st.session_state["son_karar"] = ("AST-N", "L1")
    st.selectbox.return_value = "serbest"
    st.text_area.return_value = "tekrar test uygun"
    st.button.return_value = True

    def hatali(*_a, **_k):
        raise DenetimHatasi("kullanıcı boş olamaz")

    monkeypatch.setattr(uygulama.modul, "karari_duzelt", hatali)
    uygulama.modul.duzeltme_formu(mock.MagicMock(), mock.MagicMock(), SimpleNamespace(ad="gk", rol="giris_kalite"))
    st.error.assert_called_once()
    assert "kullanıcı" in st.error.call_args.args[0]
    st.success.assert_not_called()


# === İnceleme sonrası düzeltmeler (ikinci tur) =================================================


# --- Önemli 1: taslak işlemleri farklı bağlantıdaki defteri reddeder ---------------------------


def _ayri_baglantili(tur, tmp_path):
    """Katalog ve onunla bağlantı paylaşmayan bir defter: ayrı :memory: ya da aynı dosyanın ayrı bağlantısı."""
    if tur == "ayri_bellek":
        return Katalog(), DenetimKaydi()
    yol = tmp_path / "k.sqlite"
    return Katalog(yol), DenetimKaydi(yol)


@pytest.mark.parametrize("tur", ["ayri_bellek", "ayni_dosya_ayri_baglanti"])
def test_taslak_duzelt_ayri_baglantili_defteri_yazmadan_reddeder(tur, tmp_path):
    """İnceleme 2, önemli 1: taslak_duzelt, katalogla bağlantı paylaşmayan defteri KatalogHatasi ile reddeder; hiçbir şey yazılmaz."""
    k, d = _ayri_baglantili(tur, tmp_path)
    t = k.taslak_kaydet(dokuman(voc_ust=340.0), "mp1")
    with pytest.raises(KatalogHatasi):
        ev.taslak_duzelt(k, d, t.id, dokuman(voc_ust=330.0), "mp1")
    assert next(x for x in k.taslak(t.id).dokuman.testler if x.id == "voc").sinir.ust == 340.0
    assert d.kayitlar() == []
    d.kapat()
    k.kapat()


@pytest.mark.parametrize("tur", ["ayri_bellek", "ayni_dosya_ayri_baglanti"])
def test_taslak_onayla_ayri_baglantili_defteri_yazmadan_reddeder(tur, tmp_path):
    """İnceleme 2, önemli 1: taslak_onayla, katalogla bağlantı paylaşmayan defteri KatalogHatasi ile reddeder; sürüm oluşmaz."""
    k, d = _ayri_baglantili(tur, tmp_path)
    t = k.taslak_kaydet(dokuman(), "mp1")
    with pytest.raises(KatalogHatasi):
        ev.taslak_onayla(k, d, t.id, "mp1", "onay")
    assert k.taslak(t.id).durum == "taslak"
    assert k.dokuman_surumleri("MIL-PRF-23377", "K") == []
    assert d.kayitlar() == []
    d.kapat()
    k.kapat()


# --- Önemli 2: K2 makine kuralında yarış (iki bağlantı, aynı dosya) -----------------------------


@pytest.fixture
def iki_baglanti(tmp_path):
    """Aynı dosyaya iki ayrı bağlantı: A (insan) ve B (makine / ikinci kullanıcı). L1 yeni ve bekliyor."""
    yol = tmp_path / "k.sqlite"
    ka = Katalog(yol)
    da = DenetimKaydi(ka.baglanti)
    dokuman_onayla(ka, da, dokuman(), "mp1", "ilk onay")
    ka.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
    ka.tedarikci_onayla("AST-N", "Ted A")
    ka.parti_ekle("L1", "AST-N", "Ted A", "K", "2026-06-01")
    kb = Katalog(yol)
    db = DenetimKaydi(kb.baglanti)
    yield SimpleNamespace(yol=yol, ka=ka, da=da, kb=kb, db=db)
    kb.kapat()
    ka.kapat()


def _uygun_sertifika():
    return sertifika().model_copy(update={"parti_no": "L1"})


def _araya_insan_karari_sok(monkeypatch, b, kb, ka, da):
    """B'nin işlem dışındaki ilk parti okumasından hemen sonra A'da insan kararını (karantina) yazıp bitirir.

    B'nin okuması açık bir işlemin içindeyse kanca çalışmaz: o okuma zaten
    korumalıdır. Okumaların hiçbiri işlem dışında değilse yarış penceresi yoktur;
    o durumda insan kararı B bittikten sonra yazılır.
    """
    orijinal = Katalog.parti
    durum = {"tetiklendi": False}

    def kanca(self, malzeme_kodu, lot_no):
        sonuc = orijinal(self, malzeme_kodu, lot_no)
        if self is kb and not durum["tetiklendi"] and not self.baglanti.in_transaction:
            durum["tetiklendi"] = True
            karari_duzelt(ka, da, "mp1", malzeme_kodu, lot_no, "karantina", "insan: lab sonucu şüpheli", rol="mp")
        return sonuc

    monkeypatch.setattr(Katalog, "parti", kanca)
    return durum


def test_yaris_duzeni_yarissiz_makine_kabulu_verir(iki_baglanti):
    """Önemli 2 (düzenek denetimi): yarış olmadan aynı sertifika yeni partiyi serbest bırakır; yarış testi boşa geçmez."""
    s = iki_baglanti
    k = malzeme_koduyla_kontrol(s.kb, "AST-N", _uygun_sertifika(), lot_no="L1", defter=s.db, kullanici="gk1")
    assert k.parti_karari == "kabul" and s.ka.parti("AST-N", "L1").durum == "serbest"


def test_makine_karari_okumasiyla_yazmasi_arasindaki_insan_karantinasini_ezmez(iki_baglanti, monkeypatch):
    """Önemli 2 (K2 yarışı): B okuduktan sonra A partiyi insan kararıyla karantinaya alırsa B'nin kabulü serbest bırakmaz.

    Karar yolu partiyi IMMEDIATE işlem içinde yeniden okumalı; kayıttaki parti durumu gerçek durumla tutmalı.
    """
    s = iki_baglanti
    kanca = _araya_insan_karari_sok(monkeypatch, s.kb, s.kb, s.ka, s.da)
    malzeme_koduyla_kontrol(s.kb, "AST-N", _uygun_sertifika(), lot_no="L1", defter=s.db, kullanici="gk1")
    if not kanca["tetiklendi"]:  # yarış penceresi yok: insan kararı sonra gelir
        karari_duzelt(s.ka, s.da, "mp1", "AST-N", "L1", "karantina", "insan: lab sonucu şüpheli", rol="mp")
    assert s.ka.parti("AST-N", "L1").durum == "karantina"
    kararlar = [x for x in s.da.kayitlar("karar") if x.lot_no == "L1"]
    assert len(kararlar) == 1
    duz = s.da.kayitlar("duzeltme")[0]
    if kararlar[0].sira > duz.sira:  # karar insandan sonra yazıldıysa insan kararını görmüş olmalı
        assert kararlar[0].veri["parti_durumu"] == "karantina"
    else:
        assert duz.veri["onceki_durum"] == kararlar[0].veri["parti_durumu"]
    assert s.da.zinciri_dogrula().gecerli


def test_karari_duzelt_onceki_durumu_yazma_isleminin_icinde_okur(iki_baglanti, monkeypatch):
    """Önemli 2: iki eşzamanlı düzeltmede sonra yazılan kaydın onceki_durum'u, ilk düzeltmenin yeni_durum'udur."""
    s = iki_baglanti
    kanca = _araya_insan_karari_sok(monkeypatch, s.kb, s.kb, s.ka, s.da)
    karari_duzelt(s.kb, s.db, "mp2", "AST-N", "L1", "serbest", "yeniden test uygun", rol="mp")
    if not kanca["tetiklendi"]:
        karari_duzelt(s.ka, s.da, "mp1", "AST-N", "L1", "karantina", "insan: lab sonucu şüpheli", rol="mp")
    ilk, son = sorted(s.da.kayitlar("duzeltme"), key=lambda x: x.sira)
    assert ilk.veri["onceki_durum"] == "bekliyor"
    assert son.veri["onceki_durum"] == ilk.veri["yeni_durum"]
    assert s.ka.parti("AST-N", "L1").durum == son.veri["yeni_durum"]


def _islem_basinda_insan_karantinasi_sok(monkeypatch, kb, ka, da):
    """B'nin ilk (dış) işlemi açılmadan hemen önce A'da M&P karantinasını yazıp bitirir.

    B işlem dışında parti okuduysa o okuma bayatlar: B'nin kararı ancak işlemin
    içinde yeniden okursa doğru durumu (karantina) görür. Aynı anda
    `_araya_insan_karari_sok` gibi işlem dışı parti okumasından sonra da tetiklenir
    (hangisi önce gelirse).
    """
    import contextlib

    durum = {"tetiklendi": False}

    def sok():
        if not durum["tetiklendi"]:
            durum["tetiklendi"] = True
            karari_duzelt(ka, da, "mp1", "AST-N", "L1", "karantina", "M&P: lab sonucu şüpheli", rol="mp")

    orijinal_islem = Katalog.islem
    orijinal_parti = Katalog.parti

    @contextlib.contextmanager
    def islem_kancasi(self):
        if self is kb and not self.baglanti.in_transaction:
            sok()
        with orijinal_islem(self) as b:
            yield b

    def parti_kancasi(self, malzeme_kodu, lot_no):
        sonuc = orijinal_parti(self, malzeme_kodu, lot_no)
        if self is kb and not self.baglanti.in_transaction:
            sok()
        return sonuc

    monkeypatch.setattr(Katalog, "islem", islem_kancasi)
    monkeypatch.setattr(Katalog, "parti", parti_kancasi)
    return durum


def test_giris_kalite_serbest_birakirken_araya_giren_mp_karantinasini_ezemez(iki_baglanti, monkeypatch):
    """Önemli 2 (rol + yarış): giriş kalite bekliyor → serbest isterken araya M&P karantinası girerse
    giriş kalite M&P hatasıyla reddedilir; parti karantinada kalır, B hiçbir kayıt yazmaz."""
    s = iki_baglanti
    assert s.ka.parti("AST-N", "L1").durum == "bekliyor"
    kanca = _islem_basinda_insan_karantinasi_sok(monkeypatch, s.kb, s.ka, s.da)
    with pytest.raises(KatalogHatasi, match="M&P"):
        karari_duzelt(s.kb, s.db, "gk1", "AST-N", "L1", "serbest", "iç laboratuvar sonucu uygun", rol="giris_kalite")
    assert kanca["tetiklendi"], "araya girme olmadı; test boşa geçti"
    assert s.ka.parti("AST-N", "L1").durum == "karantina"
    duzeltmeler = s.da.kayitlar("duzeltme")
    assert [(x.kullanici, x.veri["yeni_durum"], x.veri["rol"]) for x in duzeltmeler] == [("mp1", "karantina", "mp")]
    assert s.da.zinciri_dogrula().gecerli


# --- Küçük: göç, gelecek zaman, açık işlem ------------------------------------------------------


def test_eski_veritabanina_uzerine_yazma_tetikleyicisi_acilista_eklenir(tmp_path):
    """İnceleme 2, küçük (göç): uzerine_yazilamaz tetikleyicisi olmadan kurulmuş eski veritabanı açılınca onu kazanır; REPLACE reddedilir."""
    from malzeme_kabul.kayit.denetim_kaydi import SEMA

    eski_sema = SEMA.split("CREATE TRIGGER IF NOT EXISTS denetim_kaydi_uzerine_yazilamaz")[0]
    yol = tmp_path / "eski.sqlite"
    b = sqlite3.connect(yol)
    b.executescript(eski_sema)
    b.close()
    assert ("trigger", "denetim_kaydi_uzerine_yazilamaz") not in _sema_nesneleri(yol)
    with DenetimKaydi(yol) as d:
        d.ekle("onay", "mp1", {"dokuman": "v1"})
        k1 = d.kayitlar()[0]
    assert ("trigger", "denetim_kaydi_uzerine_yazilamaz") in _sema_nesneleri(yol)
    b = sqlite3.connect(yol)
    with pytest.raises(sqlite3.DatabaseError):
        b.execute(
            "INSERT OR REPLACE INTO denetim_kaydi (sira, zaman, tur, kullanici, icerik, onceki_ozet, ozet)"
            " VALUES (1, ?, 'karar', 'sahte', '{}', ?, ?)",
            (k1.zaman, k1.onceki_ozet, "b" * 64),
        )
    b.close()
    assert _satirlar(yol) == [(1, "mp1", k1.ozet)]


def _iso(an):
    return an.isoformat(timespec="microseconds")


def test_bes_dakikadan_ileri_zaman_reddedilir():
    """İnceleme 2, küçük (B7): şimdiden 5 dakikadan fazla ileri zaman DenetimHatasi verir (hemen üstü: 5 dk + 1 sn)."""
    from datetime import datetime, timedelta, timezone

    with DenetimKaydi() as d:
        with pytest.raises(DenetimHatasi, match="zaman"):
            d.ekle("karar", "gk1", {}, zaman=_iso(datetime.now(timezone.utc) + timedelta(minutes=5, seconds=1)))
        with pytest.raises(DenetimHatasi, match="zaman"):
            d.ekle("karar", "gk1", {}, zaman=_iso(datetime.now(timezone.utc) + timedelta(days=365)))
        assert d.kayitlar() == []


def test_ileri_zaman_baska_saat_diliminde_de_reddedilir():
    """İnceleme 2, küçük (B7, birim karışıklığı): +03:00 ile yazılmış ileri zaman da UTC'ye göre ölçülür ve reddedilir."""
    from datetime import datetime, timedelta, timezone

    istanbul = timezone(timedelta(hours=3))
    with DenetimKaydi() as d:
        with pytest.raises(DenetimHatasi, match="zaman"):
            d.ekle("karar", "gk1", {}, zaman=_iso(datetime.now(istanbul) + timedelta(minutes=6)))


def test_bes_dakikanin_hemen_altindaki_ileri_zaman_kabul_edilir():
    """İnceleme 2, küçük (B7, hemen altı): saat kayması payı içindeki (4 dk 50 sn ileri) zaman kabul edilir."""
    from datetime import datetime, timedelta, timezone

    with DenetimKaydi() as d:
        d.ekle("karar", "gk1", {}, zaman=_iso(datetime.now(timezone.utc) + timedelta(minutes=4, seconds=50)))
        assert len(d.kayitlar()) == 1


def test_acik_islemdeki_baglantiyla_defter_kurulamaz():
    """İnceleme 2, küçük: bağlantıda açık işlem varken DenetimKaydi kurulamaz; executescript işlemi sessizce bitirmez."""
    k = Katalog()
    k.dokuman_onayla(dokuman(), "mp1")
    k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
    b = k.baglanti
    b.execute("BEGIN")
    b.execute("UPDATE malzemeler SET aciklama = 'yarım iş' WHERE kod = 'AST-N'")
    with pytest.raises(DenetimHatasi):
        DenetimKaydi(b)
    assert b.in_transaction
    b.rollback()
    assert k.malzeme("AST-N").aciklama is None
    k.kapat()


# --- Küçük: arayüz (sahte streamlit) -----------------------------------------------------------


def _giris_yapmis_calistir(uygulama, monkeypatch):
    from malzeme_kabul.arayuz.kimlik import Kullanici

    st = uygulama.st
    st.session_state["kullanici"] = Kullanici("mp", "mp")
    st.sidebar.button.return_value = False
    st.sidebar.radio.return_value = "depo"
    monkeypatch.setattr(uygulama.modul, "EKRAN_FONKSIYONLARI", {"depo": lambda *_a: None})
    uygulama.modul.main()
    yazilar = [c.args[0] for c in st.sidebar.caption.call_args_list if c.args and "Denetim zinciri" in str(c.args[0])]
    assert len(yazilar) == 1, st.sidebar.caption.call_args_list
    return yazilar[0]


def _uygulama_defteri(db):
    with DenetimKaydi(db) as d:
        d.ekle("onay", "mp1", {"dokuman": "v1"})
        d.ekle("karar", "gk1", {"karar": "kabul"})


def test_kenar_cubugu_saglam_zinciri_saglam_gosterir(uygulama, monkeypatch):
    """İnceleme 2, küçük (düzenek denetimi): şema tam ve zincir sağlamsa kenar çubuğu "sağlam" der."""
    _uygulama_defteri(uygulama.db)
    assert "sağlam" in _giris_yapmis_calistir(uygulama, monkeypatch)


@pytest.mark.parametrize("tetikleyici", ["denetim_kaydi_degistirilemez", "denetim_kaydi_silinemez", "denetim_kaydi_uzerine_yazilamaz"])
def test_kenar_cubugu_eksik_tetikleyicide_bozuk_gosterir(uygulama, monkeypatch, tetikleyici):
    """İnceleme 2, küçük: tetikleyicisi kaldırılmış veritabanında kenar çubuğu, özetler tutsa da "BOZUK" der."""
    _uygulama_defteri(uygulama.db)
    b = sqlite3.connect(uygulama.db)
    b.execute(f"DROP TRIGGER {tetikleyici}")
    b.commit()
    b.close()
    yazi = _giris_yapmis_calistir(uygulama, monkeypatch)
    assert "BOZUK" in yazi and "sağlam" not in yazi


def test_kenar_cubugu_bosaltilmis_tabloda_bozuk_gosterir(uygulama, monkeypatch):
    """İnceleme 2, küçük: silme tetikleyicisi kaldırılıp tablo boşaltılmışsa kenar çubuğu "BOZUK" der (0 kayıt sağlam değil)."""
    _uygulama_defteri(uygulama.db)
    b = sqlite3.connect(uygulama.db)
    b.execute("DROP TRIGGER denetim_kaydi_silinemez")
    b.execute("DELETE FROM denetim_kaydi")
    b.commit()
    b.close()
    yazi = _giris_yapmis_calistir(uygulama, monkeypatch)
    assert "BOZUK" in yazi and "sağlam" not in yazi


@pytest.mark.parametrize("hata", [KatalogHatasi("MIL-PRF-23377K zaten yüklü"), ValueError("revizyon harfi geçersiz")])
def test_revizyon_yukleme_formu_hatayi_kullaniciya_gosterir(uygulama, monkeypatch, hata):
    """İnceleme 2, küçük (uygulama.py ~145): yeni_revizyon_yukle KatalogHatasi/ValueError verirse form st.error gösterir, çökmez."""
    st = uygulama.st
    st.tabs.return_value = [mock.MagicMock(), mock.MagicMock(), mock.MagicMock()]
    st.file_uploader.return_value = None
    st.form_submit_button.return_value = True
    st.text_input.side_effect = lambda etiket, *a, **k: {"Belge no": "MIL-PRF-23377", "Yeni revizyon harfi": "K"}.get(etiket, "")
    monkeypatch.setattr(uygulama.modul.ev, "hazir_revizyon_raporlari", lambda *_a, **_k: {})

    def hatali(*_a, **_k):
        raise hata

    monkeypatch.setattr(uygulama.modul, "yeni_revizyon_yukle", hatali)
    with Katalog() as k:
        uygulama.modul.revizyon_ekrani(k, DenetimKaydi(k.baglanti), SimpleNamespace(ad="mp"))
    st.error.assert_called_once_with(str(hata))
    st.success.assert_not_called()


# --- baglan ve zincir_durumu (sahte streamlit ile içe aktarılır) --------------------------------


def test_baglan_defteri_katalogla_ayni_baglantida_kurar(uygulama):
    """baglan: defter katalogun bağlantısını kullanır ve kurulduktan sonra şema tamdır."""
    from malzeme_kabul.kayit.denetim_kaydi import sema_eksikleri

    with Katalog() as k:
        defter, _ = uygulama.modul.baglan(k)
        assert defter.baglanti is k.baglanti
        assert sema_eksikleri(k.baglanti) == []


def test_baglan_bos_veritabaninda_kurulumdan_onceki_eksikleri_doner(uygulama):
    """baglan: denetim şeması hiç yoksa dönen eksik listesi tabloyu ve üç tetikleyiciyi içerir."""
    from malzeme_kabul.kayit.denetim_kaydi import TETIKLEYICILER

    with Katalog() as k:
        _, eksik = uygulama.modul.baglan(k)
    assert eksik == ["tablo denetim_kaydi"] + [f"tetikleyici {t}" for t in TETIKLEYICILER]


def test_baglan_kurulumun_yeniden_yarattigi_tetikleyiciyi_eksik_bildirir(uygulama):
    """baglan: eksik tetikleyici kurulumdan önce okunur; kurulum onu geri yaratsa da eksik listesinde kalır."""
    from malzeme_kabul.kayit.denetim_kaydi import sema_eksikleri

    with Katalog() as k:
        DenetimKaydi(k.baglanti)
        k.baglanti.execute("DROP TRIGGER denetim_kaydi_uzerine_yazilamaz")
        _, eksik = uygulama.modul.baglan(k)
        assert eksik == ["tetikleyici denetim_kaydi_uzerine_yazilamaz"]
        assert sema_eksikleri(k.baglanti) == []  # kurulum yeniden yarattı; eksik ondan önce okundu


def test_zincir_durumu_saglam_zincirde_kayit_sayisini_yazar(uygulama):
    """zincir_durumu: şema tam ve zincir sağlamsa "sağlam (N kayıt)" yazar."""
    with DenetimKaydi() as d:
        d.ekle("onay", "mp1", {"dokuman": "v1"})
        d.ekle("karar", "gk1", {"karar": "kabul"})
        assert uygulama.modul.zincir_durumu(d, []) == "Denetim zinciri: sağlam (2 kayıt)"


def test_zincir_durumu_sema_eksikse_zincir_saglam_olsa_da_bozuk_yazar(uygulama):
    """zincir_durumu: şema eksikse özetler tutsa da BOZUK der ve eksik nesneleri sayar."""
    with DenetimKaydi() as d:
        d.ekle("onay", "mp1", {"dokuman": "v1"})
        yazi = uygulama.modul.zincir_durumu(d, ["tetikleyici denetim_kaydi_silinemez"])
    assert yazi == "Denetim zinciri: BOZUK (şema: eksik tetikleyici denetim_kaydi_silinemez)"


def test_zincir_durumu_degistirilmis_kayitta_bozuk_sirayi_yazar(uygulama):
    """zincir_durumu: içeriği değiştirilmiş kaydın sırasını ve nedenini yazar."""
    with DenetimKaydi() as d:
        d.ekle("onay", "mp1", {"dokuman": "v1"})
        d.ekle("karar", "gk1", {"karar": "kabul"})
        d.baglanti.execute("DROP TRIGGER denetim_kaydi_degistirilemez")
        d.baglanti.execute("UPDATE denetim_kaydi SET icerik = '{\"karar\":\"red\"}' WHERE sira = 2")
        yazi = uygulama.modul.zincir_durumu(d, [])
    assert yazi.startswith("Denetim zinciri: BOZUK (kayıt 2: ") and "sağlam" not in yazi


def test_zincir_durumu_sirasi_olmayan_bozuklukta_zincir_sonu_yazar(uygulama):
    """zincir_durumu: doğrulama bozuk sıra vermezse (son özet tutmazsa) "zincir sonu" yazar."""
    from malzeme_kabul.kayit.denetim_kaydi import DogrulamaSonucu

    defter = SimpleNamespace(zinciri_dogrula=lambda: DogrulamaSonucu(False, 2, None, "son özet tutmuyor"))
    assert uygulama.modul.zincir_durumu(defter, []) == "Denetim zinciri: BOZUK (zincir sonu: son özet tutmuyor)"


# --- MESGUL: karar sırasında veritabanı kilitliyse form "meşgul" der, çökmez --------------------


def _mesgul(*_a, **_k):
    raise sqlite3.OperationalError("database is locked")


def _mesgul_gosterildi(uygulama):
    st = uygulama.st
    st.error.assert_called_once()
    assert uygulama.modul.MESGUL in st.error.call_args.args[0]
    assert "database is locked" in st.error.call_args.args[0]
    st.success.assert_not_called()


def test_duzeltme_formu_veritabani_mesgulse_mesgul_mesaji_gosterir(uygulama, monkeypatch):
    st = uygulama.st
    st.session_state["son_karar"] = ("AST-N", "L1")
    st.selectbox.return_value = "serbest"
    st.text_area.return_value = "tekrar test uygun"
    st.button.return_value = True
    monkeypatch.setattr(uygulama.modul, "karari_duzelt", _mesgul)
    uygulama.modul.duzeltme_formu(mock.MagicMock(), mock.MagicMock(), SimpleNamespace(ad="gk", rol="giris_kalite"))
    _mesgul_gosterildi(uygulama)


@pytest.mark.parametrize("dosya_adi, hedef", [("coc.pdf", "sertifika_hatti"), ("coc.json", "ev.json_sertifika_karari")])
def test_giris_kalite_karari_veritabani_mesgulse_mesgul_mesaji_gosterir(uygulama, monkeypatch, dosya_adi, hedef):
    st = uygulama.st
    m = SimpleNamespace(kod="AST-N", standart_etiketi="MIL-PRF-23377K", tip="I", sinif="N", revizyon="K")
    st.selectbox.side_effect = [m, "L1"]  # malzeme, sonra var olan lot
    st.radio.return_value = "kural"
    dosya = mock.MagicMock()
    dosya.name = dosya_adi
    dosya.getvalue.return_value = b"{}"
    st.file_uploader.return_value = dosya
    st.button.return_value = True
    monkeypatch.setattr(uygulama.modul, "dosyayi_kaydet", lambda _d: uygulama.db.parent / dosya_adi)
    if hedef == "sertifika_hatti":
        monkeypatch.setattr(uygulama.modul, "sertifika_hatti", _mesgul)
    else:
        monkeypatch.setattr(uygulama.modul.ev, "json_sertifika_karari", _mesgul)
    uygulama.modul.giris_kalite_ekrani(mock.MagicMock(), mock.MagicMock(), SimpleNamespace(ad="gk"))
    _mesgul_gosterildi(uygulama)
    assert "son_karar" not in st.session_state  # karar gösterilmedi, düzeltme formu açılmaz


@pytest.mark.parametrize("dugme, hedef", [("sol", "taslak_duzelt"), ("sag", "taslak_onayla")])
def test_taslak_islemi_veritabani_mesgulse_mesgul_mesaji_gosterir(uygulama, monkeypatch, dugme, hedef):
    st = uygulama.st
    sol, sag = mock.MagicMock(), mock.MagicMock()
    sol.button.return_value = dugme == "sol"
    sag.button.return_value = dugme == "sag"
    sag.text_input.return_value = ""
    st.columns.return_value = [sol, sag]
    secim = mock.MagicMock()
    katalog = mock.MagicMock()
    katalog.taslaklar.return_value = [secim]
    st.selectbox.return_value = secim
    monkeypatch.setattr(uygulama.modul.ev, "test_tablosu", lambda *_a, **_k: [])
    monkeypatch.setattr(uygulama.modul.ev, "tablodan_dokuman", lambda *_a, **_k: None)
    monkeypatch.setattr(uygulama.modul.ev, hedef, _mesgul)
    uygulama.modul.taslak_ekrani(katalog, mock.MagicMock(), SimpleNamespace(ad="mp"))
    _mesgul_gosterildi(uygulama)


def test_revizyon_yukleme_formu_veritabani_mesgulse_mesgul_mesaji_gosterir(uygulama, monkeypatch):
    st = uygulama.st
    st.tabs.return_value = [mock.MagicMock(), mock.MagicMock(), mock.MagicMock()]
    st.file_uploader.return_value = None
    st.form_submit_button.return_value = True
    st.text_input.side_effect = lambda etiket, *a, **k: {"Belge no": "MIL-PRF-23377", "Yeni revizyon harfi": "K"}.get(etiket, "")
    monkeypatch.setattr(uygulama.modul.ev, "hazir_revizyon_raporlari", lambda *_a, **_k: {})
    monkeypatch.setattr(uygulama.modul, "yeni_revizyon_yukle", _mesgul)
    with Katalog() as k:
        uygulama.modul.revizyon_ekrani(k, DenetimKaydi(k.baglanti), SimpleNamespace(ad="mp"))
    _mesgul_gosterildi(uygulama)


def test_mp_inceleme_kapatma_veritabani_mesgulse_mesgul_mesaji_gosterir(uygulama, monkeypatch):
    st = uygulama.st
    st.tabs.return_value = [mock.MagicMock(), mock.MagicMock(), mock.MagicMock()]
    st.file_uploader.return_value = None
    st.form_submit_button.return_value = False
    st.text_input.return_value = ""
    st.selectbox.return_value = "AST-N"
    st.radio.return_value = "gerek_yok"
    st.button.return_value = True  # "İncelemeyi kapat"
    monkeypatch.setattr(uygulama.modul.ev, "hazir_revizyon_raporlari", lambda *_a, **_k: {})
    monkeypatch.setattr(uygulama.modul, "mp_bekleyenler", lambda *_a, **_k: ["AST-N"])
    monkeypatch.setattr(uygulama.modul, "mp_incelemesini_kapat", _mesgul)
    uygulama.modul.revizyon_ekrani(mock.MagicMock(), mock.MagicMock(), SimpleNamespace(ad="mp"))
    _mesgul_gosterildi(uygulama)
