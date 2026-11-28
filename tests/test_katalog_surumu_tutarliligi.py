"""Katalog sürümü tutarlılığı: okuma karşılaştırması ile parti kararı aynı dayanağı kullanır (Codex incelemesi).

Bulgu: `sertifika_hatti` kabul dokümanını okuyup kural/model okuma
karşılaştırmasına veriyordu; `malzeme_koduyla_kontrol` ise dokümanı ve
malzemeyi (tip/sınıf) model çağrısından sonra, parti durumunu yazan işlemin
dışında yeniden okuyordu. Model çağrısı sürerken M&P başka bağlantıdan yeni
bir sürüm onaylayıp yeni bir kabul testi eklerse o testteki kural/model okuma
farkı karşılaştırmaya girmiyor, parti serbest kalabiliyordu.

Tarif edilen tasarım:

- `malzeme_koduyla_kontrol(..., surum=DokumanSurumu, malzeme_kaydi=Malzeme)`:
  verilirse karar bu sürüm ve bu malzemenin tip/sınıfıyla verilir; verilmezse
  fonksiyon kendisi okur (eski davranış).
- Parti durumunu yazan `katalog.islem()` içinde geçerli sürüm (etiket, özet) ve
  malzeme (belge_no, revizyon, tip, sınıf) yeniden okunur; kararın dayandığıyla
  farklıysa `dokuman_dayanagi` ("Karar dayanağı") ek denetimi insan incelemeli
  olur, gerekçesinde kullanılan ve şimdiki sürüm etiketi yazar. Aynıysa satır
  eklenmez.
- `KatalogKarari.dokuman_surumu` ve denetim kaydının `dokuman_surumu` alanı
  kararın gerçekten dayandığı sürümdür.
- `sertifika_hatti` sürümü ve malzemeyi bir kez okur ve ikisini de hem okuma
  karşılaştırmasına hem karara verir.

Dil modeli yoktur: sahte istemci model yanıtı gibi JSON döner, ağ kullanmaz.
Katalog ve PDF `tmp_path` altındadır; data/ altına yazılmaz.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from malzeme_kabul.belge.pdf_okuyucu import pdf_oku
from malzeme_kabul.cikarim.sertifika_okuyucu import kural_ile_oku
from malzeme_kabul.hat.hibrit_hat import sertifika_hatti
from malzeme_kabul.hat.katalog_karari import _dayanak_denetimi, dokuman_onayla, malzeme_koduyla_kontrol
from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.sozlesme.sema import KabulDokumani, StandartBilgisi
from tests.test_hibrit_guvenligi import model_yaniti, pdf_yaz
from tests.test_katalog_karari import _test, sertifika

TEDARIKCI = "Kurgu Coatings Inc. (kurgusal)"
LOT = "T900"
V1, V2 = "MIL-PRF-23377K v1", "MIL-PRF-23377K v2"


def dokuman(krom: bool, revizyon: str = "K", krom_ust: float = 0.1) -> KabulDokumani:
    """v1: yalnız VOC; v2: VOC + yeni kabul testi krom (en çok `krom_ust` percent)."""
    testler = [_test("voc", "VOC content", 340.0)]
    if krom:
        testler.append(_test("krom", "Chromium content", krom_ust, birim="percent"))
    return KabulDokumani(standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon=revizyon), testler=testler)


def dayanak_satirlari(karar) -> list:
    return [s for s in karar.ek_denetimler if s.test_id == "dokuman_dayanagi"]


# --- asıl senaryo: model çağrısı sırasında başka bağlantıdan yeni sürüm onayı -----------------


@pytest.fixture
def dosya_katalogu(tmp_path):
    """Dosya tabanlı katalog: v1 onaylı (yalnız VOC), AST-N Type I Class N, onaylı tedarikçi, bekleyen parti."""
    yol = tmp_path / "katalog.db"
    k = Katalog(yol)
    defter = DenetimKaydi(k.baglanti)
    dokuman_onayla(k, defter, dokuman(krom=False), "mp1")
    k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
    k.tedarikci_onayla("AST-N", TEDARIKCI)
    k.parti_ekle(LOT, "AST-N", TEDARIKCI, "K", "2026-06-01")
    yield k, defter, yol
    k.kapat()


def sertifika_pdf(tmp_path: Path) -> Path:
    """VOC 300 g/L (uygun) ve Chromium content 0.5 percent (en çok 0.1: uygun değil).

    Metot hücresinde "Ref 0.05" vardır: model sonucu oradan "0.05" okur. Bu
    okuma kanıt doğrulayıcıdan geçer (aynı satırda, şart sözcüğü yok); kural
    okuyucu sonuç sütunundan 0.5 okur. Fark yalnız krom testi karşılaştırmaya
    girerse yakalanır.
    """
    return pdf_yaz(tmp_path / "sertifika.pdf", TEDARIKCI, [
        ["VOC content", "ASTM D3960", "340 max", "300", "g/L"],
        ["Chromium content", "Ref 0.05", "0.1 max", "0.5", "percent"],
    ], lot=LOT)


def krom_yanlis_okuyan_yanit(pdf: Path) -> dict:
    yanit = model_yaniti(kural_ile_oku(pdf_oku(pdf)))
    for s in yanit["satirlar"]:
        if s["test_adi"] == "Chromium content":
            s["sonuc_hucresi"] = "0.05"  # sonuç sütununda 0.5 var
    return yanit


class SurumOnaylayanModel:
    """Sahte yerel model: yanıt vermeden önce İKİNCİ bir sqlite bağlantısıyla yeni sürüm onaylatır (M&P).

    Ağ kullanmaz. `onayla=False` ise yalnız yanıtı döner.
    """

    model = "sahte-model"

    def __init__(self, yanit: dict, katalog_yolu: Path, onayla: bool = True):
        self.yanit, self.katalog_yolu, self.onayla = yanit, katalog_yolu, onayla
        self.onaylanan: str | None = None

    def sohbet(self, mesajlar, sema):
        if self.onayla and self.onaylanan is None:
            with Katalog(self.katalog_yolu) as ikinci:
                surum = dokuman_onayla(ikinci, DenetimKaydi(ikinci.baglanti), dokuman(krom=True), "mp2",
                                       "krom kabul testi eklendi")
                self.onaylanan = surum.etiket
        return json.dumps(self.yanit)


def test_senaryo_kendi_icinde_gecerli_v2_bastan_gecerliyse_krom_okuma_farki_yakalanir(dosya_katalogu, tmp_path):
    """Kontrol: yarış yokken (v2 baştan geçerli) krom okuma farkı karşılaştırmada yakalanır, parti serbest olmaz.

    Bu test bugün de geçer; aşağıdaki yarış testindeki farkın gerçekten
    yakalanabilir bir fark olduğunu gösterir.
    """
    k, defter, _ = dosya_katalogu
    dokuman_onayla(k, defter, dokuman(krom=True), "mp2")
    pdf = sertifika_pdf(tmp_path)
    model = SurumOnaylayanModel(krom_yanlis_okuyan_yanit(pdf), dosya_katalogu[2], onayla=False)
    karar, okuma = sertifika_hatti(k, "AST-N", pdf, mod="hibrit", istemci=model, lot_no=LOT,
                                   defter=defter, kullanici="gk1")
    assert okuma.kanitsiz == []
    assert any(a.test_id == "krom" for a in okuma.anlasmazliklar), okuma.anlasmazliklar
    assert karar.parti_karari != "kabul"
    assert k.parti("AST-N", LOT).durum != "serbest"


def test_model_cagrisi_sirasinda_yeni_surum_onaylanirsa_parti_serbest_kalmaz(dosya_katalogu, tmp_path):
    k, defter, yol = dosya_katalogu
    pdf = sertifika_pdf(tmp_path)
    model = SurumOnaylayanModel(krom_yanlis_okuyan_yanit(pdf), yol)

    karar, _ = sertifika_hatti(k, "AST-N", pdf, mod="hibrit", istemci=model, lot_no=LOT,
                               defter=defter, kullanici="gk1")

    assert model.onaylanan == V2  # yarış gerçekten oldu: karar verilirken katalogda v2 geçerli
    assert karar.parti_karari != "kabul"
    assert karar.parti_durumu != "serbest"
    assert k.parti("AST-N", LOT).durum != "serbest"
    (dayanak,) = dayanak_satirlari(karar)
    assert dayanak.karar == "insan_incelemeli" and dayanak.test_adi == "Karar dayanağı"
    assert V1 in dayanak.gerekce and V2 in dayanak.gerekce, dayanak.gerekce


def test_model_cagrisi_sirasinda_yeni_surum_onaylanirsa_karar_okumanin_dayandigi_surumu_tasir(
    dosya_katalogu, tmp_path
):
    k, defter, yol = dosya_katalogu
    pdf = sertifika_pdf(tmp_path)
    karar, _ = sertifika_hatti(k, "AST-N", pdf, mod="hibrit", istemci=SurumOnaylayanModel(krom_yanlis_okuyan_yanit(pdf), yol),
                               lot_no=LOT, defter=defter, kullanici="gk1")
    assert karar.dokuman_surumu == V1
    assert karar.dokuman_ozeti == k.dokuman_surumu("MIL-PRF-23377", "K", 1).ozet
    # Karşılaştırma v1 ile yapıldı; karar da v1 ile verilir (v1'de krom testi yok).
    assert "krom" not in [s.test_id for s in karar.kontrol.satirlar]
    (kayit,) = defter.kayitlar("karar")
    assert kayit.dokuman_surumu == V1


def test_yaris_yoksa_hibrit_hatta_dayanak_satiri_eklenmez(dosya_katalogu, tmp_path):
    k, defter, yol = dosya_katalogu
    pdf = sertifika_pdf(tmp_path)
    model = SurumOnaylayanModel(krom_yanlis_okuyan_yanit(pdf), yol, onayla=False)
    karar, _ = sertifika_hatti(k, "AST-N", pdf, mod="hibrit", istemci=model, lot_no=LOT,
                               defter=defter, kullanici="gk1")
    assert dayanak_satirlari(karar) == []
    assert karar.dokuman_surumu == V1


# --- malzeme_koduyla_kontrol: verilen sürüm ve malzeme ---------------------------------------


@pytest.fixture
def katalog():
    """Bellekte katalog: v1 (yalnız VOC) onaylı, AST-N Type I Class N, tedarikçi 'Ted A', parti L1 bekliyor."""
    k = Katalog()
    k.dokuman_onayla(dokuman(krom=False), "mp1")
    k.malzeme_ekle("AST-N", "MIL-PRF-23377", "K", tip="I", sinif="N")
    k.tedarikci_onayla("AST-N", "Ted A")
    k.parti_ekle("L1", "AST-N", "Ted A", "K", "2026-06-01")
    yield k
    k.kapat()


def denetimli(k: Katalog) -> dict:
    return {"defter": DenetimKaydi(k.baglanti), "kullanici": "gk1"}


def test_verilen_surumle_karar_verilir_katalogdaki_yeni_surumle_degil(katalog):
    v1 = katalog.gecerli_dokuman("AST-N")
    katalog.dokuman_onayla(dokuman(krom=True, krom_ust=0.01), "mp2")  # v2: krom 0.05 bu sınırı aşar
    sonuc = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(), surum=v1)
    assert [s.test_id for s in sonuc.kontrol.satirlar] == ["voc"]
    assert sonuc.dokuman_surumu == V1 and sonuc.dokuman_ozeti == v1.ozet


def test_eski_surum_verilip_katalogda_yeni_surum_gecerliyse_dayanak_insan_incelemeli(katalog):
    v1 = katalog.gecerli_dokuman("AST-N")
    katalog.dokuman_onayla(dokuman(krom=True), "mp2")
    sonuc = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(), surum=v1)
    (dayanak,) = dayanak_satirlari(sonuc)
    assert dayanak.karar == "insan_incelemeli" and dayanak.test_adi == "Karar dayanağı"
    assert V1 in dayanak.gerekce and V2 in dayanak.gerekce, dayanak.gerekce
    assert sonuc.parti_karari != "kabul"


def test_eski_surumle_lotlu_karar_partiyi_serbest_birakmaz_ve_kayit_eski_surumu_tasir(katalog):
    v1 = katalog.gecerli_dokuman("AST-N")
    katalog.dokuman_onayla(dokuman(krom=True), "mp2")
    d = denetimli(katalog)
    sonuc = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(), lot_no="L1", surum=v1, **d)
    assert sonuc.parti_karari == "inceleme" and sonuc.parti_durumu == "bekliyor"
    assert katalog.parti("AST-N", "L1").durum == "bekliyor"
    assert sonuc.dokuman_surumu == V1
    (kayit,) = d["defter"].kayitlar("karar")
    assert kayit.dokuman_surumu == V1


def test_eski_surumle_red_karari_karantinaya_alir(katalog):
    """Dayanak farkı kararı yalnız kısıtlar: red varsa parti karantinaya gider (serbest bırakılmaz)."""
    v1 = katalog.gecerli_dokuman("AST-N")
    katalog.dokuman_onayla(dokuman(krom=True), "mp2")
    sonuc = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(voc="400"), lot_no="L1", surum=v1,
                                    **denetimli(katalog))
    assert [s.karar for s in dayanak_satirlari(sonuc)] == ["insan_incelemeli"]
    assert sonuc.parti_karari == "red" and katalog.parti("AST-N", "L1").durum == "karantina"


def test_verilen_surum_gecerli_surumse_dayanak_satiri_yok_ve_karar_eski_davranisla_ayni(katalog):
    eski = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika())
    yeni = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(),
                                   surum=katalog.gecerli_dokuman("AST-N"), malzeme_kaydi=katalog.malzeme("AST-N"))
    assert dayanak_satirlari(yeni) == []
    assert yeni.model_dump() == eski.model_dump()
    assert yeni.parti_karari == "kabul"


def test_surum_ayniyken_lotlu_kararda_dayanak_satiri_yok_parti_serbest(katalog):
    s = sertifika().model_copy(update={"parti_no": "L1"})  # K3: sertifika bu partiye ait (lot ve tedarikçi tutuyor)
    sonuc = malzeme_koduyla_kontrol(katalog, "AST-N", s, lot_no="L1",
                                    surum=katalog.gecerli_dokuman("AST-N"), malzeme_kaydi=katalog.malzeme("AST-N"),
                                    **denetimli(katalog))
    assert dayanak_satirlari(sonuc) == []
    assert sonuc.parti_karari == "kabul" and katalog.parti("AST-N", "L1").durum == "serbest"


def test_verilen_malzemenin_tip_sinifiyla_karar_verilir(katalog):
    """Class N'ye özgü krom testi, verilen malzeme kaydı Class C2 ise uygulanmaz (katalogdaki N değil)."""
    katalog.dokuman_onayla(
        KabulDokumani(standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"), testler=[
            _test("voc", "VOC content", 340.0), _test("krom", "Chromium content", 0.1, ["Class N"], birim="percent"),
        ]), "mp2",
    )
    surum = katalog.gecerli_dokuman("AST-N")
    c2 = dataclasses.replace(katalog.malzeme("AST-N"), sinif="C2")
    sonuc = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(atif="MIL-PRF-23377K", krom=None),
                                    surum=surum, malzeme_kaydi=c2)
    assert [s.test_id for s in sonuc.kontrol.satirlar] == ["voc"]


def test_verilen_malzeme_sinifi_katalogdakinden_farkliysa_dayanak_insan_incelemeli(katalog):
    surum = katalog.gecerli_dokuman("AST-N")
    c2 = dataclasses.replace(katalog.malzeme("AST-N"), sinif="C2")
    sonuc = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(atif="MIL-PRF-23377K"), lot_no="L1",
                                    surum=surum, malzeme_kaydi=c2, **denetimli(katalog))
    assert [s.karar for s in dayanak_satirlari(sonuc)] == ["insan_incelemeli"]
    assert sonuc.parti_karari != "kabul" and katalog.parti("AST-N", "L1").durum != "serbest"


def test_malzeme_revizyon_gecisi_karardan_once_olduysa_dayanak_insan_incelemeli(katalog):
    """Gerçek katalog yolu: M&P malzemeyi K'dan L'ye geçirir (`malzeme_revizyonu_ata`)."""
    surum, malzeme = katalog.gecerli_dokuman("AST-N"), katalog.malzeme("AST-N")
    katalog.dokuman_onayla(dokuman(krom=False, revizyon="L"), "mp2")
    katalog.malzeme_revizyonu_ata("AST-N", "L")
    sonuc = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(), lot_no="L1",
                                    surum=surum, malzeme_kaydi=malzeme, **denetimli(katalog))
    (dayanak,) = dayanak_satirlari(sonuc)
    assert dayanak.karar == "insan_incelemeli"
    assert V1 in dayanak.gerekce and "MIL-PRF-23377L v1" in dayanak.gerekce, dayanak.gerekce
    assert sonuc.parti_karari != "kabul" and katalog.parti("AST-N", "L1").durum != "serbest"
    assert sonuc.dokuman_surumu == V1


def test_parametresiz_cagri_eski_davranis_dayanak_satiri_eklemez(katalog):
    katalog.dokuman_onayla(dokuman(krom=True), "mp2")
    sonuc = malzeme_koduyla_kontrol(katalog, "AST-N", sertifika(), lot_no="L1", **denetimli(katalog))
    assert dayanak_satirlari(sonuc) == []
    assert sonuc.dokuman_surumu == V2


# --- _dayanak_denetimi: doğrudan birim testleri -----------------------------------------------


def test_dayanak_denetimi_surum_ve_malzeme_ayniysa_satir_dondurmez(katalog):
    assert _dayanak_denetimi(katalog, "AST-N", katalog.gecerli_dokuman("AST-N"), katalog.malzeme("AST-N")) is None


def test_dayanak_denetimi_eski_surumle_insan_incelemeli_ve_iki_etiketi_yazar(katalog):
    v1 = katalog.gecerli_dokuman("AST-N")
    katalog.dokuman_onayla(dokuman(krom=True), "mp2")
    satir = _dayanak_denetimi(katalog, "AST-N", v1, katalog.malzeme("AST-N"))
    assert satir is not None
    assert (satir.test_id, satir.test_adi, satir.karar) == ("dokuman_dayanagi", "Karar dayanağı", "insan_incelemeli")
    assert V1 in satir.gerekce and V2 in satir.gerekce, satir.gerekce


def test_dayanak_denetimi_etiket_ayni_ozet_farkliysa_insan_incelemeli(katalog):
    kurcalanmis = dataclasses.replace(katalog.gecerli_dokuman("AST-N"), ozet="0" * 64)
    satir = _dayanak_denetimi(katalog, "AST-N", kurcalanmis, katalog.malzeme("AST-N"))
    assert satir is not None and satir.karar == "insan_incelemeli"


@pytest.mark.parametrize("alan, deger", [("tip", "II"), ("sinif", "C2"), ("tip", None), ("sinif", None)])
def test_dayanak_denetimi_tip_sinif_farkinda_insan_incelemeli(katalog, alan, deger):
    farkli = dataclasses.replace(katalog.malzeme("AST-N"), **{alan: deger})
    satir = _dayanak_denetimi(katalog, "AST-N", katalog.gecerli_dokuman("AST-N"), farkli)
    assert satir is not None and satir.karar == "insan_incelemeli"
    assert "tip/sınıf" in satir.gerekce, satir.gerekce


@pytest.mark.parametrize("alan, deger", [("revizyon", "L"), ("belge_no", "MIL-PRF-85285")])
def test_dayanak_denetimi_malzeme_standart_farkinda_insan_incelemeli(katalog, alan, deger):
    farkli = dataclasses.replace(katalog.malzeme("AST-N"), **{alan: deger})
    satir = _dayanak_denetimi(katalog, "AST-N", katalog.gecerli_dokuman("AST-N"), farkli)
    assert satir is not None and satir.karar == "insan_incelemeli"


def test_dayanak_denetimi_yalniz_aciklama_farki_dayanak_sayilmaz(katalog):
    """Karara girmeyen alan (açıklama) farkı dayanak farkı değildir; gereksiz insan incelemesi doğmaz."""
    farkli = dataclasses.replace(katalog.malzeme("AST-N"), aciklama="başka açıklama")
    assert _dayanak_denetimi(katalog, "AST-N", katalog.gecerli_dokuman("AST-N"), farkli) is None
