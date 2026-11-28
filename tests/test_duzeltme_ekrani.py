"""Plan adım 3-5: düzeltme olaylarının ekran işlerine bağlanması, pano ekranı ve etiket adayı betiği."""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from malzeme_kabul.arayuz import ekran_verisi as ev
from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.kayit.duzeltme_kaydi import DuzeltmeKaydi
from malzeme_kabul.sozlesme.alanlar import alanlari_duzlestir
from malzeme_kabul.sozlesme.sema import KabulDokumani
from tests.conftest import betik_yukle
from tests.duzeltme_ornekleri import alan_anahtarlari, alan_sayisi, taban, viskozite_ust

UST = ("test.sinir.ust", "viskozite")


@pytest.fixture
def katalog():
    k = Katalog()
    yield k
    k.kapat()


@pytest.fixture
def bolunme(tmp_path):
    yaml = tmp_path / "bolunme.yaml"
    yaml.write_text("gelistirme:\n  - MIL-PRF-23377K\ntest:\n  - MIL-PRF-87937D\n", encoding="utf-8")
    return yaml


@pytest.fixture
def sahte_cikarici(monkeypatch):
    """Kural çıkarıcı gerçek PDF ister; burada küçük tabanı döner."""
    monkeypatch.setattr(ev, "cikar", lambda pdf_yolu, belge_no, revizyon: taban())


def yukle(katalog, tmp_path, bolunme):
    return ev.standart_yukle(katalog, tmp_path / "MIL-PRF-23377K.pdf", "mp1", bolunme)


# --- standart_yukle ----------------------------------------------------------------------------


def test_standart_yukle_tabani_kaydeder(katalog, tmp_path, bolunme, sahte_cikarici):
    t = yukle(katalog, tmp_path, bolunme)
    kaydi = DuzeltmeKaydi(katalog.baglanti)
    assert alanlari_duzlestir(kaydi.taban(t.id)) == alanlari_duzlestir(taban())


def test_standart_yukle_tabanin_ureteni_kuraldir(katalog, tmp_path, bolunme, sahte_cikarici):
    t = yukle(katalog, tmp_path, bolunme)
    assert DuzeltmeKaydi(katalog.baglanti).ureten(t.id)["yaklasim"] == "kural"


# --- taslak_duzelt ----------------------------------------------------------------------------------


def test_taslak_duzelt_olay_yazar_ve_gerekceyi_gecirir(katalog, tmp_path, bolunme, sahte_cikarici):
    t = yukle(katalog, tmp_path, bolunme)
    d = DenetimKaydi(katalog.baglanti)
    ev.taslak_duzelt(katalog, d, t.id, viskozite_ust(35.0), "mp1", gerekce="tabloda 35 s")
    (o,) = DuzeltmeKaydi(katalog.baglanti).olaylar(t.id)
    assert ((o.alan, o.kayit), o.islem, o.muhendis, o.gerekce) == (UST, "degistir", "mp1", "tabloda 35 s")


def test_taslak_duzelt_gerekcesiz_de_calisir(katalog, tmp_path, bolunme, sahte_cikarici):
    t = yukle(katalog, tmp_path, bolunme)
    ev.taslak_duzelt(katalog, DenetimKaydi(katalog.baglanti), t.id, viskozite_ust(35.0), "mp1")
    (o,) = DuzeltmeKaydi(katalog.baglanti).olaylar(t.id)
    assert o.gerekce is None


def test_farksiz_taslak_duzelt_olay_yazmaz(katalog, tmp_path, bolunme, sahte_cikarici):
    t = yukle(katalog, tmp_path, bolunme)
    assert ev.taslak_duzelt(katalog, DenetimKaydi(katalog.baglanti), t.id, taban(), "mp1") == []
    assert DuzeltmeKaydi(katalog.baglanti).olaylar(t.id) == []


def test_olay_yazimi_duserse_taslak_ve_denetim_kaydi_geri_alinir(katalog, tmp_path, bolunme, sahte_cikarici, monkeypatch):
    t = yukle(katalog, tmp_path, bolunme)
    d = DenetimKaydi(katalog.baglanti)

    def patlat(*args, **kwargs):
        raise RuntimeError("olay yazılamadı")

    monkeypatch.setattr(DuzeltmeKaydi, "duzeltmeleri_kaydet", patlat)
    with pytest.raises(RuntimeError):
        ev.taslak_duzelt(katalog, d, t.id, viskozite_ust(35.0), "mp1")
    assert katalog.taslak(t.id).dokuman.testler[0].sinir.ust == 30.0
    assert d.kayitlar() == []
    assert DuzeltmeKaydi(katalog.baglanti).olaylar(t.id) == []


def test_tabani_olmayan_eski_taslakta_ilk_duzeltme_tabani_kurar(katalog):
    t = katalog.taslak_kaydet(taban(), "mp1")  # standart_yukle'siz (eski) taslak
    ev.taslak_duzelt(katalog, DenetimKaydi(katalog.baglanti), t.id, viskozite_ust(35.0), "mp1")
    kaydi = DuzeltmeKaydi(katalog.baglanti)
    assert kaydi.ureten(t.id) == {"yaklasim": "bilinmiyor"}
    assert kaydi.taban(t.id).testler[0].sinir.ust == 30.0


# --- taslak_onayla -------------------------------------------------------------------------------------


def test_taslak_onayla_onay_olaylarini_yazar(katalog, tmp_path, bolunme, sahte_cikarici):
    t = yukle(katalog, tmp_path, bolunme)
    d = DenetimKaydi(katalog.baglanti)
    ev.taslak_duzelt(katalog, d, t.id, viskozite_ust(35.0), "mp1")
    ev.taslak_onayla(katalog, d, t.id, "mp1")
    onaylar = [o for o in DuzeltmeKaydi(katalog.baglanti).olaylar(t.id) if o.islem == "onayla"]
    assert {(o.alan, o.kayit) for o in onaylar} == alan_anahtarlari(taban()) - {UST}
    assert all(o.muhendis == "mp1" for o in onaylar)


def test_ekran_akisi_panoda_gorunur(katalog, tmp_path, bolunme, sahte_cikarici):
    from malzeme_kabul.kayit.duzeltme_kaydi import duzeltme_panosu

    t = yukle(katalog, tmp_path, bolunme)
    d = DenetimKaydi(katalog.baglanti)
    ev.taslak_duzelt(katalog, d, t.id, viskozite_ust(35.0, kap_omru_ust=80.0), "mp1")
    ev.taslak_onayla(katalog, d, t.id, "mp1")
    p = duzeltme_panosu(katalog.baglanti)
    n = alan_sayisi(taban())
    assert (p.toplam_alan, p.duzeltilen_alan) == (n, 2) and p.oran == pytest.approx(2 / n)


# --- komut satırı: scripts/etiket_adaylari.py -----------------------------------------------------------


def onayli_db(tmp_path, monkeypatch, adet: int = 1) -> Path:
    monkeypatch.setattr(ev, "cikar", lambda pdf_yolu, belge_no, revizyon: taban())
    yaml = tmp_path / "bolunme.yaml"
    yaml.write_text("gelistirme:\n  - MIL-PRF-23377K\n", encoding="utf-8")
    db = tmp_path / "k.sqlite"
    with Katalog(db) as k:
        d = DenetimKaydi(k.baglanti)
        for _ in range(adet):
            t = ev.standart_yukle(k, tmp_path / "MIL-PRF-23377K.pdf", "mp1", yaml)
            ev.taslak_duzelt(k, d, t.id, viskozite_ust(35.0), "mp1")
            ev.taslak_onayla(k, d, t.id, "mp1")
    return db


def test_etiket_adaylari_betigi_onayli_taslaklari_disa_verir(tmp_path, monkeypatch, capsys):
    db = onayli_db(tmp_path, monkeypatch)
    klasor = tmp_path / "adaylar"
    assert betik_yukle("scripts/etiket_adaylari.py").main(["--db", str(db), "--klasor", str(klasor)]) == 0
    assert sorted(p.name for p in klasor.iterdir()) == ["MIL-PRF-23377K_taslak1.json", "MIL-PRF-23377K_taslak1.olaylar.jsonl"]


def test_etiket_adaylari_betigi_duzeltme_oranini_basar(tmp_path, monkeypatch, capsys):
    db = onayli_db(tmp_path, monkeypatch)
    betik_yukle("scripts/etiket_adaylari.py").main(["--db", str(db), "--klasor", str(tmp_path / "adaylar")])
    assert "düzeltme oranı" in capsys.readouterr().out.lower()


def test_etiket_adaylari_betigi_gold_klasorune_yazmaz(tmp_path, monkeypatch):
    db = onayli_db(tmp_path, monkeypatch)
    gold = tmp_path / "data" / "gold"
    kod = betik_yukle("scripts/etiket_adaylari.py").main(["--db", str(db), "--klasor", str(gold)])
    assert kod == 2
    assert not gold.exists() or not any(gold.iterdir())


def test_etiket_adaylari_betigi_buyuk_harfli_gold_klasorunde_2_doner(tmp_path, monkeypatch):
    db = onayli_db(tmp_path, monkeypatch)
    gold = tmp_path / "data" / "Gold"
    kod = betik_yukle("scripts/etiket_adaylari.py").main(["--db", str(db), "--klasor", str(gold)])
    assert kod == 2
    assert not gold.exists() or not any(gold.iterdir())


def _aday_adlari(tid: int) -> tuple[str, str]:
    return f"MIL-PRF-23377K_taslak{tid}.json", f"MIL-PRF-23377K_taslak{tid}.olaylar.jsonl"


def test_etiket_adaylari_betigi_var_olan_aday_dosyasinin_uzerine_yazmaz(tmp_path, monkeypatch, capsys):
    db = onayli_db(tmp_path, monkeypatch)
    klasor = tmp_path / "adaylar"
    betik = betik_yukle("scripts/etiket_adaylari.py")
    betik.main(["--db", str(db), "--klasor", str(klasor)])
    for ad in _aday_adlari(1):
        (klasor / ad).write_text("ELLE DUZELTILDI", encoding="utf-8")
    capsys.readouterr()
    betik.main(["--db", str(db), "--klasor", str(klasor)])
    assert all((klasor / ad).read_text(encoding="utf-8") == "ELLE DUZELTILDI" for ad in _aday_adlari(1))
    assert "atlandı" in capsys.readouterr().out


def test_etiket_adaylari_betigi_uzerine_yaz_secenegiyle_var_olan_adayi_yeniler(tmp_path, monkeypatch):
    db = onayli_db(tmp_path, monkeypatch)
    klasor = tmp_path / "adaylar"
    betik = betik_yukle("scripts/etiket_adaylari.py")
    betik.main(["--db", str(db), "--klasor", str(klasor)])
    json_adi, olay_adi = _aday_adlari(1)
    for ad in (json_adi, olay_adi):
        (klasor / ad).write_text("ELLE DUZELTILDI", encoding="utf-8")
    assert betik.main(["--db", str(db), "--klasor", str(klasor), "--uzerine-yaz"]) == 0
    okunan = KabulDokumani.model_validate_json((klasor / json_adi).read_text(encoding="utf-8"))
    assert okunan.testler[0].sinir.ust == 35.0
    assert (klasor / olay_adi).read_text(encoding="utf-8") != "ELLE DUZELTILDI"


def test_etiket_adaylari_betigi_bir_taslakta_hata_olsa_da_digerlerini_disa_verir_ve_2_doner(tmp_path, monkeypatch):
    db = onayli_db(tmp_path, monkeypatch, adet=2)
    klasor = tmp_path / "adaylar"
    betik = betik_yukle("scripts/etiket_adaylari.py")
    gercek = betik.etiket_adayi_yaz

    def ilkinde_patla(katalog, taslak_id, *args, **kwargs):
        if taslak_id == 1:
            raise OSError("disk yazılamadı")
        return gercek(katalog, taslak_id, *args, **kwargs)

    monkeypatch.setattr(betik, "etiket_adayi_yaz", ilkinde_patla)
    assert betik.main(["--db", str(db), "--klasor", str(klasor)]) == 2
    assert sorted(p.name for p in klasor.iterdir()) == sorted(_aday_adlari(2))


# --- gözden geçirme: ek alanlar ekrandan düzeltilince olay olur ------------------------------------------


@pytest.mark.parametrize("sutun, yeni_deger, alan, eski_deger", [
    ("sayfa", 6, "test.kaynak.sayfa", 5),
    ("orijinal_metin", "20 - 35 s", "test.sinir.orijinal_metin", "20 to 30 s"),
    ("sonuc_kaynagi", "ic_laboratuvar", "test.sonuc_kaynagi", "coc"),
])
def test_tablodan_yalniz_ek_alan_degisince_taslak_duzelt_degistir_olayi_yazar(
        katalog, tmp_path, bolunme, sahte_cikarici, sutun, yeni_deger, alan, eski_deger):
    t = yukle(katalog, tmp_path, bolunme)
    satirlar = ev.test_tablosu(t.dokuman)
    assert satirlar[0]["id"] == "viskozite"
    satirlar[0][sutun] = yeni_deger
    ev.taslak_duzelt(katalog, DenetimKaydi(katalog.baglanti), t.id, ev.tablodan_dokuman(t.dokuman, satirlar), "mp1")
    olaylar = DuzeltmeKaydi(katalog.baglanti).olaylar(t.id)
    assert [(o.kayit_turu, o.kayit, o.alan, o.islem, o.eski_deger, o.yeni_deger) for o in olaylar] == [
        ("test", "viskozite", alan, "degistir", eski_deger, yeni_deger)]


def test_yalniz_sayfa_duzeltilen_taslak_panoda_sayfa_alani_duzeltilmis_sayilir(katalog, tmp_path, bolunme,
                                                                                sahte_cikarici):
    from malzeme_kabul.kayit.duzeltme_kaydi import duzeltme_panosu
    from tests.duzeltme_ornekleri import kirilim_satiri

    t = yukle(katalog, tmp_path, bolunme)
    d = DenetimKaydi(katalog.baglanti)
    satirlar = ev.test_tablosu(t.dokuman)
    satirlar[0]["sayfa"] = 6
    ev.taslak_duzelt(katalog, d, t.id, ev.tablodan_dokuman(t.dokuman, satirlar), "mp1")
    ev.taslak_onayla(katalog, d, t.id, "mp1")
    p = duzeltme_panosu(katalog.baglanti)
    assert (p.toplam_alan, p.duzeltilen_alan) == (alan_sayisi(taban()), 1)
    assert p.oran == pytest.approx(1 / alan_sayisi(taban()))
    satir = kirilim_satiri(p.alan_bazinda, "test.kaynak.sayfa")
    assert (satir["toplam"], satir["duzeltilen"]) == (2, 1)


# --- gözden geçirme: tek işlem geri almaları ---------------------------------------------------------------


def _patlat(*args, **kwargs):
    raise RuntimeError("yazılamadı")


def test_taban_kaydi_duserse_standart_yukle_taslagi_kaydetmez(katalog, tmp_path, bolunme, sahte_cikarici, monkeypatch):
    monkeypatch.setattr(DuzeltmeKaydi, "taban_kaydet", _patlat)
    with pytest.raises(RuntimeError):
        yukle(katalog, tmp_path, bolunme)
    assert katalog.taslaklar() == []


def test_onay_olaylari_duserse_taslak_onayla_hicbir_seyi_yazmaz(katalog, tmp_path, bolunme, sahte_cikarici,
                                                                 monkeypatch):
    t = yukle(katalog, tmp_path, bolunme)
    d = DenetimKaydi(katalog.baglanti)
    ev.taslak_duzelt(katalog, d, t.id, viskozite_ust(35.0), "mp1")
    kayit_sayisi = len(d.kayitlar())
    monkeypatch.setattr(DuzeltmeKaydi, "onaylari_kaydet", _patlat)
    with pytest.raises(RuntimeError):
        ev.taslak_onayla(katalog, d, t.id, "mp1")
    assert katalog.taslak(t.id).durum == "taslak"
    assert katalog.dokuman_surumleri("MIL-PRF-23377", "K") == []
    assert d.kayitlar(tur="onay") == [] and len(d.kayitlar()) == kayit_sayisi
    assert [o for o in DuzeltmeKaydi(katalog.baglanti).olaylar(t.id) if o.islem == "onayla"] == []


# --- gözden geçirme: taslak_duzelt eski dokümanı yazma işleminin içinde okur -------------------------------


def test_taslak_duzelt_eski_dokumani_yazma_isleminin_icinde_okur(katalog, tmp_path, bolunme, sahte_cikarici,
                                                                  monkeypatch):
    t = yukle(katalog, tmp_path, bolunme)
    d = DenetimKaydi(katalog.baglanti)
    gercek = katalog.taslak
    islemde_mi: list[bool] = []

    def izle(taslak_id):
        islemde_mi.append(katalog.baglanti.in_transaction)
        return gercek(taslak_id)

    monkeypatch.setattr(katalog, "taslak", izle)
    ev.taslak_duzelt(katalog, d, t.id, viskozite_ust(35.0), "mp1")
    assert islemde_mi, "taslak_duzelt taslağı okumadı"
    assert all(islemde_mi), f"taslak işlem dışında okundu: {islemde_mi}"
    (o,) = DuzeltmeKaydi(katalog.baglanti).olaylar(t.id)
    assert (o.eski_deger, o.yeni_deger) == (30.0, 35.0)


# --- gözden geçirme: uygulama.etiket_adayi_kaydet (onaydan sonra etiket adayı) -----------------------------


@pytest.fixture
def uygulama():
    pytest.importorskip("streamlit")
    from malzeme_kabul.arayuz import uygulama as modul

    return modul


def _onayli(katalog, tmp_path, bolunme) -> int:
    t = yukle(katalog, tmp_path, bolunme)
    d = DenetimKaydi(katalog.baglanti)
    ev.taslak_duzelt(katalog, d, t.id, viskozite_ust(35.0), "mp1")
    ev.taslak_onayla(katalog, d, t.id, "mp1")
    return t.id


def test_etiket_adayi_kaydet_basarida_yollari_ve_none_doner(uygulama, katalog, tmp_path, bolunme, sahte_cikarici):
    tid = _onayli(katalog, tmp_path, bolunme)
    klasor = tmp_path / "adaylar"
    yollar, hata = uygulama.etiket_adayi_kaydet(katalog, tid, klasor)
    assert hata is None
    assert sorted(Path(p).name for p in yollar) == sorted(_aday_adlari(tid))
    assert all(Path(p).is_file() for p in yollar)


@pytest.mark.parametrize("istisna", [
    sqlite3.OperationalError("database is locked"),
    sqlite3.DatabaseError("veritabanı bozuk"),
    OSError("disk dolu"),
    ValueError("gold klasörüne yazılmaz"),
])
def test_etiket_adayi_kaydet_hatada_onayi_bozmaz_ve_uyari_metni_doner(uygulama, katalog, tmp_path, bolunme,
                                                                       sahte_cikarici, monkeypatch, istisna):
    tid = _onayli(katalog, tmp_path, bolunme)

    def patla(*args, **kwargs):
        raise istisna

    monkeypatch.setattr(uygulama, "etiket_adayi_yaz", patla)
    yollar, hata = uygulama.etiket_adayi_kaydet(katalog, tid, tmp_path / "adaylar")
    assert list(yollar) == []
    assert isinstance(hata, str) and str(istisna) in hata
    assert "kaydedilmedi" not in hata.casefold()
    assert katalog.taslak(tid).durum == "onaylandi"


def test_taslak_ekrani_etiket_adayini_etiket_adayi_kaydet_ile_yazar(uygulama):
    kaynak = inspect.getsource(uygulama.taslak_ekrani)
    assert "etiket_adayi_kaydet(" in kaynak
    assert "etiket_adayi_yaz(" not in kaynak
