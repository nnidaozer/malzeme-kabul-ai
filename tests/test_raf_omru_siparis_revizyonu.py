"""Raf ömrü, lotun sipariş revizyonuna bağlıdır (Codex bulgusu; proje sahibi kararı).

Depodaki lot için siparişte yazan revizyon geçerlidir (docs/mimari.md). Malzeme
kodu yeni revizyona taşındığında eski lot eski revizyonun raf ömrünü korur. Lotun
sipariş revizyonu için onaylı kabul dokümanı yoksa süre hesaplanmaz; malzemenin
(daha uzun olabilecek) yeni revizyon süresine asla düşülmez.

Senaryo: MIL-PRF-23377J raf ömrü 6 ay, MIL-PRF-23377K raf ömrü 12 ay.
"""

from __future__ import annotations

from datetime import date

import pytest

from malzeme_kabul.arayuz import ekran_verisi as ev
from malzeme_kabul.hat.raf_omru_raporu import raf_raporu
from malzeme_kabul.hat.revizyon_etkisi import mp_incelemesini_kapat, yeni_revizyon_yukle
from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.sozlesme.sema import KabulDokumani, Kaynak, RafOmru, Sinir, StandartBilgisi, TestSarti

BELGE = "MIL-PRF-23377"
URETIM = date(2026, 1, 15)
J_SON = date(2026, 7, 15)   # üretim + 6 ay
K_SON = date(2027, 1, 15)   # üretim + 12 ay


def dokuman(revizyon: str, sure: int, birim: str = "month", uzatma_testi: str | None = None) -> KabulDokumani:
    kaynak = Kaynak(belge_no=BELGE, revizyon=revizyon, madde="3.9")
    testler = []
    if uzatma_testi:
        testler.append(TestSarti(
            id=uzatma_testi, test_adi=uzatma_testi.title(), test_turleri={"omur_uzatma"}, kaynak=kaynak,
            sinir=Sinir(kriter_turu="gecti_kaldi", orijinal_metin="shall pass"),
        ))
    return KabulDokumani(
        standart=StandartBilgisi(belge_no=BELGE, revizyon=revizyon),
        raf_omurleri=[RafOmru(sure=sure, birim=birim, kaynak=kaynak)],
        testler=testler,
    )


def malzeme_kur(k: Katalog, j_onayli: bool = True) -> None:
    """AST-N malzemesi J'de; ESKI lotu J ile sipariş edildi. K dokümanı onaylı."""
    if j_onayli:
        k.dokuman_onayla(dokuman("J", 6, uzatma_testi="viskozite_j"), "mp1")
    else:
        k.standart_ekle(BELGE, "J")
    k.dokuman_onayla(dokuman("K", 12, uzatma_testi="viskozite_k"), "mp1")
    k.malzeme_ekle("AST-N", BELGE, "J", tip="I", sinif="N")
    k.tedarikci_onayla("AST-N", "Ted A")
    k.parti_ekle("ESKI", "AST-N", "Ted A", "J", URETIM)


def satirlar(k: Katalog, bugun: date = date(2026, 3, 1)) -> dict:
    return {s.parti.lot_no: s for s in raf_raporu(k, bugun)}


# --- malzeme kodu yeni revizyona taşınınca iki lot kendi süresini korur --------------------------


def test_malzeme_yeni_revizyona_tasininca_eski_lot_eski_revizyonun_raf_omrunu_korur():
    with Katalog() as k:
        malzeme_kur(k)
        k.malzeme_revizyonu_ata("AST-N", "K")
        s = satirlar(k)["ESKI"]
    assert s.raf.son_kullanma == J_SON  # K'nın 12 ayı değil
    assert s.dokuman_surumu == f"{BELGE}J v1"


def test_yeni_revizyonla_siparis_edilen_lot_yeni_revizyonun_raf_omrunu_alir():
    with Katalog() as k:
        malzeme_kur(k)
        k.malzeme_revizyonu_ata("AST-N", "K")
        k.parti_ekle("YENI", "AST-N", "Ted A", "K", URETIM)
        r = satirlar(k)
    assert (r["ESKI"].raf.son_kullanma, r["ESKI"].dokuman_surumu) == (J_SON, f"{BELGE}J v1")
    assert (r["YENI"].raf.son_kullanma, r["YENI"].dokuman_surumu) == (K_SON, f"{BELGE}K v1")


def test_malzeme_eski_revizyondayken_yeni_revizyonla_siparis_edilen_lot_kendi_revizyonunu_kullanir():
    # Ters yön: malzeme hâlâ J'de, lot K ile sipariş edilmiş.
    with Katalog() as k:
        malzeme_kur(k)
        k.parti_ekle("YENI", "AST-N", "Ted A", "K", URETIM)
        r = satirlar(k)
    assert (r["ESKI"].raf.son_kullanma, r["ESKI"].dokuman_surumu) == (J_SON, f"{BELGE}J v1")
    assert (r["YENI"].raf.son_kullanma, r["YENI"].dokuman_surumu) == (K_SON, f"{BELGE}K v1")


def test_eski_lot_uyarisi_eski_revizyonun_suresine_gore_verilir():
    # J'ye göre son kullanma 2026-07-15: 2026-07-01'de 14 gün kalır (uyarı). K'ya göre 198 gün kalırdı.
    with Katalog() as k:
        malzeme_kur(k)
        k.malzeme_revizyonu_ata("AST-N", "K")
        s = satirlar(k, date(2026, 7, 1))["ESKI"]
    assert s.raf.durum == "yaklasiyor" and s.raf.kalan_gun == 14 and s.raf.uyari


def test_eski_lot_omur_uzatma_testleri_siparis_revizyonunun_dokumanindan_gelir():
    with Katalog() as k:
        malzeme_kur(k)
        k.malzeme_revizyonu_ata("AST-N", "K")
        s = satirlar(k, date(2026, 7, 1))["ESKI"]
    assert [t.id for t in s.omur_uzatma_testleri] == ["viskozite_j"]


def test_siparis_revizyonunun_en_son_onayli_surumu_kullanilir():
    with Katalog() as k:
        malzeme_kur(k)
        k.dokuman_onayla(dokuman("J", 9), "mp1")  # J v2: 9 ay
        k.malzeme_revizyonu_ata("AST-N", "K")
        s = satirlar(k)["ESKI"]
    assert s.dokuman_surumu == f"{BELGE}J v2"
    assert s.raf.son_kullanma == date(2026, 10, 15)


def test_siparis_revizyonu_buyuk_kucuk_harf_ve_bosluk_farkinda_ayni_revizyon_sayilir():
    # Sipariş revizyonu elle girilir; " j " J revizyonudur, K'ya düşülmez.
    with Katalog() as k:
        malzeme_kur(k)
        k.parti_ekle("KUCUK", "AST-N", "Ted A", " j ", URETIM)
        k.malzeme_revizyonu_ata("AST-N", "K")
        s = satirlar(k)["KUCUK"]
    assert s.raf.son_kullanma == J_SON and s.dokuman_surumu == f"{BELGE}J v1"


# --- sipariş revizyonunun onaylı dokümanı yoksa belirsizlik ---------------------------------------


def test_siparis_revizyonunun_onayli_dokumani_yoksa_sure_hesaplanmaz():
    with Katalog() as k:
        malzeme_kur(k, j_onayli=False)
        k.malzeme_revizyonu_ata("AST-N", "K")
        s = satirlar(k)["ESKI"]
    assert s.raf.durum == "bilinmiyor"
    assert s.raf.son_kullanma is None and s.raf.kalan_gun is None
    assert s.dokuman_surumu is None  # K dokümanı gösterilmez


def test_siparis_revizyonunun_onayli_dokumani_yoksa_not_revizyonu_anar():
    with Katalog() as k:
        malzeme_kur(k, j_onayli=False)
        k.malzeme_revizyonu_ata("AST-N", "K")
        s = satirlar(k)["ESKI"]
    assert len(s.raf.notlar) >= 1
    not_ = " ".join(s.raf.notlar)
    assert "sipariş revizyonu J" in not_ and "onaylı" in not_


def test_siparis_revizyonunun_onayli_dokumani_yoksa_yeni_revizyonun_uzatma_testleri_listelenmez():
    with Katalog() as k:
        malzeme_kur(k, j_onayli=False)
        k.malzeme_revizyonu_ata("AST-N", "K")
        s = satirlar(k, date(2027, 1, 10))["ESKI"]
    assert s.omur_uzatma_testleri == []


def test_malzeme_revizyonunda_dokuman_varken_siparis_revizyonunda_yoksa_belirsizlik():
    # Malzeme J'de ve J onaylı; lot K ile sipariş edilmiş ama K hiç onaylanmamış.
    with Katalog() as k:
        k.dokuman_onayla(dokuman("J", 6), "mp1")
        k.standart_ekle(BELGE, "K")
        k.malzeme_ekle("AST-N", BELGE, "J", tip="I", sinif="N")
        k.tedarikci_onayla("AST-N", "Ted A")
        k.parti_ekle("YENI", "AST-N", "Ted A", "K", URETIM)
        s = satirlar(k)["YENI"]
    assert s.raf.durum == "bilinmiyor" and s.raf.son_kullanma is None and s.dokuman_surumu is None
    assert "sipariş revizyonu K" in " ".join(s.raf.notlar)


def test_siparis_revizyonunun_demo_isareti_kendi_dokumanindan_gelir():
    with Katalog() as k:
        k.dokuman_onayla(dokuman("J", 6), "ornek-veri", demo_onayi=True)
        k.dokuman_onayla(dokuman("K", 12), "mp1")
        k.malzeme_ekle("AST-N", BELGE, "J", tip="I", sinif="N")
        k.tedarikci_onayla("AST-N", "Ted A")
        k.parti_ekle("ESKI", "AST-N", "Ted A", "J", URETIM)
        k.malzeme_revizyonu_ata("AST-N", "K")
        k.parti_ekle("YENI", "AST-N", "Ted A", "K", URETIM)
        r = satirlar(k)
    assert r["ESKI"].demo_onayi is True and r["ESKI"].dokuman_surumu == f"{BELGE}J v1"
    assert r["YENI"].demo_onayi is False


# --- kurcalanmış sürüm: ilgili revizyon okunamazsa belirsizlik, başka revizyona düşülmez -------------


def ozeti_boz(k: Katalog, revizyon: str, surum: int = 1) -> None:
    """Değiştirilemezlik tetikleyicisini geçici kaldırıp sürümün özetini bozar, sonra geri kurar."""
    b = k.baglanti
    (tanim,) = b.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'dokuman_surumu_degistirilemez'"
    ).fetchone()
    b.execute("DROP TRIGGER dokuman_surumu_degistirilemez")
    b.execute("UPDATE dokuman_surumleri SET ozet = ? WHERE belge_no = ? AND revizyon = ? AND surum = ?",
              ("0" * 64, BELGE, revizyon, surum))
    b.execute(tanim)
    b.commit()


def test_siparis_revizyonunun_surumu_kurcalanmissa_belirsizlik_ve_yeni_revizyona_dusulmez():
    with Katalog() as k:
        malzeme_kur(k)
        k.malzeme_revizyonu_ata("AST-N", "K")
        ozeti_boz(k, "J")
        s = satirlar(k)["ESKI"]
    assert s.raf.durum == "bilinmiyor"
    assert s.raf.son_kullanma is None and s.raf.kalan_gun is None
    assert s.dokuman_surumu is None
    assert s.omur_uzatma_testleri == []


def test_yalniz_yeni_revizyon_kurcalanmissa_eski_lot_kendi_suresini_korur():
    with Katalog() as k:
        malzeme_kur(k)
        k.malzeme_revizyonu_ata("AST-N", "K")
        ozeti_boz(k, "K")
        s = satirlar(k)["ESKI"]
    assert s.raf.son_kullanma == J_SON
    assert s.dokuman_surumu == f"{BELGE}J v1"


# --- revizyon geçişi akışı (yeni revizyon yükle → M&P yeni revizyona geç) -------------------------


@pytest.mark.parametrize("j_onayli, beklenen_son", [(True, J_SON), (False, None)])
def test_mp_incelemesi_yeni_revizyona_gecince_eski_lot_suresi_degismez(j_onayli, beklenen_son):
    with Katalog() as k:
        if j_onayli:
            k.dokuman_onayla(dokuman("J", 6), "mp1")
        else:
            k.standart_ekle(BELGE, "J")
        k.malzeme_ekle("AST-N", BELGE, "J", tip="I", sinif="N")
        k.tedarikci_onayla("AST-N", "Ted A")
        k.parti_ekle("ESKI", "AST-N", "Ted A", "J", URETIM)
        yeni_revizyon_yukle(k, BELGE, "K", "mp1")
        k.dokuman_onayla(dokuman("K", 12), "mp1")
        mp_incelemesini_kapat(k, DenetimKaydi(k.baglanti), "AST-N", "mp1", "yeni_revizyona_gec", yeni_revizyon="K")
        assert k.malzeme("AST-N").revizyon == "K"
        s = satirlar(k)["ESKI"]
    assert s.raf.son_kullanma == beklenen_son
    assert s.raf.son_kullanma != K_SON


# --- depo ekranı aynı kaynaktan gelir ---------------------------------------------------------------


def test_depo_tablosu_eski_lot_icin_siparis_revizyonunun_suresini_gosterir():
    with Katalog() as k:
        malzeme_kur(k)
        k.malzeme_revizyonu_ata("AST-N", "K")
        k.parti_ekle("YENI", "AST-N", "Ted A", "K", URETIM)
        tablo = {s["lot"]: s for s in ev.depo_tablosu(k, date(2026, 3, 1))}
    assert tablo["ESKI"]["son kullanma"] == J_SON.isoformat()
    assert tablo["ESKI"]["kabul dokümanı"].startswith(f"{BELGE}J v1")
    assert tablo["YENI"]["son kullanma"] == K_SON.isoformat()
    assert tablo["YENI"]["kabul dokümanı"].startswith(f"{BELGE}K v1")


def test_depo_tablosu_siparis_revizyonunun_dokumani_yoksa_bos_sure_ve_not_gosterir():
    with Katalog() as k:
        malzeme_kur(k, j_onayli=False)
        k.malzeme_revizyonu_ata("AST-N", "K")
        (satir,) = ev.depo_tablosu(k, date(2026, 3, 1))
    assert satir["son kullanma"] == "" and satir["kalan gün"] is None
    assert satir["raf"] == ev.RAF_ETIKETI["bilinmiyor"]
    assert satir["kabul dokümanı"] == ""
    assert "sipariş revizyonu J" in satir["not"]
