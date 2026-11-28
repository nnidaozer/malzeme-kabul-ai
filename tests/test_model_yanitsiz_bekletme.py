"""Hibritte dil modeli yanıt vermezse parti bekletilir (onaylı karar, proje sahibi).

Karar: "Dil modeli yanıt vermemişse parti 'bekliyor' olsun. Eksik bilgi hiçbir
zaman 'uygun' sonucuna yol açmamalı; bazı partilerin insana kalması kabul."

Hibritte model hata verir ya da şemaya uymayan yanıt dönerse hat kural
okumasına düşer (`SertifikaOkumasi.yedek`). Kural okuması yine okunur ve kayda
girer, ama karar onunla verilmez:

- `kanit` ek denetimi insan incelemeli olur ("dil modeli yanıt vermedi" + yedek nedeni);
- kontrol satırlarından (revizyon, satirlar, tip_sinif) uygun ya da uygun değil
  olanlar insan incelemeli olur; gerekçeye "yalnız kural okumasıyla karar
  verilmez" ve kuralın kendi kararı ("kural okumasına göre: ...") eklenir;
- parti kararı "inceleme", parti durumu "bekliyor" (karantinadaki parti karantinada kalır).

Arayüz: `malzeme_koduyla_kontrol(..., bekletme_nedeni=...)`; `sertifika_hatti`
yedekte bu parametreyi doldurur.

Örnek sertifikalar (AST-001: Type I Class N), kural modunda:
- S-028 → kabul (Kurgu Coatings, parti A94009);
- S-089 → red (yalnız drying_time uygun değil; Ornek Aerospace Finishes).
Testlerde gerçek dil modeli yoktur; `SahteModel` ağ kullanmaz.
"""

from __future__ import annotations

import json

import pytest

from malzeme_kabul.hat.hibrit_hat import sertifika_hatti
from malzeme_kabul.hat.katalog_karari import malzeme_koduyla_kontrol
from malzeme_kabul.katalog.ornek_veri import ornek_yukle
from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from tests.conftest import KOK
from tests.test_hibrit_hat import SET, SahteModel, sertifika_json

KABUL_PDF = SET / "pdf/S-028.pdf"  # kural okumasıyla kabul
RED_PDF = SET / "pdf/S-089.pdf"  # kural okumasıyla red (drying_time sınır dışı)
S028_LOT, S028_TEDARIKCI = "A94009", "Kurgu Coatings Inc. (kurgusal)"
S089_TEDARIKCI = "Ornek Aerospace Finishes Ltd. (kurgusal)"
YANIT_VERMEDI = "dil modeli yanıt vermedi"
KURALLA_KARAR_YOK = "yalnız kural okumasıyla karar verilmez"
KURALA_GORE = "kural okumasına göre"


@pytest.fixture
def katalog():
    k = Katalog()
    ornek_yukle(k, KOK / "data/ornek/katalog.json", KOK)
    k.tedarikci_onayla("AST-001", S028_TEDARIKCI)
    k.tedarikci_onayla("AST-001", S089_TEDARIKCI)
    yield k
    k.kapat()


def yanitsiz_modeller(no: str) -> list[SahteModel]:
    """Yedeğe düşüren üç durum: bağlantı hatası, JSON olmayan yanıt, şemaya uymayan yanıt."""
    s = sertifika_json(no)
    return [
        SahteModel(s, hata=ConnectionRefusedError("bağlantı reddedildi")),
        SahteModel(s, ham="bu json değil"),
        SahteModel(s, ham=json.dumps({"satirlar": [{"sayfa": 1, "test_adi": "x", "sonuc_hucresi": "1",
                                                    "karar": "uygun"}]})),
    ]


YANITSIZ_IDS = ["baglanti_hatasi", "json_degil", "semaya_uymuyor"]


class TamSahteModel(SahteModel):
    """SahteModel'e üretim tarihini de ekler; böylece başarılı hibritte okuma anlaşmazlığı çıkmaz."""

    def sohbet(self, mesajlar, sema):
        yanit = json.loads(super().sohbet(mesajlar, sema))
        yanit["uretim_tarihi"] = self.sertifika.uretim_tarihi
        return json.dumps(yanit)


def kanit_satiri(karar):
    satirlar = [s for s in karar.ek_denetimler if s.test_id == "kanit"]
    assert len(satirlar) == 1, [s.test_id for s in karar.ek_denetimler]
    return satirlar[0]


def kontrol_satirlari(karar):
    k = karar.kontrol
    return [k.revizyon, *k.satirlar, *([k.tip_sinif] if k.tip_sinif is not None else [])]


# --- 1. kanıt denetimi ----------------------------------------------------------------------


@pytest.mark.parametrize("i", range(3), ids=YANITSIZ_IDS)
def test_model_yanit_vermezse_kanit_denetimi_insan_incelemeli_olur(katalog, i):
    model = yanitsiz_modeller("S-028")[i]
    karar, okuma = sertifika_hatti(katalog, "AST-001", KABUL_PDF, mod="hibrit", istemci=model)
    assert okuma.yedek  # ön koşul: yedeğe düşüldü
    kanit = kanit_satiri(karar)
    assert kanit.karar == "insan_incelemeli", kanit.gerekce


def test_model_yanit_vermezse_kanit_gerekcesi_neden_ve_yedek_nedenini_soyler(katalog):
    model = SahteModel(sertifika_json("S-028"), hata=ConnectionRefusedError("bağlantı reddedildi"))
    karar, okuma = sertifika_hatti(katalog, "AST-001", KABUL_PDF, mod="hibrit", istemci=model)
    kanit = kanit_satiri(karar)
    assert YANIT_VERMEDI in kanit.gerekce
    assert okuma.yedek in kanit.gerekce
    assert "ConnectionRefusedError" in kanit.gerekce


# --- 2. kural okuması kayda girer ama karar onunla verilmez -----------------------------------


def test_yedekte_kural_okumasi_yine_okunur_ve_kayda_girer(katalog):
    model = SahteModel(sertifika_json("S-028"), hata=ConnectionRefusedError("bağlantı reddedildi"))
    karar, okuma = sertifika_hatti(katalog, "AST-001", KABUL_PDF, mod="hibrit", istemci=model)
    assert okuma.sertifika.satirlar == sertifika_json("S-028").satirlar
    assert karar.hat["yedek"] == okuma.yedek
    assert karar.kontrol.satirlar  # kural okumasının satırları kontrol edildi


@pytest.mark.parametrize("i", range(3), ids=YANITSIZ_IDS)
def test_yedekte_kural_okumasinin_kabul_verecegi_sertifikada_hicbir_kontrol_satiri_uygun_kalmaz(katalog, i):
    karar, _ = sertifika_hatti(katalog, "AST-001", KABUL_PDF, mod="hibrit", istemci=yanitsiz_modeller("S-028")[i])
    kalan = [(s.test_id, s.karar) for s in kontrol_satirlari(karar) if s.karar != "insan_incelemeli"]
    assert kalan == []


def test_yedekte_kural_okumasinin_red_verecegi_sertifikada_uygun_degil_satiri_insana_gider(katalog):
    model = SahteModel(sertifika_json("S-089"), hata=ConnectionRefusedError("bağlantı reddedildi"))
    karar, _ = sertifika_hatti(katalog, "AST-001", RED_PDF, mod="hibrit", istemci=model)
    kurutma = next(s for s in karar.kontrol.satirlar if s.test_id == "drying_time")
    assert kurutma.karar == "insan_incelemeli"
    assert f"{KURALA_GORE}: uygun_degil" in kurutma.gerekce
    assert all(s.karar == "insan_incelemeli" for s in kontrol_satirlari(karar))


def test_yedekte_satir_gerekcesi_korunur_ve_kuralin_karari_eklenir(katalog):
    kural, _ = sertifika_hatti(katalog, "AST-001", KABUL_PDF, mod="kural")
    model = SahteModel(sertifika_json("S-028"), hata=ConnectionRefusedError("bağlantı reddedildi"))
    karar, _ = sertifika_hatti(katalog, "AST-001", KABUL_PDF, mod="hibrit", istemci=model)
    eski = {s.test_id: s for s in kontrol_satirlari(kural)}
    for s in kontrol_satirlari(karar):
        assert s.gerekce.startswith(eski[s.test_id].gerekce), s.test_id  # gerekçe korunur
        assert KURALLA_KARAR_YOK in s.gerekce, s.test_id
        assert f"{KURALA_GORE}: {eski[s.test_id].karar}" in s.gerekce, s.test_id


def test_yedekte_belge_karari_inceleme_olarak_yeniden_hesaplanir(katalog):
    for pdf, no in ((KABUL_PDF, "S-028"), (RED_PDF, "S-089")):
        model = SahteModel(sertifika_json(no), hata=ConnectionRefusedError("bağlantı reddedildi"))
        karar, _ = sertifika_hatti(katalog, "AST-001", pdf, mod="hibrit", istemci=model)
        assert karar.kontrol.belge_karari == "inceleme", no


# --- 3. parti kararı ve durumu ---------------------------------------------------------------------


def test_kural_okumasinin_red_verecegi_sertifika_kural_modunda_reddedilir(katalog):
    """Ön koşul: S-089 sınır dışıdır; kural modunda red verir."""
    karar, _ = sertifika_hatti(katalog, "AST-001", RED_PDF, mod="kural")
    assert karar.parti_karari == "red"
    assert [s.test_id for s in karar.kontrol.satirlar if s.karar == "uygun_degil"] == ["drying_time"]


@pytest.mark.parametrize("pdf, no", [(KABUL_PDF, "S-028"), (RED_PDF, "S-089")], ids=["kabul_olurdu", "red_olurdu"])
@pytest.mark.parametrize("i", range(3), ids=YANITSIZ_IDS)
def test_model_yanit_vermezse_parti_inceleme_ve_bekliyor_olur(katalog, pdf, no, i):
    karar, _ = sertifika_hatti(katalog, "AST-001", pdf, mod="hibrit", istemci=yanitsiz_modeller(no)[i])
    assert (karar.parti_karari, karar.parti_durumu) == ("inceleme", "bekliyor")


def test_model_yanit_vermezse_yeni_parti_serbest_birakilmaz_bekliyor_yazilir(katalog):
    katalog.parti_ekle(S028_LOT, "AST-001", S028_TEDARIKCI, "K", "2026-06-01")  # bekliyor, hiç karar yok
    assert not katalog.parti("AST-001", S028_LOT).karar_verildi
    d = DenetimKaydi(katalog.baglanti)
    model = SahteModel(sertifika_json("S-028"), hata=ConnectionRefusedError("bağlantı reddedildi"))
    karar, _ = sertifika_hatti(katalog, "AST-001", KABUL_PDF, mod="hibrit", istemci=model,
                               lot_no=S028_LOT, defter=d, kullanici="gk1")
    assert (karar.parti_karari, karar.parti_durumu) == ("inceleme", "bekliyor")
    assert katalog.parti("AST-001", S028_LOT).durum == "bekliyor"


def test_yeni_parti_kural_modunda_serbest_birakilir(katalog):
    """Karşılaştırma: aynı parti ve sertifika kural modunda serbest olur (ön koşul)."""
    katalog.parti_ekle(S028_LOT, "AST-001", S028_TEDARIKCI, "K", "2026-06-01")
    d = DenetimKaydi(katalog.baglanti)
    karar, _ = sertifika_hatti(katalog, "AST-001", KABUL_PDF, mod="kural", lot_no=S028_LOT, defter=d, kullanici="gk1")
    assert (karar.parti_karari, karar.parti_durumu) == ("kabul", "serbest")


def test_model_yanit_vermezse_karantinadaki_parti_karantinada_kalir(katalog):
    katalog.parti_ekle(S028_LOT, "AST-001", S028_TEDARIKCI, "K", "2026-06-01", durum="karantina")
    d = DenetimKaydi(katalog.baglanti)
    model = SahteModel(sertifika_json("S-028"), hata=ConnectionRefusedError("bağlantı reddedildi"))
    karar, _ = sertifika_hatti(katalog, "AST-001", KABUL_PDF, mod="hibrit", istemci=model,
                               lot_no=S028_LOT, defter=d, kullanici="gk1")
    assert karar.parti_durumu == "karantina"
    assert katalog.parti("AST-001", S028_LOT).durum == "karantina"
    assert karar.parti_karari == "inceleme"
    assert all(s.karar == "insan_incelemeli" for s in kontrol_satirlari(karar))


# --- 4. arayüz: malzeme_koduyla_kontrol(bekletme_nedeni=...) -----------------------------------------


NEDEN = "dil modeli yanıt vermedi (ConnectionRefusedError: bağlantı reddedildi)"


def test_bekletme_nedeni_verilmezse_karar_degismez(katalog):
    s = sertifika_json("S-028")
    once = malzeme_koduyla_kontrol(katalog, "AST-001", s)
    sonra = malzeme_koduyla_kontrol(katalog, "AST-001", s, bekletme_nedeni=None)
    assert sonra.kontrol == once.kontrol and sonra.parti_karari == once.parti_karari == "kabul"


def test_bekletme_nedeni_verilirse_uygun_satirlar_insan_incelemeli_olur(katalog):
    s = sertifika_json("S-028")
    once = malzeme_koduyla_kontrol(katalog, "AST-001", s)
    karar = malzeme_koduyla_kontrol(katalog, "AST-001", s, bekletme_nedeni=NEDEN)
    eski = {x.test_id: x for x in kontrol_satirlari(once)}
    for x in kontrol_satirlari(karar):
        assert x.karar == "insan_incelemeli", x.test_id
        assert x.gerekce.startswith(eski[x.test_id].gerekce), x.test_id
        assert NEDEN in x.gerekce and KURALLA_KARAR_YOK in x.gerekce, x.test_id
        assert f"{KURALA_GORE}: uygun" in x.gerekce, x.test_id
    assert karar.kontrol.belge_karari == "inceleme"
    assert karar.parti_karari == "inceleme" and karar.parti_durumu == "bekliyor"


def test_bekletme_nedeni_verilirse_uygun_degil_satir_insan_incelemeli_olur(katalog):
    karar = malzeme_koduyla_kontrol(katalog, "AST-001", sertifika_json("S-089"), bekletme_nedeni=NEDEN)
    kurutma = next(x for x in karar.kontrol.satirlar if x.test_id == "drying_time")
    assert kurutma.karar == "insan_incelemeli"
    assert NEDEN in kurutma.gerekce and f"{KURALA_GORE}: uygun_degil" in kurutma.gerekce
    assert karar.kontrol.belge_karari == "inceleme"
    assert karar.parti_karari == "inceleme" and karar.parti_durumu == "bekliyor"


def test_bekletme_nedeni_insan_incelemeli_satirin_kararini_degistirmez(katalog):
    """S-001 (Type II Class C2) AST-001 için tip/sınıf ve bazı satırlarda zaten insan incelemeli."""
    s = sertifika_json("S-001")
    once = malzeme_koduyla_kontrol(katalog, "AST-001", s)
    karar = malzeme_koduyla_kontrol(katalog, "AST-001", s, bekletme_nedeni=NEDEN)
    assert karar.kontrol.tip_sinif is not None and karar.kontrol.tip_sinif.karar == "insan_incelemeli"
    zaten = {x.test_id for x in kontrol_satirlari(once) if x.karar == "insan_incelemeli"}
    assert zaten  # ön koşul
    assert all(x.karar == "insan_incelemeli" for x in kontrol_satirlari(karar))


# --- 5. regresyon: kural modu ve başarılı hibrit değişmez ---------------------------------------------


def test_kural_modunda_kabul_verecek_sertifika_hala_kabul(katalog):
    karar, _ = sertifika_hatti(katalog, "AST-001", KABUL_PDF, mod="kural")
    assert karar.parti_karari == "kabul" and karar.parti_durumu == "serbest"
    assert all(s.karar == "uygun" for s in kontrol_satirlari(karar))
    assert all(KURALLA_KARAR_YOK not in s.gerekce for s in kontrol_satirlari(karar))


def test_basarili_hibritte_kanit_uygun_ve_parti_kabul(katalog):
    karar, okuma = sertifika_hatti(katalog, "AST-001", KABUL_PDF, mod="hibrit",
                                   istemci=TamSahteModel(sertifika_json("S-028")))
    assert okuma.yedek is None and okuma.anlasmazliklar == []
    assert kanit_satiri(karar).karar == "uygun"
    assert karar.parti_karari == "kabul"
    assert all(KURALLA_KARAR_YOK not in s.gerekce for s in kontrol_satirlari(karar))


# --- 6. denetim kaydı ----------------------------------------------------------------------------------


def test_yedekte_karar_kaydi_inceleme_tasir_model_ve_istem_surumu_yazilmaz(katalog):
    d = DenetimKaydi(katalog.baglanti)
    model = SahteModel(sertifika_json("S-028"), hata=ConnectionRefusedError("bağlantı reddedildi"))
    _, okuma = sertifika_hatti(katalog, "AST-001", KABUL_PDF, mod="hibrit", istemci=model, defter=d, kullanici="gk1")
    k = d.kayitlar("karar")[-1]
    assert k.model is None and k.istem_surumu is None
    assert k.veri["parti_karari"] == "inceleme"
    assert k.veri["hat"]["yedek"] == okuma.yedek
    assert d.zinciri_dogrula().gecerli
