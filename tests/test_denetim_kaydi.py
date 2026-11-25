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
    karari_duzelt(k, d, "mp1", "AST-N", "L1", "serbest", "tekrar test uygun")
    kayitlar = d.kayitlar()
    assert [x.tur for x in kayitlar] == ["onay", "karar", "duzeltme"]
    onay, karar, duz = kayitlar
    assert onay.dokuman_surumu == "MIL-PRF-23377K v1" and onay.veri["not"] == "ilk onay"
    assert (karar.kullanici, karar.model, karar.istem_surumu, karar.pdf_sayfasi) == ("gk1", "qwen3:8b", "okuma-v1", "1-2")
    assert karar.veri["parti_karari"] == "red" and karar.veri["kontrol"]["satirlar"][0]["madde"] == "MIL-PRF-23377K, 3.5.1"
    assert duz.veri == {"onceki_durum": "karantina", "yeni_durum": "serbest", "neden": "tekrar test uygun"}
    assert k.parti("AST-N", "L1").durum == "serbest"
    assert d.zinciri_dogrula().gecerli


def test_kayitli_karar_kullanici_ister(katalog_ve_defter):
    k, d = katalog_ve_defter
    with pytest.raises(KatalogHatasi, match="kullanıcı"):
        malzeme_koduyla_kontrol(k, "AST-N", sertifika(), defter=d)


def test_duzeltme_gerekce_ister(katalog_ve_defter):
    k, d = katalog_ve_defter
    with pytest.raises(KatalogHatasi, match="gerekçe"):
        karari_duzelt(k, d, "mp1", "AST-N", "L1", "serbest", " ")


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
