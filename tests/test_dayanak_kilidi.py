"""Karar dayanağı denetimi kilit altında çalışır (PR #79 regresyonu).

`malzeme_koduyla_kontrol` parti durumunu yazan `katalog.islem()` (BEGIN
IMMEDIATE) içinde geçerli sürümü ve malzemeyi `_dayanak_denetimi` ile yeniden
okur. Yazma kilidi bu işlem boyunca tutulduğu için yeniden okuma ile durum
yazımı arasında başka bir bağlantı yeni sürüm onaylayamaz: ikinci bağlantının
`dokuman_onayla` denemesi beklemeden (busy_timeout = 0) "database is locked"
alır. `_dayanak_denetimi` çağrısı işlemin dışına taşınırsa
`test_dayanak_denetimi_acik_islemin_icinde_cagrilir` ve
`test_dayanak_okumasindan_sonra_durum_yazilana_kadar_ikinci_baglanti_onaylayamaz`
düşer.

Katalog `tmp_path` altında dosya tabanlıdır; data/ altına yazılmaz. Dil
modeli kullanılmaz.
"""

from __future__ import annotations

import sqlite3

import pytest

from malzeme_kabul.hat import katalog_karari
from malzeme_kabul.hat.katalog_karari import dokuman_onayla, malzeme_koduyla_kontrol
from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.sozlesme.sema import KabulDokumani, StandartBilgisi
from malzeme_kabul.sozlesme.sertifika import Sertifika, SertifikaSatiri
from tests.test_katalog_karari import _test

TEDARIKCI = "Ted A"
LOT = "L1"
V1, V2 = "MIL-PRF-23377K v1", "MIL-PRF-23377K v2"


def dokuman(krom: bool) -> KabulDokumani:
    testler = [_test("voc", "VOC content", 340.0)]
    if krom:
        testler.append(_test("krom", "Chromium content", 0.01, birim="percent"))
    return KabulDokumani(standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"), testler=testler)


def sertifika() -> Sertifika:
    return Sertifika(
        sertifika_no="S1", standart_atfi="MIL-PRF-23377K Type I Class N", tedarikci=TEDARIKCI, parti_no=LOT,
        satirlar=[SertifikaSatiri(test_adi="VOC content", sonuc="300", birim="g/L")],
    )


@pytest.fixture
def ortam(tmp_path):
    """Birinci bağlantı (karar veren) ve önceden açılmış, beklemeyen ikinci bağlantı (M&P)."""
    yol = tmp_path / "katalog.db"
    k = Katalog(yol)
    defter = DenetimKaydi(k.baglanti)
    dokuman_onayla(k, defter, dokuman(krom=False), "mp1")
    k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
    k.tedarikci_onayla("AST-N", TEDARIKCI)
    k.parti_ekle(LOT, "AST-N", TEDARIKCI, "K", "2026-06-01")
    ikinci = Katalog(yol)
    ikinci.baglanti.execute("PRAGMA busy_timeout = 0")  # timeout=0: kilit varsa hemen hata
    yield k, defter, ikinci
    ikinci.kapat()
    k.kapat()


def ikinci_onaylamayi_dener(ikinci: Katalog) -> None:
    dokuman_onayla(ikinci, DenetimKaydi(ikinci.baglanti), dokuman(krom=True), "mp2", "krom eklendi")


def karar_ver(k: Katalog, defter: DenetimKaydi):
    return malzeme_koduyla_kontrol(k, "AST-N", sertifika(), lot_no=LOT, defter=defter, kullanici="gk1")


def dayanak_satirlari(karar) -> list:
    return [s for s in karar.ek_denetimler if s.test_id == "dokuman_dayanagi"]


def test_kontrol_ortami_kilit_yokken_ikinci_baglanti_onaylayabilir(ortam):
    """Kontrol: kilitlenme testleri ikinci bağlantının kendisinden değil, kilitten kaynaklanır."""
    k, _, ikinci = ortam
    ikinci_onaylamayi_dener(ikinci)
    assert k.gecerli_dokuman("AST-N").etiket == V2


def test_parti_okunurken_ikinci_baglanti_dokuman_onaylayamaz_database_is_locked(ortam, monkeypatch):
    k, defter, ikinci = ortam
    hatalar: list[Exception] = []
    asil = k.parti

    def sarili_parti(*a, **kw):
        assert k.baglanti.in_transaction
        try:
            ikinci_onaylamayi_dener(ikinci)
        except sqlite3.OperationalError as hata:
            hatalar.append(hata)
        return asil(*a, **kw)

    monkeypatch.setattr(k, "parti", sarili_parti)
    karar = karar_ver(k, defter)
    monkeypatch.undo()

    # parti işlem içinde birden çok kez okunabilir; her denemede kilit tutulur.
    assert hatalar and all("database is locked" in str(h) for h in hatalar)
    assert not ikinci.baglanti.in_transaction
    assert k.gecerli_dokuman("AST-N").etiket == V1  # onay gerçekleşmedi
    assert karar.dokuman_surumu == V1 and dayanak_satirlari(karar) == []


def test_parti_okunurken_onay_reddedilince_karar_v1_ile_tutarli_yazilir(ortam, monkeypatch):
    k, defter, ikinci = ortam
    asil = k.parti

    def sarili_parti(*a, **kw):
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            ikinci_onaylamayi_dener(ikinci)
        return asil(*a, **kw)

    monkeypatch.setattr(k, "parti", sarili_parti)
    karar = karar_ver(k, defter)
    monkeypatch.undo()
    assert karar.parti_karari == "kabul" and k.parti("AST-N", LOT).durum == "serbest"
    (kayit,) = defter.kayitlar("karar")
    assert kayit.dokuman_surumu == V1
    # Kilit bırakıldıktan sonra onay mümkündür.
    ikinci_onaylamayi_dener(ikinci)
    assert k.gecerli_dokuman("AST-N").etiket == V2


def test_dayanak_denetimi_acik_islemin_icinde_cagrilir(ortam, monkeypatch):
    k, defter, _ = ortam
    asil = katalog_karari._dayanak_denetimi
    islemde: list[bool] = []

    def sarili(katalog, *a, **kw):
        islemde.append(katalog.baglanti.in_transaction)
        return asil(katalog, *a, **kw)

    monkeypatch.setattr(katalog_karari, "_dayanak_denetimi", sarili)
    karar_ver(k, defter)
    assert islemde == [True]


def test_dayanak_denetimi_lotsuz_kararda_da_islemin_icinde_cagrilir(ortam, monkeypatch):
    k, _, _ = ortam
    asil = katalog_karari._dayanak_denetimi
    islemde: list[bool] = []

    def sarili(katalog, *a, **kw):
        islemde.append(katalog.baglanti.in_transaction)
        return asil(katalog, *a, **kw)

    monkeypatch.setattr(katalog_karari, "_dayanak_denetimi", sarili)
    malzeme_koduyla_kontrol(k, "AST-N", sertifika())
    assert islemde == [True]


def test_dayanak_okumasindan_sonra_durum_yazilana_kadar_ikinci_baglanti_onaylayamaz(ortam, monkeypatch):
    """Yeniden okuma ile durum yazımı arasında yeni sürüm onaylanamaz.

    `_dayanak_denetimi` kilit dışına (işlemden önce ya da sonra) taşınırsa
    ikinci bağlantının onayı başarılı olur ve bu test düşer.
    """
    k, defter, ikinci = ortam
    asil = katalog_karari._dayanak_denetimi
    hatalar: list[Exception] = []

    def sarili(*a, **kw):
        sonuc = asil(*a, **kw)
        try:
            ikinci_onaylamayi_dener(ikinci)
        except sqlite3.OperationalError as hata:
            hatalar.append(hata)
        return sonuc

    monkeypatch.setattr(katalog_karari, "_dayanak_denetimi", sarili)
    karar = karar_ver(k, defter)

    assert len(hatalar) == 1 and "database is locked" in str(hatalar[0])
    assert k.gecerli_dokuman("AST-N").etiket == V1
    assert karar.dokuman_surumu == V1
    assert k.parti("AST-N", LOT).durum == "serbest"


def test_islem_baslamadan_once_onaylanan_surum_dayanak_satiriyla_yakalanir(ortam, monkeypatch):
    """Kilitten önce (sürüm okunduktan sonra) onaylanan yeni sürüm kilit altındaki yeniden okumada görülür."""
    k, defter, ikinci = ortam
    asil_islem = k.islem
    onaylandi: list[bool] = []

    def sarili_islem():
        if not onaylandi and not k.baglanti.in_transaction:
            ikinci_onaylamayi_dener(ikinci)  # kilit henüz alınmadı: başarılı olur
            onaylandi.append(True)
        return asil_islem()

    monkeypatch.setattr(k, "islem", sarili_islem)
    karar = karar_ver(k, defter)

    assert onaylandi == [True]
    (dayanak,) = dayanak_satirlari(karar)
    assert dayanak.karar == "insan_incelemeli"
    assert V1 in dayanak.gerekce and V2 in dayanak.gerekce
    assert karar.parti_karari != "kabul" and k.parti("AST-N", LOT).durum != "serbest"
