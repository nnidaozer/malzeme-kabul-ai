"""Arayüz: kimlik ve roller, ekranların arkasındaki işler, Streamlit ekranları (streamlit kuruluysa)."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from malzeme_kabul.arayuz import ekran_verisi as ev
from malzeme_kabul.arayuz.kimlik import KimlikHatasi, giris, kullanici_ekle, kullanicilar, yetkili_mi
from malzeme_kabul.katalog.ornek_veri import ornek_yukle
from malzeme_kabul.katalog.veritabani import Katalog, KatalogHatasi
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.sozlesme.sema import KabulDokumani, Kaynak, RafOmru, StandartBilgisi
from tests.conftest import KOK, betik_yukle

DOKUMAN = KabulDokumani.model_validate_json((KOK / "data/cikti/MIL-PRF-23377K_kabul_dokumani.json").read_text(encoding="utf-8"))
SET = KOK / "data/sentetik/sertifikalar/MIL-PRF-23377K"
UYGULAMA = KOK / "src/malzeme_kabul/arayuz/uygulama.py"


@pytest.fixture
def katalog():
    k = Katalog()
    ornek_yukle(k, KOK / "data/ornek/katalog.json", KOK)
    yield k
    k.kapat()


# --- kimlik ve roller ----------------------------------------------------------------


def test_giris_ve_roller():
    b = sqlite3.connect(":memory:")
    kullanici_ekle(b, "nida", "uzun-parola-1", "mp")
    kullanici_ekle(b, "ali", "uzun-parola-2", "giris_kalite")
    mp = giris(b, "nida", "uzun-parola-1")
    assert mp.rol == "mp" and mp.ekranlar == ("standart", "taslak", "revizyon", "depo")
    assert giris(b, "nida", "yanlis-parola") is None and giris(b, "yok", "uzun-parola-1") is None
    gk = giris(b, "ali", "uzun-parola-2")
    assert yetkili_mi(gk, "giris") and yetkili_mi(gk, "depo") and not yetkili_mi(gk, "taslak")
    assert not yetkili_mi(mp, "giris") and not yetkili_mi(None, "depo")
    assert [k.ad for k in kullanicilar(b)] == ["ali", "nida"]


def test_parola_duz_saklanmaz():
    b = sqlite3.connect(":memory:")
    kullanici_ekle(b, "nida", "uzun-parola-1", "mp")
    tuz, ozet = b.execute("SELECT tuz, ozet FROM kullanicilar").fetchone()
    assert "uzun-parola-1" not in ozet and len(ozet) == 64 and len(tuz) == 32


@pytest.mark.parametrize("ad, parola, rol", [("x", "kisa", "mp"), (" ", "uzun-parola", "mp"), ("x", "uzun-parola", "admin")])
def test_gecersiz_kullanici(ad, parola, rol):
    with pytest.raises(KimlikHatasi):
        kullanici_ekle(sqlite3.connect(":memory:"), ad, parola, rol)


def test_ayni_kullanici_iki_kez_eklenemez():
    b = sqlite3.connect(":memory:")
    kullanici_ekle(b, "nida", "uzun-parola-1", "mp")
    with pytest.raises(KimlikHatasi, match="zaten var"):
        kullanici_ekle(b, "nida", "uzun-parola-1", "mp")


def test_kullanici_ekle_betigi(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MALZEME_KABUL_PAROLA", "uzun-parola-1")
    db = tmp_path / "k.sqlite"
    assert betik_yukle("scripts/kullanici_ekle.py").main(["--ad", "nida", "--rol", "mp", "--db", str(db)]) == 0
    assert giris(sqlite3.connect(db), "nida", "uzun-parola-1").rol == "mp"


# --- test kümesi kilidi ---------------------------------------------------------------------


def test_standart_izni_bolunmeye_gore(tmp_path):
    yaml = tmp_path / "b.yaml"
    yaml.write_text("test_kumesi_acik: false\ngelistirme:\n  - MIL-PRF-23377K\n# yorum\n\ntest:\n  - MIL-PRF-87937D\n", encoding="utf-8")
    assert ev.standart_izinli_mi("MIL-PRF-23377K", yaml)[0]
    izin, neden = ev.standart_izinli_mi("MIL-PRF-87937D", yaml)
    assert not izin and "test kümesinde" in neden
    assert not ev.standart_izinli_mi("MIL-PRF-1A", yaml)[0]
    assert not ev.standart_izinli_mi("MIL-PRF-23377K", tmp_path / "yok.yaml")[0]


def test_gercek_bolunmede_test_kumesi_reddedilir():
    assert ev.standart_izinli_mi("MIL-PRF-23377K")[0]
    assert not ev.standart_izinli_mi("MIL-PRF-87937D")[0]


def test_test_kumesindeki_standart_yuklenemez(katalog, tmp_path):
    yaml = tmp_path / "b.yaml"
    yaml.write_text("gelistirme:\n  - MIL-PRF-23377K\ntest:\n  - MIL-PRF-87937D\n", encoding="utf-8")
    with pytest.raises(KatalogHatasi, match="test kümesinde"):
        ev.standart_yukle(katalog, tmp_path / "MIL-PRF-87937D.pdf", "mp1", yaml)
    assert katalog.taslaklar() == []


# --- M&P: taslak düzelt ve onayla -------------------------------------------------------------


def test_taslak_tablosu_duzeltilir_kaydedilir_onaylanir(katalog):
    d = DenetimKaydi(katalog.baglanti)
    t = katalog.taslak_kaydet(DOKUMAN, "mp1")
    tablo = ev.test_tablosu(t.dokuman)
    voc = next(s for s in tablo if s["id"] == "voc_solvent_content")
    assert voc["ust"] == 340 and voc["birim"] == "g/L" and voc["kabul"]
    voc["ust"] = 330.0
    voc["omur_uzatma"] = True
    yeni = ev.tablodan_dokuman(t.dokuman, tablo)
    farklar = ev.taslak_duzelt(katalog, d, t.id, yeni, "mp1")
    assert any("voc_solvent_content.sinir" in f for f in farklar) and any("test_turleri" in f for f in farklar)
    assert ev.taslak_duzelt(katalog, d, t.id, yeni, "mp1") == []  # değişiklik yoksa kayıt yok
    s = ev.taslak_onayla(katalog, d, t.id, "mp1", "VOC düzeltildi")
    assert s.etiket == "MIL-PRF-23377K v2"
    assert next(x for x in s.dokuman.testler if x.id == "voc_solvent_content").sinir.ust == 330
    assert [k.tur for k in d.kayitlar()] == ["duzeltme", "onay"] and d.zinciri_dogrula().gecerli
    with pytest.raises(KatalogHatasi, match="onaylanmış"):
        katalog.taslak_guncelle(t.id, yeni)
    with pytest.raises(KatalogHatasi, match="zaten onaylanmış"):
        katalog.taslagi_onayla(t.id, "mp1")


def test_tablo_gecersiz_duzeltmeyi_reddeder():
    tablo = ev.test_tablosu(DOKUMAN)
    with pytest.raises(ValueError, match="eklenemez"):
        ev.tablodan_dokuman(DOKUMAN, tablo[1:])
    tablo[0]["kabul"] = tablo[0]["omur_uzatma"] = tablo[0]["yeterlilik"] = False
    with pytest.raises(ValueError, match="test türü"):
        ev.tablodan_dokuman(DOKUMAN, tablo)
    tablo = ev.test_tablosu(DOKUMAN)
    voc = next(s for s in tablo if s["id"] == "voc_solvent_content")
    voc["birim"] = "parsek-bilmem"
    with pytest.raises(ValueError):
        ev.tablodan_dokuman(DOKUMAN, tablo)


def test_tablo_bos_hucreleri_none_sayar():
    tablo = ev.test_tablosu(DOKUMAN)
    voc = next(s for s in tablo if s["id"] == "voc_solvent_content")
    voc["alt"] = float("nan")
    assert ev.tablodan_dokuman(DOKUMAN, tablo) == DOKUMAN


def test_taslak_standardi_degistirilemez(katalog):
    t = katalog.taslak_kaydet(DOKUMAN, "mp1")
    baska = DOKUMAN.model_copy(update={"standart": DOKUMAN.standart.model_copy(update={"revizyon": "J"})})
    with pytest.raises(KatalogHatasi, match="değiştirilemez"):
        katalog.taslak_guncelle(t.id, baska)


def test_hazir_revizyon_raporlari():
    r = ev.hazir_revizyon_raporlari()
    assert "MIL-PRF-23377_J-K" in r and r["MIL-PRF-23377_J-K"].suffix == ".md"


# --- giriş kalite ve depo ---------------------------------------------------------------------


def test_json_sertifika_karari_ve_tablo(katalog):
    d = DenetimKaydi(katalog.baglanti)
    p = ev.parti_hazirla(katalog, "AST-001", "YENI-1", "Örnek Tedarikçi A", "K", "2026-11-01")
    assert p.durum == "bekliyor" and ev.parti_hazirla(katalog, "AST-001", "YENI-1", "x", "K", "2026-01-01") == p
    karar = ev.json_sertifika_karari(katalog, d, "AST-001", (SET / "json/S-001.json").read_text(encoding="utf-8"), "gk1", "YENI-1")
    tablo = ev.karar_tablosu(karar)
    assert tablo[0]["test"] == "Standart ve revizyon atfı" and any(s["madde"].startswith("MIL-PRF-23377K") for s in tablo)
    assert {"karar", "test", "madde", "sayfa", "gerekce"} <= set(tablo[0])
    assert d.kayitlar("karar")[0].lot_no == "YENI-1"


def test_depo_tablosu(katalog):
    tablo = ev.depo_tablosu(katalog, date(2026, 11, 25))
    assert tablo[0]["lot"] == "A-2510-03" and tablo[0]["raf"] == ev.RAF_ETIKETI["doldu"]
    yakin = next(s for s in tablo if s["lot"] == "A-2512-01")
    assert yakin["kalan gün"] == 15 and yakin["ömür uzatma testleri"] == "tanımlı değil"


def test_depo_tablosu_raf_notunu_gosterir():
    kaynak = Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde="3.9")
    d = KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        raf_omurleri=[RafOmru(sure=1, birim="year", kaynak=kaynak),
                      RafOmru(kap_turu="plastik", sure=6, birim="month", kaynak=kaynak)],
    )
    with Katalog() as k:
        k.dokuman_onayla(d, "mp1")
        k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
        k.tedarikci_onayla("AST-N", "Ted A")
        k.parti_ekle("KAPSIZ", "AST-N", "Ted A", "K", "2026-03-10")
        (satir,) = ev.depo_tablosu(k, date(2026, 4, 1))
    assert satir["son kullanma"] == "2026-09-10"
    assert "kap türü bilinmiyor" in satir["not"] and "en kısa" in satir["not"]


# --- M&P: revizyon raporu ve test kümesi kilidi ---------------------------------------------


@pytest.fixture
def karsilastirma_yasak(monkeypatch):
    """Kilit reddederse revizyonlari_karsilastir hiç çağrılmamalı."""
    def yasak(*a, **k):
        raise AssertionError("revizyonlari_karsilastir kilitten önce çağrıldı")

    monkeypatch.setattr(ev, "revizyonlari_karsilastir", yasak)


def bolunme(tmp_path, gelistirme=(), test=(), acik=False):
    yol = tmp_path / "bolunme.yaml"
    satirlar = [f"test_kumesi_acik: {'true' if acik else 'false'}", "gelistirme:"]
    satirlar += [f"  - {s}" for s in gelistirme]
    satirlar += ["test:"] + [f"  - {s}" for s in test]
    yol.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    return yol


def test_revizyon_raporu_test_kumesindeki_standardi_reddeder(tmp_path, karsilastirma_yasak):
    yaml = bolunme(tmp_path, gelistirme=["MIL-PRF-99999B"], test=["MIL-PRF-99999A"])
    with pytest.raises(KatalogHatasi, match="test kümesinde"):
        ev.revizyon_raporu(tmp_path / "MIL-PRF-99999A.pdf", tmp_path / "MIL-PRF-99999B.pdf", bolunme_yolu=yaml)


def test_revizyon_raporu_yeni_revizyon_test_kumesindeyse_reddeder(tmp_path, karsilastirma_yasak):
    yaml = bolunme(tmp_path, gelistirme=["MIL-PRF-99999A"], test=["MIL-PRF-99999B"])
    with pytest.raises(KatalogHatasi, match="MIL-PRF-99999B test kümesinde"):
        ev.revizyon_raporu(tmp_path / "MIL-PRF-99999A.pdf", tmp_path / "MIL-PRF-99999B.pdf", bolunme_yolu=yaml)


def test_revizyon_raporu_bolunmede_olmayani_reddeder(tmp_path, karsilastirma_yasak):
    yaml = bolunme(tmp_path, gelistirme=["MIL-PRF-99999A"])
    with pytest.raises(KatalogHatasi, match="bölünmede yok"):
        ev.revizyon_raporu(tmp_path / "MIL-PRF-99999A.pdf", tmp_path / "MIL-PRF-99999B.pdf", bolunme_yolu=yaml)


def test_revizyon_raporu_bolunme_dosyasi_yoksa_reddeder(tmp_path, karsilastirma_yasak):
    with pytest.raises(KatalogHatasi, match="denetlenemedi"):
        ev.revizyon_raporu(tmp_path / "MIL-PRF-99999A.pdf", tmp_path / "MIL-PRF-99999B.pdf",
                           bolunme_yolu=tmp_path / "yok.yaml")


class SahteFark:
    def ozet(self):
        return {"degisen": 1}


def sahte_karsilastirma(monkeypatch):
    cagrilar = []

    def karsilastir(eski_pdf, yeni_pdf, belge_no, eski_rev, yeni_rev):
        cagrilar.append((eski_pdf, yeni_pdf, belge_no, eski_rev, yeni_rev))
        return SahteFark()

    monkeypatch.setattr(ev, "revizyonlari_karsilastir", karsilastir)
    monkeypatch.setattr(ev, "markdown_raporu", lambda fark, oneriler=None: "# sahte rapor")
    return cagrilar


def test_revizyon_raporu_gelistirme_kumesinde_karsilastirir(tmp_path, monkeypatch):
    cagrilar = sahte_karsilastirma(monkeypatch)
    yaml = bolunme(tmp_path, gelistirme=["MIL-PRF-99999A", "MIL-PRF-99999B"])
    eski, yeni = tmp_path / "MIL-PRF-99999A.pdf", tmp_path / "MIL-PRF-99999B.pdf"
    assert ev.revizyon_raporu(eski, yeni, bolunme_yolu=yaml) == ("# sahte rapor", {"degisen": 1})
    assert cagrilar == [(eski, yeni, "MIL-PRF-99999", "A", "B")]


def test_revizyon_raporu_kilit_acikken_test_kumesine_izin_verir(tmp_path, monkeypatch):
    cagrilar = sahte_karsilastirma(monkeypatch)
    yaml = bolunme(tmp_path, test=["MIL-PRF-99999A", "MIL-PRF-99999B"], acik=True)
    md, ozet = ev.revizyon_raporu(tmp_path / "MIL-PRF-99999A.pdf", tmp_path / "MIL-PRF-99999B.pdf", bolunme_yolu=yaml)
    assert (md, ozet) == ("# sahte rapor", {"degisen": 1}) and len(cagrilar) == 1


def test_revizyon_raporu_farkli_standart_valueerror_kalir(tmp_path, karsilastirma_yasak):
    # Belge no denetimi kilitten önce: bölünmede olmasalar da ValueError.
    yaml = bolunme(tmp_path)
    with pytest.raises(ValueError, match="aynı standardın"):
        ev.revizyon_raporu(tmp_path / "MIL-PRF-99999A.pdf", tmp_path / "MIL-PRF-88888B.pdf", bolunme_yolu=yaml)


def test_revizyon_izinli_mi_iki_revizyonu_da_denetler(tmp_path):
    yaml = bolunme(tmp_path, gelistirme=["MIL-PRF-99999A", "MIL-PRF-99999C"], test=["MIL-PRF-99999B"])
    assert ev.revizyon_izinli_mi("MIL-PRF-99999A.pdf", "MIL-PRF-99999C.pdf", yaml)[0] is True
    for eski, yeni, reddedilen in [
        ("MIL-PRF-99999A.pdf", "MIL-PRF-99999B.pdf", "MIL-PRF-99999B"),  # yeni test kümesinde
        ("MIL-PRF-99999B.pdf", "MIL-PRF-99999C.pdf", "MIL-PRF-99999B"),  # eski test kümesinde
        ("MIL-PRF-99999A.pdf", "MIL-PRF-99999D.pdf", "MIL-PRF-99999D"),  # yeni bölünmede yok
        ("MIL-PRF-99999D.pdf", "MIL-PRF-99999A.pdf", "MIL-PRF-99999D"),  # eski bölünmede yok
    ]:
        assert ev.revizyon_izinli_mi(eski, yeni, yaml) == (False, ev.standart_izinli_mi(reddedilen, yaml)[1])
    eksik = tmp_path / "yok.yaml"
    assert ev.revizyon_izinli_mi("MIL-PRF-99999A.pdf", "MIL-PRF-99999C.pdf", eksik) == (
        False, ev.standart_izinli_mi("MIL-PRF-99999A", eksik)[1])


# --- Streamlit ekranları (streamlit kuruluysa; CI'da arayuz işi) -------------------------------------


@pytest.fixture
def uygulama(tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    db = tmp_path / "k.sqlite"
    betik_yukle("scripts/katalog_kur.py").main(["--db", str(db), "--ornek", "--ornek-kullanicilar"])
    monkeypatch.setenv("MALZEME_KABUL_DB", str(db))
    monkeypatch.setenv("MALZEME_KABUL_YUKLEME", str(tmp_path / "yuklenen"))

    def ac(ad=None, parola=None):
        at = AppTest.from_file(str(UYGULAMA), default_timeout=60).run()
        if ad:
            at.text_input[0].input(ad)
            at.text_input[1].input(parola)
            at.button[0].click().run()
        return at, db

    return ac


def test_ekran_giris_yanlis_parola(uygulama):
    at, _ = uygulama("gk", "yanlis-parola")
    assert not at.exception and "yanlış" in at.error[0].value and not at.sidebar.radio


def test_ekran_giris_kalite_rolu_yalniz_kendi_ekranlarini_gorur(uygulama):
    at, _ = uygulama("gk", "gk-ornek-parola")
    assert not at.exception
    assert at.sidebar.radio[0].options == ["Giriş kalite: CoC kontrolü", "Depo: partiler ve raf ömrü"]
    assert at.header[0].value == "Giriş kalite: CoC kontrolü"
    assert any("Kabul dokümanı: MIL-PRF-23377K v1" in c.value for c in at.caption)


def test_ekran_mp_rolu_ve_depo(uygulama):
    at, _ = uygulama("mp", "mp-ornek-parola")
    assert at.sidebar.radio[0].options == ["Standart yükle", "Taslağı düzelt ve onayla",
                                           "Revizyon farkı ve M&P incelemesi", "Depo: partiler ve raf ömrü"]
    at.sidebar.radio[0].set_value("depo").run()
    assert not at.exception and at.dataframe and "raf ömrü uyarısı" in at.warning[0].value


def test_ekran_mp_taslak_ve_revizyon(uygulama):
    at, db = uygulama("mp", "mp-ornek-parola")
    at.sidebar.radio[0].set_value("taslak").run()
    assert "Açık taslak yok" in at.info[0].value
    with Katalog(db) as k:
        k.taslak_kaydet(DOKUMAN, "mp")
    at.sidebar.radio[0].set_value("depo").run()
    at.sidebar.radio[0].set_value("taslak").run()
    assert not at.exception and at.selectbox[0].value.id == 1
    at.sidebar.radio[0].set_value("revizyon").run()
    assert not at.exception and any("MIL-PRF-23377" in m.value for m in at.markdown)
