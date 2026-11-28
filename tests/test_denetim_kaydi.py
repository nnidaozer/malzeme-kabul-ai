"""Zincirli denetim kaydının testleri (docs/mimari.md madde 3)."""

from __future__ import annotations

import sqlite3

import pytest

from malzeme_kabul.kayit.denetim_kaydi import BASLANGIC, DenetimHatasi, DenetimKaydi, kayit_ozeti
from tests.conftest import betik_yukle


@pytest.fixture
def defter():
    d = DenetimKaydi()
    d.ekle("onay", "mp1", {"dokuman": "MIL-PRF-23377K v1"}, dokuman_surumu="MIL-PRF-23377K v1")
    d.ekle("karar", "gk1", {"karar": "kabul"}, malzeme_kodu="AST-001", lot_no="L1",
           dokuman_surumu="MIL-PRF-23377K v1", pdf_sayfasi=3, model="qwen3:8b", istem_surumu="okuma-v1")
    d.ekle("duzeltme", "gk2", {"onceki": "kabul", "yeni": "red", "neden": "lab sonucu"}, malzeme_kodu="AST-001")
    yield d
    d.kapat()


def _kurcala(d: DenetimKaydi, sql: str) -> None:
    d.baglanti.execute("DROP TRIGGER denetim_kaydi_degistirilemez")
    d.baglanti.execute("DROP TRIGGER denetim_kaydi_silinemez")
    d.baglanti.execute(sql)


def test_kayit_alanlari(defter):
    k = defter.kayitlar("karar")[0]
    assert (k.sira, k.kullanici, k.malzeme_kodu, k.lot_no, k.dokuman_surumu) == (2, "gk1", "AST-001", "L1", "MIL-PRF-23377K v1")
    assert (k.pdf_sayfasi, k.model, k.istem_surumu) == ("3", "qwen3:8b", "okuma-v1")
    assert k.veri == {"karar": "kabul"} and k.zaman.endswith("+00:00")


def test_zincir_baglantisi(defter):
    k = defter.kayitlar()
    assert k[0].onceki_ozet == BASLANGIC
    assert [x.onceki_ozet for x in k[1:]] == [x.ozet for x in k[:-1]]
    assert defter.son_ozet() == k[-1].ozet


def test_saglam_zincir_dogrulanir(defter):
    s = defter.zinciri_dogrula()
    assert s.gecerli and s.kayit_sayisi == 3 and s.son_ozet == defter.son_ozet()
    assert defter.zinciri_dogrula(beklenen_son_ozet=defter.son_ozet()).gecerli


def test_bos_zincir_gecerli():
    with DenetimKaydi() as d:
        s = d.zinciri_dogrula()
        assert s.gecerli and s.kayit_sayisi == 0 and s.son_ozet == BASLANGIC


def test_tetikleyiciler_degisiklik_ve_silmeyi_reddeder(defter):
    with pytest.raises(sqlite3.IntegrityError, match="değiştirilemez"):
        defter.baglanti.execute("UPDATE denetim_kaydi SET kullanici = 'x'")
    with pytest.raises(sqlite3.IntegrityError, match="silinemez"):
        defter.baglanti.execute("DELETE FROM denetim_kaydi WHERE sira = 3")


def test_degistirilen_kayit_yakalanir(defter):
    _kurcala(defter, "UPDATE denetim_kaydi SET icerik = '{\"karar\":\"red\"}' WHERE sira = 2")
    s = defter.zinciri_dogrula()
    assert not s.gecerli and s.bozuk_sira == 2 and "değiştirilmiş" in s.neden


def test_ortadan_silinen_kayit_yakalanir(defter):
    _kurcala(defter, "DELETE FROM denetim_kaydi WHERE sira = 2")
    s = defter.zinciri_dogrula()
    assert not s.gecerli and s.bozuk_sira == 3


def test_ozet_yeniden_hesaplanip_yazilsa_da_sonraki_kayit_yakalar(defter):
    k = defter.kayitlar()[1]
    alanlar = dict(k.__dict__, kullanici="sahte")
    yeni = kayit_ozeti(alanlar)
    _kurcala(defter, f"UPDATE denetim_kaydi SET kullanici = 'sahte', ozet = '{yeni}' WHERE sira = 2")
    s = defter.zinciri_dogrula()
    assert not s.gecerli and s.bozuk_sira == 3 and "önceki özet" in s.neden


def test_sondan_silme_dis_ozetle_yakalanir(defter):
    son = defter.son_ozet()
    _kurcala(defter, "DELETE FROM denetim_kaydi WHERE sira = 3")
    assert defter.zinciri_dogrula().gecerli  # zincir kendi içinde tutarlı
    s = defter.zinciri_dogrula(beklenen_son_ozet=son)
    assert not s.gecerli and "dışarıda saklanan" in s.neden


def test_gecersiz_kayit_reddedilir(defter):
    with pytest.raises(DenetimHatasi, match="bilinmeyen kayıt türü"):
        defter.ekle("silme", "x", {})
    with pytest.raises(DenetimHatasi, match="kullanıcı"):
        defter.ekle("karar", " ", {})
    assert defter.zinciri_dogrula().kayit_sayisi == 3


def test_ozet_alan_sirasindan_bagimsiz():
    a = {"sira": 1, "zaman": "t", "tur": "karar", "kullanici": "u", "icerik": "{}", "onceki_ozet": BASLANGIC}
    assert kayit_ozeti(a) == kayit_ozeti(dict(reversed(list(a.items()))))


def test_filtreler(defter):
    assert [k.tur for k in defter.kayitlar(malzeme_kodu="AST-001")] == ["karar", "duzeltme"]


def test_dosyada_kalici_ve_paylasilan_baglanti(tmp_path):
    yol = tmp_path / "k.sqlite"
    with DenetimKaydi(yol) as d:
        d.ekle("karar", "u", {"a": 1})
    baglanti = sqlite3.connect(yol)
    d2 = DenetimKaydi(baglanti)
    d2.ekle("karar", "u", {"a": 2})
    d2.kapat()  # paylaşılan bağlantıyı kapatmaz
    assert DenetimKaydi(baglanti).zinciri_dogrula().kayit_sayisi == 2


def test_dogrulama_komutu(tmp_path, capsys):
    yol = tmp_path / "k.sqlite"
    with DenetimKaydi(yol) as d:
        d.ekle("karar", "u", {"a": 1})
        son = d.son_ozet()
    betik = betik_yukle("scripts/denetim_dogrula.py")
    assert betik.main(["--db", str(yol)]) == 0
    assert "zincir sağlam: 1 kayıt" in capsys.readouterr().out
    assert betik.main(["--db", str(yol), "--son-ozet", son]) == 0
    assert betik.main(["--db", str(yol), "--son-ozet", "f" * 64]) == 1
    b = sqlite3.connect(yol)
    b.execute("DROP TRIGGER denetim_kaydi_degistirilemez")
    b.execute("UPDATE denetim_kaydi SET kullanici = 'x'")
    b.commit()
    b.close()
    assert betik.main(["--db", str(yol)]) == 1
    assert "ZİNCİR BOZUK" in capsys.readouterr().out


# --- hatta bağlantı ------------------------------------------------------------------

from malzeme_kabul.hat.katalog_karari import dokuman_onayla, karari_duzelt, malzeme_koduyla_kontrol  # noqa: E402
from malzeme_kabul.katalog.veritabani import Katalog, KatalogHatasi  # noqa: E402
from tests.test_katalog_karari import dokuman, sertifika  # noqa: E402


@pytest.fixture
def katalog_ve_defter():
    k = Katalog()
    d = DenetimKaydi(k.baglanti)
    dokuman_onayla(k, d, dokuman(), "mp1", "ilk onay")
    k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
    k.tedarikci_onayla("AST-N", "Ted A")
    k.parti_ekle("L1", "AST-N", "Ted A", "K", "2026-06-01")
    yield k, d
    k.kapat()


def test_onay_karar_ve_duzeltme_zincire_yazilir(katalog_ve_defter):
    k, d = katalog_ve_defter
    malzeme_koduyla_kontrol(k, "AST-N", sertifika(voc="400"), lot_no="L1", defter=d, kullanici="gk1",
                            model="qwen3:8b", istem_surumu="okuma-v1", pdf_sayfasi="1-2")
    karari_duzelt(k, d, "mp1", "AST-N", "L1", "serbest", "tekrar test uygun", rol="mp")
    kayitlar = d.kayitlar()
    assert [x.tur for x in kayitlar] == ["onay", "karar", "duzeltme"]
    onay, karar, duz = kayitlar
    assert onay.dokuman_surumu == "MIL-PRF-23377K v1" and onay.veri["not"] == "ilk onay"
    assert (karar.kullanici, karar.model, karar.istem_surumu, karar.pdf_sayfasi) == ("gk1", "qwen3:8b", "okuma-v1", "1-2")
    assert karar.veri["parti_karari"] == "red" and karar.veri["kontrol"]["satirlar"][0]["madde"] == "MIL-PRF-23377K, 3.5.1"
    assert duz.veri == {"onceki_durum": "karantina", "yeni_durum": "serbest", "neden": "tekrar test uygun",
                       "rol": "mp"}
    assert k.parti("AST-N", "L1").durum == "serbest"
    assert d.zinciri_dogrula().gecerli


def test_kayitli_karar_kullanici_ister(katalog_ve_defter):
    k, d = katalog_ve_defter
    with pytest.raises(KatalogHatasi, match="kullanıcı"):
        malzeme_koduyla_kontrol(k, "AST-N", sertifika(), defter=d)


def test_duzeltme_gerekce_ister(katalog_ve_defter):
    k, d = katalog_ve_defter
    with pytest.raises(KatalogHatasi, match="gerekçe"):
        karari_duzelt(k, d, "mp1", "AST-N", "L1", "serbest", " ", rol="mp")


# --- Nida kararı: karantinadan serbest bırakmayı yalnız M&P, gerekçeyle yapar ---------------------


def _karantinaya_al(k, d, lot="L1"):
    karari_duzelt(k, d, "mp1", "AST-N", lot, "karantina", "numune şüpheli", rol="mp")
    assert k.parti("AST-N", lot).durum == "karantina"


def _iz(k, d, lot="L1"):
    return k.parti("AST-N", lot).durum, [(x.sira, x.tur) for x in d.kayitlar()]


def test_karari_duzelt_rolu_zorunlu_anahtar_kelime_argumani_olarak_ister():
    import inspect

    p = inspect.signature(karari_duzelt).parameters["rol"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY
    assert p.default is inspect.Parameter.empty


def test_karari_duzelt_rolsuz_cagrilirsa_hicbir_sey_yazmaz(katalog_ve_defter):
    k, d = katalog_ve_defter
    once = _iz(k, d)
    with pytest.raises(TypeError):
        karari_duzelt(k, d, "gk1", "AST-N", "L1", "serbest", "tekrar test uygun")
    assert _iz(k, d) == once


@pytest.mark.parametrize("yeni_durum", ["serbest", "bekliyor"])
def test_giris_kalite_karantinadaki_partiyi_karantinadan_cikaramaz(katalog_ve_defter, yeni_durum):
    k, d = katalog_ve_defter
    _karantinaya_al(k, d)
    once = _iz(k, d)
    with pytest.raises(KatalogHatasi, match="M&P"):
        karari_duzelt(k, d, "gk1", "AST-N", "L1", yeni_durum, "tekrar test uygun", rol="giris_kalite")
    assert _iz(k, d) == once
    assert d.zinciri_dogrula().gecerli


def test_giris_kalite_makinenin_karantinaya_aldigi_partiyi_serbest_birakamaz(katalog_ve_defter):
    # Karantinanın kaynağı (makine ya da insan) fark etmez; çıkış yalnız M&P'nindir.
    k, d = katalog_ve_defter
    malzeme_koduyla_kontrol(k, "AST-N", sertifika(voc="400"), lot_no="L1", defter=d, kullanici="gk1")
    assert k.parti("AST-N", "L1").durum == "karantina"
    once = _iz(k, d)
    with pytest.raises(KatalogHatasi, match="M&P"):
        karari_duzelt(k, d, "gk1", "AST-N", "L1", "serbest", "tekrar test uygun", rol="giris_kalite")
    assert _iz(k, d) == once


@pytest.mark.parametrize("yeni_durum", ["serbest", "bekliyor"])
def test_mp_karantinadaki_partiyi_gerekceyle_karantinadan_cikarir(katalog_ve_defter, yeni_durum):
    k, d = katalog_ve_defter
    _karantinaya_al(k, d)
    kayit = karari_duzelt(k, d, "mp1", "AST-N", "L1", yeni_durum, "tekrar test uygun", rol="mp")
    assert k.parti("AST-N", "L1").durum == yeni_durum
    assert kayit.tur == "duzeltme" and kayit.kullanici == "mp1"
    assert kayit.veri["onceki_durum"] == "karantina" and kayit.veri["yeni_durum"] == yeni_durum
    assert kayit.veri["rol"] == "mp"


@pytest.mark.parametrize("neden", ["", " ", "\t\n"])
def test_mp_de_karantinadan_gerekcesiz_cikaramaz(katalog_ve_defter, neden):
    k, d = katalog_ve_defter
    _karantinaya_al(k, d)
    once = _iz(k, d)
    with pytest.raises(KatalogHatasi, match="gerekçe"):
        karari_duzelt(k, d, "mp1", "AST-N", "L1", "serbest", neden, rol="mp")
    assert _iz(k, d) == once


def test_giris_kalite_karantinadaki_partiyi_karantinada_tutan_duzeltme_yapabilir(katalog_ve_defter):
    # Kısıt yalnız karantinadan çıkıştır; karantina → karantina (gerekçe ekleme) serbesttir.
    k, d = katalog_ve_defter
    _karantinaya_al(k, d)
    kayit = karari_duzelt(k, d, "gk1", "AST-N", "L1", "karantina", "ek bulgu: ambalaj hasarlı", rol="giris_kalite")
    assert k.parti("AST-N", "L1").durum == "karantina" and kayit.veri["rol"] == "giris_kalite"


def test_giris_kalite_bekleyen_partiyi_serbest_birakabilir(katalog_ve_defter):
    k, d = katalog_ve_defter
    assert k.parti("AST-N", "L1").durum == "bekliyor"
    kayit = karari_duzelt(k, d, "gk1", "AST-N", "L1", "serbest", "iç laboratuvar sonucu uygun", rol="giris_kalite")
    assert k.parti("AST-N", "L1").durum == "serbest"
    assert kayit.veri == {"onceki_durum": "bekliyor", "yeni_durum": "serbest",
                          "neden": "iç laboratuvar sonucu uygun", "rol": "giris_kalite"}


def test_giris_kalite_bekleyen_partiyi_karantinaya_alabilir(katalog_ve_defter):
    k, d = katalog_ve_defter
    kayit = karari_duzelt(k, d, "gk1", "AST-N", "L1", "karantina", "numune şüpheli", rol="giris_kalite")
    assert k.parti("AST-N", "L1").durum == "karantina"
    assert kayit.veri["onceki_durum"] == "bekliyor" and kayit.veri["rol"] == "giris_kalite"


def test_giris_kalite_serbest_partiyi_karantinaya_alabilir(katalog_ve_defter):
    k, d = katalog_ve_defter
    karari_duzelt(k, d, "mp1", "AST-N", "L1", "serbest", "tekrar test uygun", rol="mp")
    karari_duzelt(k, d, "gk1", "AST-N", "L1", "karantina", "depoda nem hasarı", rol="giris_kalite")
    assert k.parti("AST-N", "L1").durum == "karantina"


@pytest.mark.parametrize("rol", ["", " ", "admin", "MP", "M&P", "giris", None])
def test_bilinmeyen_rol_reddedilir_ve_hicbir_sey_yazilmaz(katalog_ve_defter, rol):
    k, d = katalog_ve_defter
    once = _iz(k, d)
    with pytest.raises(KatalogHatasi):
        karari_duzelt(k, d, "gk1", "AST-N", "L1", "serbest", "tekrar test uygun", rol=rol)
    assert _iz(k, d) == once


def test_bilinmeyen_rol_karantinadaki_partide_de_reddedilir(katalog_ve_defter):
    k, d = katalog_ve_defter
    _karantinaya_al(k, d)
    once = _iz(k, d)
    with pytest.raises(KatalogHatasi):
        karari_duzelt(k, d, "x", "AST-N", "L1", "karantina", "neden", rol="depo")
    assert _iz(k, d) == once


def test_betikler_denetim_kaydina_yazar(tmp_path, capsys):
    from tests.conftest import KOK

    db = tmp_path / "k.sqlite"
    betik_yukle("scripts/katalog_kur.py").main(["--db", str(db), "--ornek"])
    ser = KOK / "data/sentetik/sertifikalar/MIL-PRF-23377K/json/S-001.json"
    betik_yukle("scripts/karar_ver.py").main(["--malzeme", "AST-001", "--sertifika", str(ser), "--db", str(db), "--kullanici", "gk1"])
    with DenetimKaydi(db) as d:
        assert [k.tur for k in d.kayitlar()] == ["onay", "onay", "onay", "karar"]
        assert d.kayitlar("karar")[0].kullanici == "gk1"
    assert betik_yukle("scripts/denetim_dogrula.py").main(["--db", str(db)]) == 0


def test_dogrulama_komutu_tetikleyiciler_yerindeyken_kurcalanan_kaydi_yakalar(tmp_path, capsys):
    """Denetim inceleme 2: şema denetimi geçse de (tetikleyici kaldırılıp kayıt değiştirilip geri kurulmuş) özet uyuşmazlığı yakalanır."""
    yol = tmp_path / "k.sqlite"
    with DenetimKaydi(yol) as d:
        d.ekle("karar", "u", {"a": 1})
        d.ekle("karar", "u", {"a": 2})
    b = sqlite3.connect(yol)
    tanim = b.execute("SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'denetim_kaydi_degistirilemez'").fetchone()[0]
    b.execute("DROP TRIGGER denetim_kaydi_degistirilemez")
    b.execute("UPDATE denetim_kaydi SET icerik = '{\"a\":9}' WHERE sira = 2")
    b.execute(tanim)
    b.commit()
    b.close()
    betik = betik_yukle("scripts/denetim_dogrula.py")
    assert betik.main(["--db", str(yol)]) == 1
    cikti = capsys.readouterr().out
    assert "ZİNCİR BOZUK (kayıt 2)" in cikti and "değiştirilmiş" in cikti and "şema" not in cikti


# --- sema_eksikleri: şemayı yalnız okuyarak eksik nesneleri bildirir ----------------------------


def test_sema_eksikleri_bos_veritabaninda_tablo_ve_uc_tetikleyiciyi_bildirir():
    from malzeme_kabul.kayit.denetim_kaydi import TETIKLEYICILER, sema_eksikleri

    b = sqlite3.connect(":memory:")
    assert sema_eksikleri(b) == ["tablo denetim_kaydi"] + [f"tetikleyici {t}" for t in TETIKLEYICILER]
    b.close()


def test_sema_eksikleri_bos_veritabaninda_sema_kurmaz():
    from malzeme_kabul.kayit.denetim_kaydi import sema_eksikleri

    b = sqlite3.connect(":memory:")
    sema_eksikleri(b)
    assert b.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0
    b.close()


def test_sema_eksikleri_tam_semada_bos_liste_doner(defter):
    from malzeme_kabul.kayit.denetim_kaydi import sema_eksikleri

    assert sema_eksikleri(defter.baglanti) == []


@pytest.mark.parametrize("tetikleyici", ["denetim_kaydi_degistirilemez", "denetim_kaydi_silinemez",
                                         "denetim_kaydi_uzerine_yazilamaz"])
def test_sema_eksikleri_tek_eksik_tetikleyiciyi_yalniz_onu_bildirir(defter, tetikleyici):
    from malzeme_kabul.kayit.denetim_kaydi import sema_eksikleri

    defter.baglanti.execute(f"DROP TRIGGER {tetikleyici}")
    assert sema_eksikleri(defter.baglanti) == [f"tetikleyici {tetikleyici}"]


def test_sema_eksikleri_eksik_tetikleyiciyi_yeniden_kurmaz(defter):
    from malzeme_kabul.kayit.denetim_kaydi import sema_eksikleri

    defter.baglanti.execute("DROP TRIGGER denetim_kaydi_silinemez")
    sema_eksikleri(defter.baglanti)
    assert sema_eksikleri(defter.baglanti) == ["tetikleyici denetim_kaydi_silinemez"]


def test_sema_eksikleri_ayni_adli_baska_tur_nesneyi_tablo_saymaz():
    from malzeme_kabul.kayit.denetim_kaydi import sema_eksikleri

    b = sqlite3.connect(":memory:")
    b.execute("CREATE TABLE baska (x)")
    b.execute("CREATE VIEW denetim_kaydi AS SELECT x FROM baska")
    assert "tablo denetim_kaydi" in sema_eksikleri(b)
    b.close()


# --- Rol güveni: kimlik tablosu varsa verilen rol kayıtlı rolle tutmalı ---------------------------

from malzeme_kabul.arayuz import kimlik  # noqa: E402

PAROLA = "deneme-parolasi-123"


@pytest.fixture
def kimlikli(katalog_ve_defter):
    """Katalog bağlantısında kimlik tablosu: 'gk' giriş kalite, 'mp' M&P. L1 bekliyor, L2 karantina."""
    k, d = katalog_ve_defter
    kimlik.kullanici_ekle(k.baglanti, "gk", PAROLA, "giris_kalite")
    kimlik.kullanici_ekle(k.baglanti, "mp", PAROLA, "mp")
    k.parti_ekle("L2", "AST-N", "Ted A", "K", "2026-06-01", durum="karantina")
    return k, d


def _tum_iz(k, d):
    return [(p.lot_no, p.durum) for p in k.partiler("AST-N")], [(x.sira, x.tur) for x in d.kayitlar()]


@pytest.mark.parametrize("kullanici, sahte_rol, lot, yeni_durum", [
    ("gk", "mp", "L2", "serbest"),            # giriş kalite kendini M&P diye tanıtıp karantinadan çıkaramaz
    ("gk", "mp", "L1", "serbest"),            # karantina dışı düzeltmede de rol tutmalı
    ("mp", "giris_kalite", "L1", "karantina"),  # kayıttaki rol yanlış yazılmaz
])
def test_kayitli_rolle_tutmayan_rol_reddedilir_ve_hicbir_sey_yazilmaz(kimlikli, kullanici, sahte_rol, lot, yeni_durum):
    k, d = kimlikli
    once = _tum_iz(k, d)
    with pytest.raises(KatalogHatasi):
        karari_duzelt(k, d, kullanici, "AST-N", lot, yeni_durum, "tekrar test uygun", rol=sahte_rol)
    assert _tum_iz(k, d) == once


@pytest.mark.parametrize("rol", ["mp", "giris_kalite"])
def test_kimlik_tablosu_varken_kayitsiz_kullanici_reddedilir(kimlikli, rol):
    k, d = kimlikli
    once = _tum_iz(k, d)
    with pytest.raises(KatalogHatasi):
        karari_duzelt(k, d, "yabanci", "AST-N", "L1", "serbest", "tekrar test uygun", rol=rol)
    assert _tum_iz(k, d) == once


def test_kayitli_mp_kendi_roluyle_karantinadan_cikarir(kimlikli):
    k, d = kimlikli
    kayit = karari_duzelt(k, d, "mp", "AST-N", "L2", "serbest", "tekrar test uygun", rol="mp")
    assert k.parti("AST-N", "L2").durum == "serbest"
    assert kayit.kullanici == "mp" and kayit.veri["rol"] == "mp"


def test_kayitli_giris_kalite_kendi_roluyle_bekleyeni_serbest_birakir(kimlikli):
    k, d = kimlikli
    kayit = karari_duzelt(k, d, "gk", "AST-N", "L1", "serbest", "iç laboratuvar sonucu uygun", rol="giris_kalite")
    assert k.parti("AST-N", "L1").durum == "serbest" and kayit.veri["rol"] == "giris_kalite"


def test_kayitli_giris_kalite_kendi_roluyle_de_karantinadan_cikaramaz(kimlikli):
    k, d = kimlikli
    once = _tum_iz(k, d)
    with pytest.raises(KatalogHatasi, match="M&P"):
        karari_duzelt(k, d, "gk", "AST-N", "L2", "serbest", "tekrar test uygun", rol="giris_kalite")
    assert _tum_iz(k, d) == once


def test_kimlik_tablosu_yoksa_verilen_rol_kullanilir(katalog_ve_defter):
    k, d = katalog_ve_defter
    tablo = k.baglanti.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'kullanicilar'").fetchone()
    assert tablo is None
    karari_duzelt(k, d, "mp1", "AST-N", "L1", "karantina", "numune şüpheli", rol="mp")
    kayit = karari_duzelt(k, d, "mp1", "AST-N", "L1", "serbest", "tekrar test uygun", rol="mp")
    assert k.parti("AST-N", "L1").durum == "serbest" and kayit.veri["rol"] == "mp"
