"""Plan adım 5: düzeltme panosu özeti (malzeme_kabul.kayit.duzeltme_kaydi.duzeltme_panosu)."""

from __future__ import annotations

import pytest

from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kayit import duzeltme_kaydi as dk
from malzeme_kabul.kayit.duzeltme_kaydi import DuzeltmeKaydi, PanoOzeti, duzeltme_panosu
from tests.duzeltme_ornekleri import (
    alan_sayisi,
    dok,
    kirilim_satiri,
    raf,
    taban,
    viskozite_ust,
)

N = alan_sayisi(taban())  # tabandaki alan sayısı: F1 alanları + dolu ek alanlar


@pytest.fixture
def katalog():
    k = Katalog()
    yield k
    k.kapat()


def akis(katalog, surumler, muhendis="mp1", yaklasim="kural", onayla=True, taban_kaydet=True) -> int:
    """Taslak kurar, `surumler` sırasıyla düzeltir, istenirse onaylar (alttaki API ile)."""
    kaydi = DuzeltmeKaydi(katalog.baglanti)
    t = katalog.taslak_kaydet(taban(), muhendis)
    if taban_kaydet:
        kaydi.taban_kaydet(t.id, taban(), {"yaklasim": yaklasim})
    eski = taban()
    for yeni in surumler:
        kaydi.duzeltmeleri_kaydet(t.id, eski, yeni, muhendis)
        katalog.taslak_guncelle(t.id, yeni)
        eski = yeni
    if onayla:
        katalog.taslagi_onayla(t.id, muhendis)
        kaydi.onaylari_kaydet(t.id, eski, muhendis)
    return t.id


def test_bos_veritabaninda_oran_sifirdir(katalog):
    DuzeltmeKaydi(katalog.baglanti)
    p = duzeltme_panosu(katalog.baglanti)
    assert isinstance(p, PanoOzeti)
    assert (p.toplam_alan, p.duzeltilen_alan, p.oran, p.onay_bekleyen_duzeltme) == (0, 0, 0.0, 0)


def test_iki_alan_duzeltilen_onayli_taslakta_oran_iki_bolu_alan_sayisidir(katalog):
    akis(katalog, [viskozite_ust(35.0, kap_omru_ust=80.0)])
    p = duzeltme_panosu(katalog.baglanti)
    assert (p.toplam_alan, p.duzeltilen_alan) == (N, 2)
    assert p.oran == pytest.approx(2 / N)


def test_hic_duzeltilmeyen_onayli_taslakta_oran_sifirdir(katalog):
    akis(katalog, [])
    p = duzeltme_panosu(katalog.baglanti)
    assert (p.toplam_alan, p.duzeltilen_alan, p.oran) == (N, 0, 0.0)


def test_ayni_alan_icin_birden_cok_olay_tek_alan_sayilir(katalog):
    akis(katalog, [viskozite_ust(35.0), viskozite_ust(36.0), viskozite_ust(37.0)])
    p = duzeltme_panosu(katalog.baglanti)
    assert (p.toplam_alan, p.duzeltilen_alan) == (N, 1)


def test_degistirilip_geri_alinan_alan_duzeltilmis_sayilmaz(katalog):
    akis(katalog, [viskozite_ust(35.0), taban()])
    assert duzeltme_panosu(katalog.baglanti).duzeltilen_alan == 0


def test_onaylanmamis_taslak_orana_girmez_ama_bekleyen_sayilir(katalog):
    akis(katalog, [viskozite_ust(35.0, kap_omru_ust=80.0)], onayla=False)
    p = duzeltme_panosu(katalog.baglanti)
    assert (p.toplam_alan, p.duzeltilen_alan, p.oran) == (0, 0, 0.0)
    assert p.onay_bekleyen_duzeltme == 2


def test_onayli_ve_bekleyen_taslak_birlikte(katalog):
    akis(katalog, [viskozite_ust(35.0)])
    akis(katalog, [viskozite_ust(35.0, kap_omru_ust=80.0)], onayla=False)
    p = duzeltme_panosu(katalog.baglanti)
    assert (p.toplam_alan, p.duzeltilen_alan, p.onay_bekleyen_duzeltme) == (N, 1, 2)


def test_iki_onayli_taslak_alanlari_toplanir(katalog):
    akis(katalog, [viskozite_ust(35.0)])
    akis(katalog, [viskozite_ust(35.0, kap_omru_ust=80.0)])
    p = duzeltme_panosu(katalog.baglanti)
    assert (p.toplam_alan, p.duzeltilen_alan) == (2 * N, 3)
    assert p.oran == pytest.approx(3 / (2 * N))


# --- kırılımlar -------------------------------------------------------------------------------


def oranli(satir, toplam, duzeltilen):
    return satir["toplam"] == toplam and satir["duzeltilen"] == duzeltilen and satir["oran"] == pytest.approx(duzeltilen / toplam)


def test_belge_bazinda_kirilim(katalog):
    akis(katalog, [viskozite_ust(35.0)])
    assert oranli(kirilim_satiri(duzeltme_panosu(katalog.baglanti).belge_bazinda, "MIL-PRF-23377K"), N, 1)


def test_alan_bazinda_kirilim(katalog):
    akis(katalog, [viskozite_ust(35.0, kap_omru_ust=80.0)])
    p = duzeltme_panosu(katalog.baglanti)
    assert oranli(kirilim_satiri(p.alan_bazinda, "test.sinir.ust"), 2, 2)
    assert oranli(kirilim_satiri(p.alan_bazinda, "test.kaynak.madde"), 2, 0)


def test_kayit_turu_bazinda_kirilim(katalog):
    akis(katalog, [viskozite_ust(35.0)])
    assert oranli(kirilim_satiri(duzeltme_panosu(katalog.baglanti).kayit_turu_bazinda, "test"), N, 1)


def test_yaklasim_bazinda_kirilim(katalog):
    akis(katalog, [viskozite_ust(35.0)], yaklasim="kural")
    akis(katalog, [], yaklasim="dil_modeli")
    p = duzeltme_panosu(katalog.baglanti)
    assert oranli(kirilim_satiri(p.yaklasim_bazinda, "kural"), N, 1)
    assert oranli(kirilim_satiri(p.yaklasim_bazinda, "dil_modeli"), N, 0)


def test_tabani_sonradan_olusan_taslak_bilinmiyor_yaklasiminda_sayilir(katalog):
    akis(katalog, [viskozite_ust(35.0)], taban_kaydet=False)
    assert oranli(kirilim_satiri(duzeltme_panosu(katalog.baglanti).yaklasim_bazinda, "bilinmiyor"), N, 1)


def test_bos_veritabaninda_tabani_bilinmeyen_taslak_sifirdir(katalog):
    DuzeltmeKaydi(katalog.baglanti)
    assert duzeltme_panosu(katalog.baglanti).tabani_bilinmeyen_taslak == 0


def test_tabani_bilinmeyen_taslak_ana_orana_ve_kirilimlara_girmez(katalog):
    akis(katalog, [viskozite_ust(35.0)], taban_kaydet=False)
    p = duzeltme_panosu(katalog.baglanti)
    assert (p.toplam_alan, p.duzeltilen_alan, p.oran) == (0, 0, 0.0)
    assert p.tabani_bilinmeyen_taslak == 1
    assert p.belge_bazinda == [] and p.alan_bazinda == [] and p.kayit_turu_bazinda == []
    assert p.muhendis_bazinda == [] and not p.gun_bazinda


def test_tabani_bilinen_ve_bilinmeyen_taslak_birlikte_yalniz_bilinen_orana_girer(katalog):
    akis(katalog, [viskozite_ust(35.0)], muhendis="mp1", yaklasim="kural")
    akis(katalog, [viskozite_ust(35.0, kap_omru_ust=80.0)], muhendis="mp9", taban_kaydet=False)
    p = duzeltme_panosu(katalog.baglanti)
    assert (p.toplam_alan, p.duzeltilen_alan) == (N, 1)
    assert p.oran == pytest.approx(1 / N)
    assert p.tabani_bilinmeyen_taslak == 1
    assert oranli(kirilim_satiri(p.belge_bazinda, "MIL-PRF-23377K"), N, 1)
    assert oranli(kirilim_satiri(p.alan_bazinda, "test.sinir.ust"), 2, 1)
    assert oranli(kirilim_satiri(p.kayit_turu_bazinda, "test"), N, 1)
    assert [s["muhendis"] for s in p.muhendis_bazinda] == ["mp1"]
    assert list(p.gun_bazinda.values()) == [pytest.approx(1 / N)]
    assert oranli(kirilim_satiri(p.yaklasim_bazinda, "kural"), N, 1)
    assert oranli(kirilim_satiri(p.yaklasim_bazinda, "bilinmiyor"), N, 2)


def test_muhendis_bazinda_kirilim(katalog):
    akis(katalog, [viskozite_ust(35.0)], muhendis="mp1")
    akis(katalog, [], muhendis="mp2")
    p = duzeltme_panosu(katalog.baglanti)
    assert oranli(kirilim_satiri(p.muhendis_bazinda, "mp1"), N, 1)
    assert oranli(kirilim_satiri(p.muhendis_bazinda, "mp2"), N, 0)


def test_gun_bazinda_onay_gununun_orani(katalog):
    tid = akis(katalog, [viskozite_ust(35.0)])
    gunler = duzeltme_panosu(katalog.baglanti).gun_bazinda
    # Beklenen gün saatten değil onay olaylarının zamanından okunur (gece yarısında kırılmasın).
    onay_gunleri = {o.zaman[:10] for o in DuzeltmeKaydi(katalog.baglanti).olaylar(tid) if o.islem == "onayla"}
    assert len(onay_gunleri) == 1
    assert [str(g) for g in gunler] == sorted(onay_gunleri)
    assert list(gunler.values()) == [pytest.approx(1 / N)]


# --- kişi ve gün atfı ---------------------------------------------------------------------------


def test_duzelten_ve_onaylayan_farkliysa_duzeltilen_alan_duzeltene_onaylanan_alan_onaylayana_sayilir(katalog):
    kaydi = DuzeltmeKaydi(katalog.baglanti)
    t = katalog.taslak_kaydet(taban(), "mp1")
    kaydi.taban_kaydet(t.id, taban(), {"yaklasim": "kural"})
    yeni = viskozite_ust(35.0, kap_omru_ust=80.0)
    kaydi.duzeltmeleri_kaydet(t.id, taban(), yeni, "mp1")
    katalog.taslak_guncelle(t.id, yeni)
    katalog.taslagi_onayla(t.id, "mp2")
    kaydi.onaylari_kaydet(t.id, yeni, "mp2")
    p = duzeltme_panosu(katalog.baglanti)
    assert oranli(kirilim_satiri(p.muhendis_bazinda, "mp1"), 2, 2)
    assert oranli(kirilim_satiri(p.muhendis_bazinda, "mp2"), N - 2, 0)
    assert sum(s["toplam"] for s in p.muhendis_bazinda) == p.toplam_alan == N


def test_ayni_alani_iki_muhendis_duzeltirse_alan_son_duzeltene_sayilir(katalog):
    kaydi = DuzeltmeKaydi(katalog.baglanti)
    t = katalog.taslak_kaydet(taban(), "mp1")
    kaydi.taban_kaydet(t.id, taban(), {"yaklasim": "kural"})
    ilk, ikinci = viskozite_ust(35.0, kap_omru_ust=80.0), viskozite_ust(36.0, kap_omru_ust=80.0)
    kaydi.duzeltmeleri_kaydet(t.id, taban(), ilk, "mp1")
    katalog.taslak_guncelle(t.id, ilk)
    kaydi.duzeltmeleri_kaydet(t.id, ilk, ikinci, "mp3")
    katalog.taslak_guncelle(t.id, ikinci)
    katalog.taslagi_onayla(t.id, "mp2")
    kaydi.onaylari_kaydet(t.id, ikinci, "mp2")
    p = duzeltme_panosu(katalog.baglanti)
    assert oranli(kirilim_satiri(p.muhendis_bazinda, "mp1"), 1, 1)  # kap ömrü üst sınırı
    assert oranli(kirilim_satiri(p.muhendis_bazinda, "mp3"), 1, 1)  # viskozite üst sınırı
    assert oranli(kirilim_satiri(p.muhendis_bazinda, "mp2"), N - 2, 0)


def test_butun_alanlari_duzeltilen_taslak_duzeltme_gununde_degil_onay_gununde_sayilir(katalog, monkeypatch):
    # Raf ömrünün kap türü değişince eski kaydın bütün alanları silinir, yeninin bütün alanları eklenir:
    # net değişmemiş alan kalmaz, onayda hiç `onayla` olayı yazılmaz.
    eski, yeni = dok([], raf=[raf()]), dok([], raf=[raf().model_copy(update={"kap_turu": "kit"})])
    kaydi = DuzeltmeKaydi(katalog.baglanti)
    t = katalog.taslak_kaydet(eski, "mp1")
    kaydi.taban_kaydet(t.id, eski, {"yaklasim": "kural"})
    with monkeypatch.context() as m:
        m.setattr(dk, "_simdi", lambda: "2000-01-01T12:00:00.000000+00:00")
        kaydi.duzeltmeleri_kaydet(t.id, eski, yeni, "mp1")
    katalog.taslak_guncelle(t.id, yeni)
    surum = katalog.taslagi_onayla(t.id, "mp2")
    kaydi.onaylari_kaydet(t.id, yeni, "mp2")
    assert [o.islem for o in kaydi.olaylar(t.id) if o.islem == "onayla"] == []
    gunler = duzeltme_panosu(katalog.baglanti).gun_bazinda
    assert "2000-01-01" not in gunler
    assert [str(g) for g in gunler] == [surum.onay_zamani[:10]]
    assert list(gunler.values()) == [pytest.approx(1.0)]


def test_pano_paydasi_ek_alanlari_icerir(katalog):
    akis(katalog, [])
    p = duzeltme_panosu(katalog.baglanti)
    assert p.toplam_alan == alan_sayisi(taban())
    assert kirilim_satiri(p.alan_bazinda, "test.kaynak.sayfa")["toplam"] == 2
    assert kirilim_satiri(p.alan_bazinda, "test.sonuc_kaynagi")["toplam"] == 2
