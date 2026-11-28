"""Kural ve dil modeli okuması arasındaki anlaşmazlık (onaylı iş, proje sahibinin kuralı).

Hibrit hatta kural okuyucu ile dil modeli aynı test için farklı değer, birim,
sınır ya da yön bulursa kuralınki sessizce alınmaz: o şart "insan_incelemeli"
olur ve anlaşmazlık kaydı tutulur (ileride güven skoru girdisi; raporda sayılır).

Karşılaştırma kural katmanındadır: `malzeme_kabul.kural.okuma_karsilastirma`
(`cikarim`'ı içe aktarmaz). Testlerde gerçek dil modeli yoktur; `SahteModel`
(tests/test_hibrit_hat.py) model yanıtı gibi davranır, ağ kullanmaz.

Eşleşmeyen satırlar için karar: sertifikadaki adı kabul dokümanındaki hiçbir
teste eşlenemeyen satır (`karar_motoru.eslestir` None dönerse) karşılaştırmada
**yok sayılır**. Böyle satırlar karara zaten girmez (`eslesmeyen_satirlar`) ve
anlaşmazlığı bağlayacak bir test_id yoktur.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from malzeme_kabul.katalog.ornek_veri import ornek_yukle
from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.sozlesme.okuma import HamOkuma
from malzeme_kabul.sozlesme.sema import KabulDokumani
from malzeme_kabul.sozlesme.sertifika import Sertifika, SertifikaSatiri
from tests.conftest import KOK
from tests.test_hibrit_hat import SET, SahteModel, sertifika_json

DOKUMAN_23377K = KOK / "data/cikti/MIL-PRF-23377K_kabul_dokumani.json"
ONAYLI_TEDARIKCILER = ("Kurgu Coatings Inc. (kurgusal)", "Ornek Aerospace Finishes Ltd. (kurgusal)")
FARKLI_OKUDU = "kural ve model farklı okudu"
S028_LOT = "A94009"  # S-028 sertifikasındaki parti numarası
S028_TEDARIKCI = "Kurgu Coatings Inc. (kurgusal)"  # S-028 sertifikasındaki tedarikçi


# --- yardımcılar -------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dokuman() -> KabulDokumani:
    return KabulDokumani.model_validate_json(DOKUMAN_23377K.read_text(encoding="utf-8"))


def sertifika(*satirlar: tuple) -> Sertifika:
    """(test_adi, sonuc[, birim]) üçlülerinden sertifika."""
    return Sertifika(
        sertifika_no="T-1",
        standart_atfi="MIL-PRF-23377K Type I Class N",
        satirlar=[SertifikaSatiri(test_adi=s[0], sonuc=s[1], birim=s[2] if len(s) > 2 else None) for s in satirlar],
    )


TEMEL = (
    ("VOC solvent content", "258", "g/L"),
    ("Viscosity", "33", "s"),
    ("Drying time", "2.6", "h"),
    ("Condition in container", "Conforms"),
    ("Pot life", "64", "s"),
)


def karsilastir(dokuman, kural_satirlari, model_satirlari):
    from malzeme_kabul.kural.okuma_karsilastirma import sertifika_okumalarini_karsilastir

    return sertifika_okumalarini_karsilastir(dokuman, sertifika(*kural_satirlari), sertifika(*model_satirlari))


def degistir(satirlar, ad, *yeni):
    return tuple((ad, *yeni) if s[0] == ad else s for s in satirlar)


# --- sertifika tarafı: kural modülü ----------------------------------------------------------


def test_anlasmazlik_modeli_fazla_alan_kabul_etmez():
    from malzeme_kabul.kural.okuma_karsilastirma import Anlasmazlik

    a = Anlasmazlik(taraf="sertifika", test_id="viscosity", test_adi="Viscosity", alan="deger",
                    kural="33", model="34", aciklama="x")
    assert a.model_dump()["alan"] == "deger"
    with pytest.raises(ValueError):
        Anlasmazlik(taraf="sertifika", test_id="v", test_adi="V", alan="deger", kural="1", model="2",
                    aciklama="x", karar="uygun")
    with pytest.raises(ValueError):
        Anlasmazlik(taraf="sertifika", test_id="v", test_adi="V", alan="sonuc", kural="1", model="2", aciklama="x")
    with pytest.raises(ValueError):
        Anlasmazlik(taraf="belge", test_id="v", test_adi="V", alan="deger", kural="1", model="2", aciklama="x")


def test_ayni_okumada_anlasmazlik_yok(dokuman):
    assert karsilastir(dokuman, TEMEL, TEMEL) == []


@pytest.mark.parametrize(
    "ad, kural_hucreleri, model_hucreleri",
    [
        ("VOC solvent content", ("320", "g/L"), ("320.0", "g/L")),   # sayı biçimi
        ("VOC solvent content", ("258", "g/L"), ("258", "g/l")),     # birimde büyük/küçük harf
        ("VOC solvent content", ("258", "g/L"), ("258", "g / L")),   # birimde iç boşluk (pint aynı çözer)
        ("Condition in container", ("Conforms",), ("conforms",)),    # metinde büyük/küçük harf
        ("Condition in container", ("Conforms",), ("  CONFORMS ",)),
        ("Viscosity", ("<1", "s"), ("< 1", "s")),                     # işaretle sayı arasında boşluk
    ],
)
def test_yalniz_bicim_farki_anlasmazlik_degildir(dokuman, ad, kural_hucreleri, model_hucreleri):
    assert karsilastir(dokuman, degistir(TEMEL, ad, *kural_hucreleri), degistir(TEMEL, ad, *model_hucreleri)) == []


def test_sayisal_deger_farki_deger_anlasmazligidir(dokuman):
    sonuc = karsilastir(dokuman, TEMEL, degistir(TEMEL, "VOC solvent content", "340", "g/L"))
    assert len(sonuc) == 1
    a = sonuc[0]
    assert (a.taraf, a.test_id, a.alan, a.kural, a.model) == ("sertifika", "voc_solvent_content", "deger", "258", "340")
    assert a.test_adi and a.aciklama


@pytest.mark.parametrize("kural_sonuc, model_sonuc", [("<1", "1"), ("1", "<1"), ("<1", "<=1"), (">5", "5")])
def test_karsilastirma_isareti_farki_deger_anlasmazligidir(dokuman, kural_sonuc, model_sonuc):
    sonuc = karsilastir(dokuman, degistir(TEMEL, "Viscosity", kural_sonuc, "s"), degistir(TEMEL, "Viscosity", model_sonuc, "s"))
    assert [(a.test_id, a.alan) for a in sonuc] == [("viscosity", "deger")]


def test_sinirin_hemen_alti_ve_ustu_farkli_degerdir(dokuman):
    # 340 g/L max sınırında: 339.9 ve 340.1 ikisi de 340'tan farklı okumadır.
    for model_degeri in ("339.9", "340.1"):
        sonuc = karsilastir(dokuman, degistir(TEMEL, "VOC solvent content", "340", "g/L"),
                            degistir(TEMEL, "VOC solvent content", model_degeri, "g/L"))
        assert [(a.alan, a.kural, a.model) for a in sonuc] == [("deger", "340", model_degeri)]


@pytest.mark.parametrize("kural_birim, model_birim", [("h", "min"), ("g/L", "lb/gal"), ("s", None), (None, "s")])
def test_birim_farki_birim_anlasmazligidir(dokuman, kural_birim, model_birim):
    sonuc = karsilastir(dokuman, degistir(TEMEL, "Pot life", "64", kural_birim),
                        degistir(TEMEL, "Pot life", "64", model_birim))
    assert [(a.test_id, a.alan, a.kural, a.model) for a in sonuc] == [("pot_life", "birim", kural_birim, model_birim)]


def test_deger_ve_birim_birlikte_farkliysa_ikisi_de_kaydedilir(dokuman):
    # S-089: kural "0.25 day" okur; model "5 hour max" şart hücresinden "5" ve "hour" okur.
    sonuc = karsilastir(dokuman, degistir(TEMEL, "Drying time", "0.25", "day"), degistir(TEMEL, "Drying time", "5", "hour"))
    assert {(a.test_id, a.alan) for a in sonuc} == {("drying_time", "deger"), ("drying_time", "birim")}


def test_sayisal_olmayan_sonuc_farki_deger_anlasmazligidir(dokuman):
    # İkisi de "geçti" anlamına gelse de okunan metin farklıdır.
    sonuc = karsilastir(dokuman, TEMEL, degistir(TEMEL, "Condition in container", "Pass"))
    assert [(a.test_id, a.alan, a.kural, a.model) for a in sonuc] == [
        ("condition_in_container", "deger", "Conforms", "Pass")]


def test_bir_okumada_eksik_satir_satir_anlasmazligidir(dokuman):
    eksik = tuple(s for s in TEMEL if s[0] != "Viscosity")
    model_eksik = karsilastir(dokuman, TEMEL, eksik)
    assert [(a.test_id, a.alan, a.kural, a.model) for a in model_eksik] == [("viscosity", "satir", "33", None)]
    kural_eksik = karsilastir(dokuman, eksik, TEMEL)
    assert [(a.test_id, a.alan, a.kural, a.model) for a in kural_eksik] == [("viscosity", "satir", None, "33")]


def test_eslesmeyen_satir_yok_sayilir(dokuman):
    # Hiçbir teste eşlenemeyen satır karara girmez; anlaşmazlık da üretmez.
    fazla = TEMEL + (("Mystery property", "12", "mg"),)
    assert karsilastir(dokuman, TEMEL, fazla) == []
    assert karsilastir(dokuman, fazla, TEMEL) == []
    assert karsilastir(dokuman, fazla, degistir(fazla, "Mystery property", "99", "mg")) == []


def test_anlasmazliklar_test_id_ye_gore_sirali_ve_deterministik(dokuman):
    model = degistir(TEMEL, "VOC solvent content", "340", "g/L")
    model = degistir(model, "Viscosity", "34", "s")
    model = degistir(model, "Condition in container", "Pass")
    model = degistir(model, "Drying time", "5", "hour")
    ilk = karsilastir(dokuman, TEMEL, model)
    assert [a.test_id for a in ilk] == sorted(a.test_id for a in ilk)
    assert {a.test_id for a in ilk} == {"voc_solvent_content", "viscosity", "condition_in_container", "drying_time"}
    karisik = random.Random(23377)
    for _ in range(5):
        k, m = list(TEMEL), list(model)
        karisik.shuffle(k)
        karisik.shuffle(m)
        assert karsilastir(dokuman, tuple(k), tuple(m)) == ilk


# --- ek durumlar: harf eki, çok satır, algılanmadı -------------------------------------------


def test_harf_eki_farki_deger_anlasmazligidir(dokuman):
    # ASTM D3359 yapışma derecesi: sayı aynı (4), harf farklı (A / B) -> farklı okuma.
    sonuc = karsilastir(dokuman, TEMEL + (("Adhesion", "4A"),), TEMEL + (("Adhesion", "4B"),))
    assert [(a.test_id, a.alan, a.kural, a.model) for a in sonuc] == [("adhesion", "deger", "4A", "4B")]


def test_harf_ekinde_buyuk_kucuk_harf_farki_anlasmazlik_degildir(dokuman):
    assert karsilastir(dokuman, TEMEL + (("Adhesion", "4A"),), TEMEL + (("Adhesion", "4a"),)) == []


KADMIYUM_SATIRLARI = (("Cadmium content", "0.4", "ppm"), ("Lead and cadmium content", "0.2", "ppm"))


def test_bir_teste_eslenen_coklu_satirlar_ayniysa_anlasmazlik_yok(dokuman):
    # İki ad da lead_and_cadmium_content testine eşlenir; satır sırası önemsizdir.
    assert karsilastir(dokuman, TEMEL + KADMIYUM_SATIRLARI, TEMEL + KADMIYUM_SATIRLARI[::-1]) == []


def test_bir_teste_eslenen_coklu_satirlar_farkliysa_tek_deger_anlasmazligi(dokuman):
    model = TEMEL + (KADMIYUM_SATIRLARI[0], ("Lead and cadmium content", "0.9", "ppm"))
    sonuc = karsilastir(dokuman, TEMEL + KADMIYUM_SATIRLARI, model)
    assert [(a.test_id, a.alan) for a in sonuc] == [("lead_and_cadmium_content", "deger")]
    assert "0.2" in sonuc[0].kural and "0.9" in sonuc[0].model


def test_algilanmadi_ifadesi_ile_yalniz_sinir_farkli_okumadir(dokuman):
    # Temkinli davranış: "ND (<0.5 ppm)" ile "<0.5 ppm" aynı sayıyı verse de farklı okuma sayılır.
    sonuc = karsilastir(dokuman, TEMEL + (("Cadmium content", "ND (<0.5 ppm)"),),
                        TEMEL + (("Cadmium content", "<0.5 ppm"),))
    assert [(a.test_id, a.alan, a.kural, a.model) for a in sonuc] == [
        ("lead_and_cadmium_content", "deger", "ND (<0.5 ppm)", "<0.5 ppm")]


# --- standart tarafı: kural modülü -----------------------------------------------------------


def _sart(id_: str, ad: str, **sinir) -> dict:
    return {
        "id": id_, "test_adi": ad, "test_turleri": ["kabul"],
        "kaynak": {"belge_no": "MIL-PRF-23377", "revizyon": "K", "madde": "3.4"},
        "sinir": {"kriter_turu": "sayisal", "orijinal_metin": "x", **sinir},
    }


@pytest.fixture
def kucuk_dokuman() -> KabulDokumani:
    return KabulDokumani.model_validate({
        "standart": {"belge_no": "MIL-PRF-23377", "revizyon": "K"},
        "testler": [
            _sart("cadmium", "Cadmium content", ust=1, birim="ppm"),                 # yön türetilir: en_cok
            _sart("flexibility", "Flexibility", alt=10, birim="percent"),             # yön türetilir: en_az
            _sart("viscosity", "Viscosity", alt=15, ust=30, birim="second"),          # yön türetilir: aralik
            _sart("pot_life", "Pot life", ust=70, birim="second", yon="en_cok"),      # yön açıkça yazılı
        ],
    })


def okuma(sart_id: str, ham: str, yon: str | None, alan: str = "sinir", sayfa: int = 1) -> HamOkuma:
    return HamOkuma(sart_id=sart_id, alan=alan, ham_metin=ham, konum={"sayfa": sayfa},
                    sinir_yonu=yon if alan == "sinir" else None)


def standart_karsilastir(okumalar, dokuman):
    from malzeme_kabul.kural.okuma_karsilastirma import standart_okumalarini_karsilastir

    return standart_okumalarini_karsilastir(okumalar, dokuman)


def test_standart_uyumlu_okumada_anlasmazlik_yok(kucuk_dokuman):
    okumalar = [
        okuma("cadmium", "not greater than 1 ppm", "en_cok"),
        okuma("flexibility", "10 percent minimum", "en_az"),
        okuma("viscosity", "15 to 30 seconds", "aralik"),
        okuma("viscosity", "15.0 to 30 seconds", "aralik"),   # sayı biçimi farkı anlaşmazlık değil
        okuma("pot_life", "70 seconds max", "en_cok"),
    ]
    assert standart_karsilastir(okumalar, kucuk_dokuman) == []


def test_standart_yon_farki_yon_anlasmazligidir(kucuk_dokuman):
    sonuc = standart_karsilastir([okuma("cadmium", "not greater than 1 ppm", "en_az")], kucuk_dokuman)
    assert [(a.taraf, a.test_id, a.alan, a.kural, a.model) for a in sonuc] == [
        ("standart", "cadmium", "yon", "en_cok", "en_az")]


def test_standart_yonu_acikca_yazilmissa_o_kullanilir(kucuk_dokuman):
    sonuc = standart_karsilastir([okuma("pot_life", "70 seconds", "en_az")], kucuk_dokuman)
    assert [(a.alan, a.kural, a.model) for a in sonuc] == [("yon", "en_cok", "en_az")]


def test_standart_aralik_ve_tek_yon_farki(kucuk_dokuman):
    sonuc = standart_karsilastir([okuma("viscosity", "15 to 30 seconds", "en_cok")], kucuk_dokuman)
    assert [(a.test_id, a.alan, a.kural, a.model) for a in sonuc] == [("viscosity", "yon", "aralik", "en_cok")]


@pytest.mark.parametrize("ham", ["15 to 35 seconds", "14 to 30 seconds", "30 seconds max", "15 to 30.5 seconds"])
def test_standart_sinir_sayisi_farki_sinir_anlasmazligidir(kucuk_dokuman, ham):
    sonuc = standart_karsilastir([okuma("viscosity", ham, None)], kucuk_dokuman)
    assert [(a.test_id, a.alan) for a in sonuc] == [("viscosity", "sinir")]
    assert sonuc[0].model and sonuc[0].kural


def test_standart_tek_sinirin_hemen_alti_ve_ustu_farklidir(kucuk_dokuman):
    for ham in ("0.9 ppm max", "1.1 ppm max"):
        sonuc = standart_karsilastir([okuma("cadmium", ham, "en_cok")], kucuk_dokuman)
        assert [(a.test_id, a.alan) for a in sonuc] == [("cadmium", "sinir")], ham


@pytest.mark.parametrize("yon", [None, "belirsiz"])
def test_standart_belirsiz_ya_da_bos_yon_karsilastirilmaz(kucuk_dokuman, yon):
    assert standart_karsilastir([okuma("cadmium", "not greater than 1 ppm", yon)], kucuk_dokuman) == []


def test_standart_eslesmeyen_sart_id_atlanir(kucuk_dokuman):
    okumalar = [okuma("bilinmeyen_sart", "5 to 500 seconds", "en_az")]
    assert standart_karsilastir(okumalar, kucuk_dokuman) == []


def test_standart_sinir_disindaki_alanlar_karsilastirilmaz(kucuk_dokuman):
    okumalar = [okuma("viscosity", "ASTM D 1200", None, alan="test_metodu"),
                okuma("viscosity", "99 seconds", None, alan="birim")]
    assert standart_karsilastir(okumalar, kucuk_dokuman) == []


@pytest.mark.xfail(strict=True, reason=(
    "Bilinen sınırlama: standart tarafında sayıların işareti yok sayılıyor ('15-30' tiresi eksi sanılmasın "
    "diye); '-5 to 5' sınırı ile '5 to 5' okuması aynı sayı kümesi sayılıyor. Düzeltilince bu test geçer "
    "ve xfail kaldırılmalıdır."))
def test_standart_negatif_sinir_isareti_farki_yakalanir():
    dok = KabulDokumani.model_validate({
        "standart": {"belge_no": "MIL-PRF-23377", "revizyon": "K"},
        "testler": [_sart("dusuk_sicaklik", "Low temperature", alt=-5, ust=5, birim="degC")],
    })
    sonuc = standart_karsilastir([okuma("dusuk_sicaklik", "5 to 5 degrees", "aralik")], dok)
    assert [(a.test_id, a.alan) for a in sonuc] == [("dusuk_sicaklik", "sinir")]


# --- standart_okumalarini_dogrula ----------------------------------------------------------


class _Sayfa:
    def __init__(self, no, metin):
        self.no, self.metin, self.tablolar = no, metin, []


class _Belge:
    def __init__(self, sayfalar):
        self.sayfalar = [_Sayfa(i, m) for i, m in enumerate(sayfalar, 1)]
        self.dosya = Path("x.pdf")


STANDART_BELGE = _Belge(["3.5 viscosity 15 to 35 seconds. Flexibility 10 percent minimum."])


def test_standart_okuma_dogrulamasi_kural_dokumaniyla_anlasmayi_belirsizlestirir(kucuk_dokuman):
    from malzeme_kabul.hat.hibrit_hat import standart_okumalarini_dogrula

    okumalar = [okuma("viscosity", "15 to 35 seconds", "aralik"), okuma("flexibility", "10 percent minimum", "en_az")]
    d = standart_okumalarini_dogrula(okumalar, STANDART_BELGE, kural_dokumani=kucuk_dokuman)
    yonler = {o.sart_id: o.sinir_yonu for o in d.kabul}
    assert yonler == {"viscosity": "belirsiz", "flexibility": "en_az"}
    assert [(a.test_id, a.alan) for a in d.anlasmazliklar] == [("viscosity", "sinir")]


def test_standart_okuma_dogrulamasi_kural_dokumani_yoksa_eskisi_gibi():
    from malzeme_kabul.hat.hibrit_hat import standart_okumalarini_dogrula

    okumalar = [okuma("viscosity", "15 to 35 seconds", "aralik")]
    d = standart_okumalarini_dogrula(okumalar, STANDART_BELGE)
    assert [o.sinir_yonu for o in d.kabul] == ["aralik"]
    assert d.anlasmazliklar == []


# --- hibrit hat ------------------------------------------------------------------------------


@pytest.fixture
def katalog():
    k = Katalog()
    ornek_yukle(k, KOK / "data/ornek/katalog.json", KOK)
    for t in ONAYLI_TEDARIKCILER:
        k.tedarikci_onayla("AST-001", t)
    # S-028'in kendi partisi: sertifikadaki parti no ve tedarikçi bu partiyle tutar (K3 denetimleri).
    # data/ornek/katalog.json'daki A-2512-01 "Örnek Tedarikçi A"nındır, S-028 için kullanılmaz.
    k.parti_ekle(S028_LOT, "AST-001", S028_TEDARIKCI, "K", "2025-12-10")
    yield k
    k.kapat()


def satir(karar, test_id):
    return next(s for s in karar.kontrol.satirlar if s.test_id == test_id)


def ek_denetim(karar, test_id):
    return [d for d in karar.ek_denetimler if d.test_id == test_id]


def denetim(katalog) -> dict:
    """Parti durumu yazan karar için defter (katalogla aynı bağlantıda) ve kullanıcı."""
    return {"defter": DenetimKaydi(katalog.baglanti), "kullanici": "gk1"}


def hibrit(katalog, no, bozucu=None, **k):
    from malzeme_kabul.hat.hibrit_hat import sertifika_hatti

    return sertifika_hatti(katalog, "AST-001", SET / f"pdf/{no}.pdf", mod="hibrit",
                           istemci=SahteModel(sertifika_json(no), bozucu), **k)


UST_ALANLARI = ("tedarikci", "parti_no", "sertifika_no", "uretim_tarihi", "standart_atfi")


class UstBilgiliSahteModel(SahteModel):
    """SahteModel, üretim tarihini de döner (temel SahteModel yalnız atıf, no, tedarikçi ve partiyi döner)."""

    def sohbet(self, mesajlar, sema):
        import json

        yanit = json.loads(super().sohbet(mesajlar, sema))
        yanit["uretim_tarihi"] = self.sertifika.uretim_tarihi
        return json.dumps(yanit)


def ayni_okuyan_model(pdf: Path) -> UstBilgiliSahteModel:
    """Kural okuyucunun okuduğu üst bilgileri ve satırları aynen döndüren sahte model."""
    from malzeme_kabul.belge.pdf_okuyucu import pdf_oku
    from malzeme_kabul.cikarim.sertifika_okuyucu import kural_ile_oku

    return UstBilgiliSahteModel(kural_ile_oku(pdf_oku(pdf)))


def test_kural_ve_model_ayni_okursa_okuma_uyumu_uygun(katalog):
    from malzeme_kabul.hat.hibrit_hat import sertifika_hatti

    pdf = SET / "pdf/S-028.pdf"
    model = ayni_okuyan_model(pdf)
    assert all(getattr(model.sertifika, a) for a in UST_ALANLARI)  # üst bilgilerin hepsi okundu, boş değil
    karar, okuma_ = sertifika_hatti(katalog, "AST-001", pdf, mod="hibrit", istemci=model, lot_no=S028_LOT,
                                   **denetim(katalog))
    assert {a: getattr(okuma_.sertifika, a) for a in UST_ALANLARI} == {
        a: getattr(okuma_.kural_sertifikasi, a) for a in UST_ALANLARI}
    assert okuma_.kanitsiz == [] and okuma_.anlasmazliklar == []
    assert ek_denetim(karar, "parti_no")[0].karar == "uygun"
    assert ek_denetim(karar, "parti_tedarikcisi")[0].karar == "uygun"
    assert karar.hat["anlasmazlik_sayisi"] == 0 and karar.hat["anlasmazliklar"] == []
    uyum = ek_denetim(karar, "okuma_uyumu")
    assert len(uyum) == 1 and uyum[0].karar == "uygun" and uyum[0].test_adi == "Kural ve model okuma uyumu"
    assert (karar.parti_karari, karar.parti_durumu) == ("kabul", "serbest")


def test_model_farkli_ama_kanitli_deger_okursa_satir_insana_gider(katalog, tmp_path):
    from malzeme_kabul.hat.hibrit_hat import sertifika_hatti

    # VOC satırında "Result" 258 g/L, "Retest" 312 g/L: iki değer de o satırın sonuç hücreleridir
    # (şart hücresi "340 g/L max" değil), ikisi de 340 g/L sınırının içindedir. Kural "Result"u okur,
    # model tekrar testi okur: kanıtlı ama farklı okuma.
    katalog.parti_ekle(TEKRAR_LOT, "AST-001", ONAYLI_TEDARIKCILER[0], "K", "2025-12-10")
    pdf = tekrar_testli_pdf(tmp_path / "voc.pdf", s028_satirlari(), "VOC solvent content", "312 g/L")

    # Önce kural modu: kendi partisinde (hiç karar verilmemiş) serbest bırakılır.
    kayit = denetim(katalog)  # iki karar da aynı defter zincirine yazılır
    kural, _ = sertifika_hatti(katalog, "AST-001", pdf, mod="kural", lot_no=TEKRAR_LOT, **kayit)
    assert satir(kural, "voc_solvent_content").karar == "uygun"
    assert (kural.parti_karari, kural.parti_durumu) == ("kabul", "serbest")

    model = SahteModel(model_sertifikasi(pdf, **{"VOC solvent content": ("312", "g/L")}))
    karar, okuma_ = sertifika_hatti(katalog, "AST-001", pdf, mod="hibrit", istemci=model, lot_no=TEKRAR_LOT,
                                   **kayit)
    assert okuma_.kanitsiz == []
    assert [(a.test_id, a.alan, a.kural, a.model) for a in okuma_.anlasmazliklar] == [
        ("voc_solvent_content", "deger", "258", "312")]
    voc = satir(karar, "voc_solvent_content")
    assert voc.karar == "insan_incelemeli" and FARKLI_OKUDU in voc.gerekce
    assert karar.hat["anlasmazlik_sayisi"] == 1
    assert karar.hat["anlasmazliklar"][0]["test_id"] == "voc_solvent_content"
    uyum = ek_denetim(karar, "okuma_uyumu")
    assert len(uyum) == 1 and uyum[0].karar == "insan_incelemeli" and "1" in uyum[0].gerekce
    assert (karar.parti_karari, karar.parti_durumu) == ("inceleme", "bekliyor")
    assert katalog.parti("AST-001", TEKRAR_LOT).durum == "bekliyor"


def test_kural_red_model_kabul_derse_sessizce_ne_red_ne_kabul(katalog, tmp_path):
    from malzeme_kabul.hat.hibrit_hat import sertifika_hatti

    # S-089 satırları: "Drying time" Result "0.25 day" (6 saat) > 5 saat; kural okuması reddeder.
    # Aynı satırın "Retest" hücresi "5 hour": sınırın tam üstünde (en çok 5 saat), uygun.
    pdf = tekrar_testli_pdf(tmp_path / "kuruma.pdf", s028_satirlari("S-089"), "Drying time", "5 hour",
                            tedarikci=ONAYLI_TEDARIKCILER[1])
    kural, _ = sertifika_hatti(katalog, "AST-001", pdf, mod="kural")
    assert satir(kural, "drying_time").karar == "uygun_degil" and kural.parti_karari == "red"

    # Model tekrar testinden "5" ve "hour" okur: kanıtlı, tek başına uygun olurdu.
    model = SahteModel(model_sertifikasi(pdf, **{"Drying time": ("5", "hour")}))
    karar, okuma_ = sertifika_hatti(katalog, "AST-001", pdf, mod="hibrit", istemci=model, lot_no="A-2512-01",
                                   **denetim(katalog))
    assert okuma_.kanitsiz == []
    assert {(a.test_id, a.alan, a.kural, a.model) for a in okuma_.anlasmazliklar} == {
        ("drying_time", "deger", "0.25", "5"), ("drying_time", "birim", "day", "hour")}
    kuruma = satir(karar, "drying_time")
    assert kuruma.karar == "insan_incelemeli" and FARKLI_OKUDU in kuruma.gerekce
    assert karar.parti_karari == "inceleme"
    assert karar.parti_durumu == "bekliyor"  # ne serbest ne karantina
    assert karar.hat["anlasmazlik_sayisi"] == 2


def test_kural_modunda_anlasmazlik_alanlari_bos_ve_okuma_uyumu_yok(katalog):
    from malzeme_kabul.hat.hibrit_hat import sertifika_hatti

    karar, okuma_ = sertifika_hatti(katalog, "AST-001", SET / "pdf/S-028.pdf", mod="kural")
    assert okuma_.anlasmazliklar == []
    assert karar.hat["anlasmazliklar"] == [] and karar.hat["anlasmazlik_sayisi"] == 0
    assert ek_denetim(karar, "okuma_uyumu") == []


def test_model_hata_verip_kurala_dusulurse_anlasmazlik_yok(katalog):
    from malzeme_kabul.hat.hibrit_hat import sertifika_hatti

    model = SahteModel(sertifika_json("S-028"), hata=ConnectionRefusedError("bağlantı reddedildi"))
    karar, okuma_ = sertifika_hatti(katalog, "AST-001", SET / "pdf/S-028.pdf", mod="hibrit", istemci=model)
    assert okuma_.yedek
    assert okuma_.anlasmazliklar == []
    assert karar.hat["anlasmazliklar"] == [] and karar.hat["anlasmazlik_sayisi"] == 0
    assert ek_denetim(karar, "okuma_uyumu") == []  # yedekte karşılaştırma yok, satır da yok


def test_denetim_kaydinda_anlasmazliklar_gorunur(katalog, tmp_path):
    from malzeme_kabul.hat.hibrit_hat import sertifika_hatti

    # VOC: kural "Result" 258'i, model aynı satırın "Retest" hücresindeki 312'yi okur (kanıtlı).
    pdf = tekrar_testli_pdf(tmp_path / "voc.pdf", s028_satirlari(), "VOC solvent content", "312 g/L")
    d = DenetimKaydi(katalog.baglanti)
    model = SahteModel(model_sertifikasi(pdf, **{"VOC solvent content": ("312", "g/L")}))
    sertifika_hatti(katalog, "AST-001", pdf, mod="hibrit", istemci=model, lot_no="A-2512-01",
                    defter=d, kullanici="gk1")
    hat = d.kayitlar("karar")[-1].veri["hat"]
    assert hat["anlasmazlik_sayisi"] == 1
    assert [(a["test_id"], a["alan"], a["kural"], a["model"]) for a in hat["anlasmazliklar"]] == [
        ("voc_solvent_content", "deger", "258", "312")]
    assert d.zinciri_dogrula().gecerli


def test_incelemeye_alinacak_kontrol_satirini_insana_cevirir(katalog):
    from malzeme_kabul.hat.katalog_karari import malzeme_koduyla_kontrol

    s = sertifika_json("S-028")
    temel = malzeme_koduyla_kontrol(katalog, "AST-001", s)
    assert temel.parti_karari == "kabul"
    karar = malzeme_koduyla_kontrol(katalog, "AST-001", s, incelemeye_alinacak={"viscosity": "kural ve model farklı okudu: 33 / 34"})
    v = satir(karar, "viscosity")
    assert v.karar == "insan_incelemeli" and FARKLI_OKUDU in v.gerekce
    assert karar.parti_karari == "inceleme" and karar.parti_durumu == "bekliyor"


def test_incelemeye_alinacak_kontrolde_olmayan_test_icin_ek_satir_eklenir(katalog):
    from malzeme_kabul.hat.katalog_karari import malzeme_koduyla_kontrol

    karar = malzeme_koduyla_kontrol(katalog, "AST-001", sertifika_json("S-028"),
                                    incelemeye_alinacak={"olmayan_test": "kural ve model farklı okudu"})
    ek = ek_denetim(karar, "olmayan_test")
    assert len(ek) == 1 and ek[0].karar == "insan_incelemeli" and FARKLI_OKUDU in ek[0].gerekce
    assert karar.parti_karari == "inceleme"


# --- gözden geçiren düzeltmeleri: tip/sınıf eşleştirmesi, atıf, birim harfi, ikisi de dışarıda ------


def test_eslestirme_tip_sinifa_gore_suzulmus_testlerle_yapilir(dokuman):
    # "Color" tam test kümesinde belirsizdir (color_type_i ve color_type_ii); Type I için color_type_i'dir.
    from malzeme_kabul.kural.okuma_karsilastirma import sertifika_okumalarini_karsilastir

    kural = sertifika(*TEMEL, ("Color", "Does not conform"))
    model = sertifika(*TEMEL, ("Color", "Conforms"))
    sonuc = sertifika_okumalarini_karsilastir(dokuman, kural, model, tip="I", sinif="N")
    assert [(a.test_id, a.alan, a.kural, a.model) for a in sonuc] == [
        ("color_type_i", "deger", "Does not conform", "Conforms")]
    sonuc_ii = sertifika_okumalarini_karsilastir(dokuman, kural, model, tip="II", sinif="C2")
    assert [(a.test_id, a.alan) for a in sonuc_ii] == [("color_type_ii", "deger")]


def _atifli(atif: str, satirlar=TEMEL) -> Sertifika:
    return sertifika(*satirlar).model_copy(update={"standart_atfi": atif})


@pytest.mark.parametrize("kural_atfi, model_atfi", [
    ("MIL-PRF-23377K Type I Class N", "MIL-PRF-23377J Type I Class N"),   # revizyon
    ("MIL-PRF-23377K Type I Class N", "MIL-PRF-23377K Type I Class C2"),  # sınıf
    ("MIL-PRF-23377K Type I Class N", "MIL-PRF-23377K Type II Class N"),  # tip
    ("MIL-PRF-23377K Type I Class N", "MIL-PRF-85285E Type I Class N"),   # belge no
])
def test_standart_atfi_farki_revizyon_anlasmazligidir(dokuman, kural_atfi, model_atfi):
    from malzeme_kabul.kural.okuma_karsilastirma import sertifika_okumalarini_karsilastir

    sonuc = sertifika_okumalarini_karsilastir(dokuman, _atifli(kural_atfi), _atifli(model_atfi))
    assert [(a.taraf, a.test_id, a.alan, a.kural, a.model) for a in sonuc] == [
        ("sertifika", "revizyon", "deger", kural_atfi, model_atfi)]


@pytest.mark.parametrize("kural_atfi, model_atfi", [
    ("MIL-PRF-23377K Type I Class C2", "MIL-PRF-23377 K, Type I, Class C2"),
    ("MIL-PRF-23377K Type I Class C2", "MIL-PRF-23377 Rev. K, Type I, Class C2"),
    ("MIL-PRF-23377K Type I Class C2", "mil-prf-23377k  type 1 class c2"),
])
def test_standart_atfinda_yalniz_bicim_farki_anlasmazlik_degildir(dokuman, kural_atfi, model_atfi):
    from malzeme_kabul.kural.okuma_karsilastirma import sertifika_okumalarini_karsilastir

    assert sertifika_okumalarini_karsilastir(dokuman, _atifli(kural_atfi), _atifli(model_atfi)) == []


@pytest.mark.parametrize("kural_birim, model_birim", [
    ("mg", "Mg"),      # miligram / megagram
    ("mL", "ML"),      # mililitre / megalitre
    ("g/L", "G/L"),    # pint: gauss / litre
    ("KU", "Ku"),      # pint çözemez: harf duyarlı metin
    ("KU", "ku"),      # biri çözülemez, öteki (pint'te kilo-amu) çözülür
])
def test_birimde_harf_farki_anlam_degistiriyorsa_anlasmazliktir(dokuman, kural_birim, model_birim):
    sonuc = karsilastir(dokuman, degistir(TEMEL, "Pot life", "64", kural_birim),
                        degistir(TEMEL, "Pot life", "64", model_birim))
    assert [(a.test_id, a.alan, a.kural, a.model) for a in sonuc] == [("pot_life", "birim", kural_birim, model_birim)]


@pytest.mark.parametrize("kural_birim, model_birim", [
    ("g/L", "g/l"),               # pint ikisini de gram / liter çözer
    ("g/L", "g / L"),
    ("Krebs unit", "Krebs  unit"),  # pint çözemez: boşluk atılmış metin aynı
])
def test_birimde_ayni_anlama_gelen_yazimlar_anlasmazlik_degildir(dokuman, kural_birim, model_birim):
    assert karsilastir(dokuman, degistir(TEMEL, "Pot life", "64", kural_birim),
                       degistir(TEMEL, "Pot life", "64", model_birim)) == []


# Hat düzeyi senaryolar için küçük sertifika PDF'i (tmp_path altında; data/ altına yazılmaz).


BASLIK = ("Test", "Method", "Requirement", "Result", "Units")
# Ek "Retest" sütunu: tedarikçinin tekrar test sonucu. Kural okuyucu yalnız "Result" sütununu okur
# ("retest" başlığı tanınmaz); model ise aynı satırın sonuç olarak yazılmış tekrar test değerini okuyabilir.
# İki okuma da o satırın kendi sonuç hücrelerine dayanır (şart ya da metot hücresine değil): kanıtlı,
# gerçek bir okuma anlaşmazlığıdır.
TEKRAR_BASLIK = (*BASLIK, "Retest")
TEKRAR_LOT = "T900"  # sertifika_pdf_yaz'ın yazdığı parti numarası


def sertifika_pdf_yaz(yol: Path, satirlar: list[list], atif: str, notlar: tuple[str, ...] = (),
                      baslik: tuple[str, ...] = BASLIK, tedarikci: str = ONAYLI_TEDARIKCILER[0]) -> Path:
    """S-028 düzeninde tek sayfalık sertifika: üst bilgi, isteğe bağlı not satırları, test tablosu."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    stil = ParagraphStyle("g", fontName="Helvetica", fontSize=9, leading=11)
    ogeler = [Paragraph(m, stil) for m in (tedarikci, "Certificate No T-900", f"Batch/Lot {TEKRAR_LOT}",
                                             f"Specification {atif}", *notlar)]
    tablo = [list(baslik)]
    tablo += [[Paragraph(str(h or ""), stil) for h in s] for s in satirlar]
    genislik = [170, 85, 90, 80, 55] if len(baslik) == 5 else [170, 70, 75, 55, 45, 60]
    t = Table(tablo, colWidths=genislik)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, "grey")]))
    SimpleDocTemplate(str(yol), pagesize=A4, invariant=1).build(ogeler + [Spacer(1, 8), t])
    return yol


ATIF_K = "MIL-PRF-23377K Type I Class N"


def s028_satirlari(no: str = "S-028", **degisiklik) -> list[list]:
    """Sertifika satırları [ad, metot, şart, sonuç, birim]; degisiklik: {eski_ad_öneki: [yeni hücreler]}."""
    satirlar = [[x.test_adi, x.metot, x.sart, x.sonuc, x.birim] for x in sertifika_json(no).satirlar]
    for onek, yeni in degisiklik.items():
        for s in satirlar:
            if s[0].startswith(onek):
                s[:] = yeni
    return satirlar


def tekrar_testli_pdf(yol: Path, satirlar: list[list], ad: str, tekrar: str,
                      tedarikci: str = ONAYLI_TEDARIKCILER[0]) -> Path:
    """Satırlardan PDF; adı `ad` olan satırın "Retest" sütununa `tekrar` yazılır, ötekilerinki boştur."""
    satirlar = [[*s, tekrar if s[0] == ad else None] for s in satirlar]
    return sertifika_pdf_yaz(yol, satirlar, ATIF_K, baslik=TEKRAR_BASLIK, tedarikci=tedarikci)


def model_sertifikasi(pdf: Path, atif: str | None = None, **hucreler) -> Sertifika:
    """Modelin okuması: kural okumasının aynısı, verilen satırlarda {ad: (sonuç, birim)} farkıyla."""
    from malzeme_kabul.belge.pdf_okuyucu import pdf_oku
    from malzeme_kabul.cikarim.sertifika_okuyucu import kural_ile_oku

    s = kural_ile_oku(pdf_oku(pdf))
    satirlar = [x.model_copy(update=dict(zip(("sonuc", "birim"), hucreler[x.test_adi]))) if x.test_adi in hucreler else x
                for x in s.satirlar]
    return s.model_copy(update={"satirlar": satirlar, "standart_atfi": atif or s.standart_atfi})


def test_hatta_tip_sinifa_gore_eslenen_satir_anlasmazliginda_insana_gider(katalog, tmp_path):
    from malzeme_kabul.hat.hibrit_hat import sertifika_hatti

    # Kural "Result" hücresindeki "Conforms"u okur, model aynı satırın "Retest" hücresindeki "Pass"i
    # (kanıtlı; metot hücresindeki "Pass/Fail" değil). İki okuma da tek başına uygun olurdu, farkı
    # insan görmeli. Satır adı yalnız "Color" (AST-001 Type I). Düz sonuç kullanılır: dipnotlu
    # "Conforms*" kural okumasında tek başına belirsizdir (K1 beyaz listesi), anlaşmazlığın etkisini gizlerdi.
    renk_satiri = ["Color", "Visual Pass/Fail", "See spec", "Conforms", None]
    pdf = tekrar_testli_pdf(tmp_path / "renk.pdf", s028_satirlari(Color=renk_satiri), "Color", "Pass")
    kural, _ = sertifika_hatti(katalog, "AST-001", pdf, mod="kural")
    assert satir(kural, "color_type_i").karar == "uygun" and kural.parti_karari == "kabul"
    model = SahteModel(model_sertifikasi(pdf, Color=("Pass", None)))
    karar, okuma_ = sertifika_hatti(katalog, "AST-001", pdf, mod="hibrit", istemci=model)
    assert okuma_.kanitsiz == []
    assert [(a.test_id, a.alan, a.kural, a.model) for a in okuma_.anlasmazliklar] == [
        ("color_type_i", "deger", "Conforms", "Pass")]
    renk = satir(karar, "color_type_i")
    assert renk.karar == "insan_incelemeli" and FARKLI_OKUDU in renk.gerekce
    assert karar.parti_karari == "inceleme"


def test_hatta_atif_farkinda_revizyon_satiri_insana_gider(katalog, tmp_path):
    from malzeme_kabul.hat.hibrit_hat import sertifika_hatti

    # Kural "Specification" satırından J okur; model belgede de geçen (kanıtlı) K atfını okur.
    pdf = sertifika_pdf_yaz(tmp_path / "atif.pdf", s028_satirlari(), "MIL-PRF-23377J Type I Class N",
                            notlar=(f"Previously {ATIF_K}",))
    karar, okuma_ = sertifika_hatti(katalog, "AST-001", pdf, mod="hibrit",
                                    istemci=SahteModel(model_sertifikasi(pdf, atif=ATIF_K)))
    assert okuma_.kanitsiz == []
    assert [(a.test_id, a.alan, a.kural, a.model) for a in okuma_.anlasmazliklar] == [
        ("revizyon", "deger", "MIL-PRF-23377J Type I Class N", ATIF_K)]
    assert karar.kontrol.revizyon.karar == "insan_incelemeli" and FARKLI_OKUDU in karar.kontrol.revizyon.gerekce
    assert karar.parti_karari != "kabul"


def test_iki_okuma_da_sinir_disindaysa_uygun_degil_kalir_ve_anlasmazlik_sayilir(katalog, tmp_path):
    from malzeme_kabul.hat.hibrit_hat import sertifika_hatti

    # VOC en çok 340 g/L: kural "Result" 400'ü, model aynı satırın "Retest" hücresindeki 401'i okur
    # (kanıtlı). İkisi de sınır dışı.
    voc = ["VOC solvent content", "ASTM D3960", "340 g/L max", "400", "g/L"]
    pdf = tekrar_testli_pdf(tmp_path / "voc.pdf", s028_satirlari(VOC=voc), "VOC solvent content", "401 g/L")
    model = SahteModel(model_sertifikasi(pdf, **{"VOC solvent content": ("401", "g/L")}))
    karar, okuma_ = sertifika_hatti(katalog, "AST-001", pdf, mod="hibrit", istemci=model, lot_no="A-2512-01",
                                   **denetim(katalog))
    assert okuma_.kanitsiz == []
    assert [(a.test_id, a.alan, a.kural, a.model) for a in okuma_.anlasmazliklar] == [
        ("voc_solvent_content", "deger", "400", "401")]
    v = satir(karar, "voc_solvent_content")
    assert v.karar == "uygun_degil" and FARKLI_OKUDU in v.gerekce
    assert (karar.parti_karari, karar.parti_durumu) == ("red", "karantina")
    assert karar.hat["anlasmazlik_sayisi"] == 1
    assert ek_denetim(karar, "okuma_uyumu")[0].karar == "insan_incelemeli"


def test_dokuman_verilmeden_hibrit_okumada_okuma_uyumu_uygun_demez():
    # Karar: hata değil; okuma_uyumu insan_incelemeli ("karşılaştırma yapılamadı").
    from malzeme_kabul.belge.pdf_okuyucu import pdf_oku
    from malzeme_kabul.hat.hibrit_hat import sertifikayi_oku

    o = sertifikayi_oku(pdf_oku(SET / "pdf/S-028.pdf"), "hibrit", SahteModel(sertifika_json("S-028")))
    d = o.okuma_uyumu_denetimi()
    assert d is not None and d.karar == "insan_incelemeli" and "karşılaştırma yapılamadı" in d.gerekce


# --- genel yardımcı fonksiyonlar: anlaşmazlık kararı, aranan/uygulanan testler, atıf çözümü ---------

KARARLAR = ("uygun", "uygun_degil", "insan_incelemeli")


@pytest.mark.parametrize("model_karari", KARARLAR)
@pytest.mark.parametrize("kural_karari", (*KARARLAR, None))
def test_anlasmazlik_karari_yalniz_ikisi_de_uygun_degilse_uygun_degil(model_karari, kural_karari):
    # Fonksiyon kural/okuma_karsilastirma.py içinde (karar_motoru'nda değil).
    from malzeme_kabul.kural.okuma_karsilastirma import anlasmazlik_karari

    beklenen = "uygun_degil" if (model_karari, kural_karari) == ("uygun_degil", "uygun_degil") else "insan_incelemeli"
    assert anlasmazlik_karari(model_karari, kural_karari) == beklenen


@pytest.fixture
def tip_sinif_dokumani() -> KabulDokumani:
    def sart(id_, ad, uyg=(), kaynak="coc", kriter="gecti_kaldi"):
        return {"id": id_, "test_adi": ad, "test_turleri": ["kabul"], "uygulanabilirlik": list(uyg),
                "sonuc_kaynagi": kaynak, "kaynak": {"belge_no": "MIL-PRF-23377", "revizyon": "K", "madde": "3.6"},
                "sinir": {"kriter_turu": kriter, "orijinal_metin": "x"}}

    return KabulDokumani.model_validate({
        "standart": {"belge_no": "MIL-PRF-23377", "revizyon": "K"},
        "testler": [
            sart("color_type_i", "Color - Type I", ["Type I"]),
            sart("color_type_ii", "Color - Type II", ["Type II"]),
            sart("odor", "Odor"),
            sart("korozyon", "Corrosion resistance", kaynak="ic_laboratuvar"),
            {**sart("yeterlilik", "Qualification only"), "test_turleri": ["yeterlilik"]},
        ],
    })


@pytest.mark.parametrize("tip, secilen, secilmeyen", [("I", "color_type_i", "color_type_ii"),
                                                      ("II", "color_type_ii", "color_type_i")])
def test_aranan_ve_uygulanan_testler_tipe_gore_suzulur(tip_sinif_dokumani, tip, secilen, secilmeyen):
    from malzeme_kabul.kural.karar_motoru import aranan_testler, uygulanan_testler

    for fonk in (aranan_testler, uygulanan_testler):
        idler = {t.id for t in fonk(tip_sinif_dokumani, tip, "N")}
        assert secilen in idler and secilmeyen not in idler and "odor" in idler, fonk.__name__
        assert "yeterlilik" not in idler  # yalnız kabul testleri


def test_ic_laboratuvar_testi_uygulanir_ama_sertifikada_aranmaz(tip_sinif_dokumani):
    from malzeme_kabul.kural.karar_motoru import aranan_testler, uygulanan_testler

    assert "korozyon" in {t.id for t in uygulanan_testler(tip_sinif_dokumani, "I", "N")}
    assert "korozyon" not in {t.id for t in aranan_testler(tip_sinif_dokumani, "I", "N")}


def test_tip_bilinmiyorsa_iki_renk_testi_de_uygulanir(tip_sinif_dokumani):
    # uygulanir_mi None (bilinmiyor) döner; test dışarıda bırakılmaz.
    from malzeme_kabul.kural.karar_motoru import aranan_testler

    assert {"color_type_i", "color_type_ii"} <= {t.id for t in aranan_testler(tip_sinif_dokumani, None, None)}


@pytest.mark.parametrize("metin, beklenen", [
    ("MIL-PRF-23377 K, Type I, Class C2", ("MIL-PRF-23377", "K", "I", "C2")),
    ("MIL-PRF-23377K Type I", ("MIL-PRF-23377", "K", "I", None)),
    ("MIL-PRF-23377 Rev. K, Type I, Class C2", ("MIL-PRF-23377", "K", "I", "C2")),
    ("MIL-PRF-23377 Type I", ("MIL-PRF-23377", None, "I", None)),
])
def test_atfi_coz_revizyon_tip_sinif(metin, beklenen):
    from malzeme_kabul.kural.karar_motoru import atfi_coz

    a = atfi_coz(metin)
    assert (a.belge_no, a.revizyon, a.tip, a.sinif) == beklenen


@pytest.mark.xfail(strict=True, reason=(
    "Bilinen risk: 'MIL-PRF-23377 I' içindeki ayrı 'I' bugün revizyon 'I' sayılıyor; tip mi revizyon mu "
    "belirsizdir, revizyon sayılmamalı (None). Düzeltilince xfail kaldırılmalı."))
def test_atfi_coz_ayri_duran_romen_rakamini_revizyon_saymaz():
    from malzeme_kabul.kural.karar_motoru import atfi_coz

    assert atfi_coz("MIL-PRF-23377 I").revizyon is None


def test_atfi_coz_ayri_duran_romen_rakami_bugun_revizyon_sayiliyor():
    # Bugünkü davranışın kaydı: yukarıdaki xfail düzeltilince bu test de değiştirilmeli.
    from malzeme_kabul.kural.karar_motoru import atfi_coz

    a = atfi_coz("MIL-PRF-23377 I")
    assert (a.belge_no, a.revizyon, a.tip, a.sinif) == ("MIL-PRF-23377", "I", None, None)


# --- mimari ----------------------------------------------------------------------------------


def test_okuma_karsilastirma_kural_katmaninda_ve_cikarimi_ice_aktarmaz():
    from tests.test_katmanlar import PAKET, ice_aktarimlar

    dosya = PAKET / "kural" / "okuma_karsilastirma.py"
    assert dosya.is_file()
    ic = {m for m in ice_aktarimlar(dosya) if m.startswith("malzeme_kabul.")}
    assert not {m for m in ic if m.startswith(("malzeme_kabul.cikarim", "malzeme_kabul.hat", "malzeme_kabul.arayuz"))}, ic


# --- Nida kararı (koruma): iki okuma da sınır dışıysa uygun değil kalır, anlaşmazlık kaydedilir -------


@pytest.mark.parametrize("kural_hucre, model_okumasi, beklenen_anlasmazlik", [
    # VOC en çok 340 g/L. İki okuma da farklı ve ikisi de sınırın üstünde.
    ("400", ("401", "g/L"), {("voc_solvent_content", "deger", "400", "401")}),
    # Kural sınırın hemen üstünü (340.1), model daha yükseğini okur.
    ("340.1", ("341", "g/L"), {("voc_solvent_content", "deger", "340.1", "341")}),
    # Birim karışıklığı: model aynı satırdan lb/gal okur; 3.4 lb/gal ≈ 407 g/L, o da sınır dışı.
    ("400", ("3.4", "lb/gal"), {("voc_solvent_content", "deger", "400", "3.4"),
                                ("voc_solvent_content", "birim", "g/L", "lb/gal")}),
])
def test_iki_farkli_sinir_disi_okumada_sart_uygun_degil_parti_red_ve_anlasmazlik_karar_ve_kayitta(
        katalog, tmp_path, kural_hucre, model_okumasi, beklenen_anlasmazlik):
    from malzeme_kabul.hat.hibrit_hat import sertifika_hatti

    voc = ["VOC solvent content", "ASTM D3960", "340 g/L max", kural_hucre, "g/L"]
    tekrar = " ".join(model_okumasi)
    pdf = tekrar_testli_pdf(tmp_path / "voc.pdf", s028_satirlari(VOC=voc), "VOC solvent content", tekrar)
    model = SahteModel(model_sertifikasi(pdf, **{"VOC solvent content": model_okumasi}))
    d = DenetimKaydi(katalog.baglanti)
    katalog.parti_ekle(TEKRAR_LOT, "AST-001", ONAYLI_TEDARIKCILER[0], "K", "2025-12-10")

    karar, okuma_ = sertifika_hatti(katalog, "AST-001", pdf, mod="hibrit", istemci=model, lot_no=TEKRAR_LOT,
                                   defter=d, kullanici="gk1")

    assert okuma_.kanitsiz == []
    v = satir(karar, "voc_solvent_content")
    assert v.karar == "uygun_degil" and FARKLI_OKUDU in v.gerekce
    assert (karar.parti_karari, karar.parti_durumu) == ("red", "karantina")
    assert katalog.parti("AST-001", TEKRAR_LOT).durum == "karantina"

    hat_anl = {(a["test_id"], a["alan"], a["kural"], a["model"]) for a in karar.hat["anlasmazliklar"]}
    assert hat_anl == beklenen_anlasmazlik
    assert karar.hat["anlasmazlik_sayisi"] == len(beklenen_anlasmazlik)

    kayit = d.kayitlar("karar")[-1]
    assert kayit.lot_no == TEKRAR_LOT and kayit.veri["parti_karari"] == "red"
    kayit_anl = {(a["test_id"], a["alan"], a["kural"], a["model"]) for a in kayit.veri["hat"]["anlasmazliklar"]}
    assert kayit_anl == beklenen_anlasmazlik
    assert d.zinciri_dogrula().gecerli
