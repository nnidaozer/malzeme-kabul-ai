"""Yalnız dil modeli çıkarıcısının sayfa başına ara kaydı (Colab koparsa kaldığı yerden devam).

Gerçek model çalıştırılmaz; sayfa numarasına göre hazır yanıt dönen sahte bir
istemci kullanılır. Ara kayıtlar pytest'in geçici klasörüne yazılır.
"""

from __future__ import annotations

import json
import os
import re

import pytest

from malzeme_kabul.belge.pdf_okuyucu import Belge, Sayfa
from malzeme_kabul.sozlesme.sema import TestSarti
from deney.yalniz_dil_modeli import belgeden_cikar


def _test_json(id_="viskozite", madde="3.6.3", sayfa=7) -> dict:
    return {
        "id": id_,
        "test_adi": "Viscosity",
        "test_metodu": "ASTM D1200",
        "sinir": {
            "kriter_turu": "sayisal",
            "alt": 15,
            "ust": 30,
            "birim": "s",
            "orijinal_metin": "The viscosity shall be 15 to 30 seconds.",
        },
        "kaynak": {"belge_no": "MIL-PRF-23377", "revizyon": "K", "madde": madde, "sayfa": sayfa},
        "test_turleri": ["kabul", "yeterlilik"],
    }


class SahteIstemci:
    """Sayfa numarasına göre hazır yanıt döner; çağrılan sayfaları kaydeder."""

    def __init__(self, yanitlar: dict[int, str] | None = None):
        self.yanitlar = yanitlar or {}
        self.cagrilan_sayfalar: list[int] = []

    def sohbet(self, mesajlar, sema):
        icerik = mesajlar[1]["content"]
        for sayfa_no in range(1, 100):
            if f"sayfa {sayfa_no}." in icerik:
                self.cagrilan_sayfalar.append(sayfa_no)
                yanit = self.yanitlar.get(sayfa_no, json.dumps({"testler": []}))
                if isinstance(yanit, Exception):
                    raise yanit
                return yanit
        raise AssertionError("istemde sayfa numarası yok")


class CagrilmamaliIstemciDisinda3(SahteIstemci):
    """Sayfa 3'ün ara kaydı var: o sayfa modele gelirse hata verir, diğerlerine boş yanıt döner."""

    def __init__(self):
        super().__init__({3: AssertionError("ara kaydı olan sayfa 3 yeniden modele gönderildi")})


class CagrilmamaliIstemci:
    def sohbet(self, mesajlar, sema):
        raise AssertionError("ara kaydı olan sayfa yeniden modele gönderildi")


def _belge() -> Belge:
    return Belge(
        dosya="sahte.pdf",
        sayfalar=[
            Sayfa(1, "MIL-PRF-23377K\n1. SCOPE"),
            Sayfa(2, ""),  # boş sayfa: modele gönderilmez, ara kaydı da olmaz
            Sayfa(3, "3.6.3 Viscosity. The viscosity shall be 15 to 30 seconds."),
            Sayfa(4, "3.6.4 Density. TABLE II"),
        ],
    )


def _yanitlar() -> dict[int, str]:
    return {
        3: json.dumps({"testler": [_test_json()]}),
        4: json.dumps({"testler": [_test_json(id_="yogunluk", madde="3.6.4")]}),
    }


def _calistir(ara, istemci=None, **kw):
    return belgeden_cikar(_belge(), "MIL-PRF-23377", "K", istemci or SahteIstemci(_yanitlar()), ara_kayit=ara, **kw)


# --- Yazma -------------------------------------------------------------------------


def test_ara_kayit_her_islenen_sayfa_icin_dosya_yazar(tmp_path):
    ara = tmp_path / "ara"
    _calistir(ara)
    assert sorted(p.name for p in ara.iterdir()) == ["sayfa_001.json", "sayfa_003.json", "sayfa_004.json"]


def test_ara_kayit_dosyasi_sayfa_sure_testler_ve_hatalari_icerir(tmp_path):
    ara = tmp_path / "ara"
    _calistir(ara)
    veri = json.loads((ara / "sayfa_003.json").read_text(encoding="utf-8"))
    assert set(veri) == {"sayfa", "sure_s", "testler", "hatalar", "parmak_izi"}
    assert veri["sayfa"] == 3
    assert isinstance(veri["sure_s"], float) and veri["sure_s"] >= 0
    assert veri["hatalar"] == []
    assert [TestSarti.model_validate(t).id for t in veri["testler"]] == ["viskozite"]


def test_ara_kayit_sayfa_hatalarini_da_yazar(tmp_path):
    ara = tmp_path / "ara"
    _calistir(ara, SahteIstemci({3: "{bozuk"}))
    veri = json.loads((ara / "sayfa_003.json").read_text(encoding="utf-8"))
    assert veri["testler"] == [] and len(veri["hatalar"]) == 1


def test_ara_kayit_klasoru_yoksa_olusturulur(tmp_path):
    ara = tmp_path / "derin" / "ic" / "ara"
    _calistir(ara)
    assert (ara / "sayfa_003.json").is_file()


# --- Devam etme ----------------------------------------------------------------------


def test_ikinci_calistirmada_model_cagrilmaz_ve_sonuc_ayni(tmp_path):
    ara = tmp_path / "ara"
    ilk, ilk_rapor = _calistir(ara)
    ikinci, ikinci_rapor = _calistir(ara, CagrilmamaliIstemci())
    assert ikinci.model_dump() == ilk.model_dump()
    assert ilk_rapor.devam_edilen_sayfalar == []
    assert ikinci_rapor.devam_edilen_sayfalar == [1, 3, 4]
    assert ikinci_rapor.test_sayisi == ilk_rapor.test_sayisi == 2


def test_devam_edilen_sayfanin_suresi_ara_kayittan_okunur(tmp_path):
    ara = tmp_path / "ara"
    _calistir(ara)
    yol = ara / "sayfa_003.json"
    veri = json.loads(yol.read_text(encoding="utf-8"))
    veri["sure_s"] = 42.5
    yol.write_text(json.dumps(veri), encoding="utf-8")
    _, rapor = _calistir(ara, CagrilmamaliIstemci())
    assert {s.sayfa: s.sure_s for s in rapor.sayfalar}[3] == 42.5


def test_devam_edilen_sayfanin_hatalari_ara_kayittan_okunur(tmp_path):
    ara = tmp_path / "ara"
    _calistir(ara, SahteIstemci({3: "{bozuk"}))
    _, rapor = _calistir(ara, CagrilmamaliIstemci())
    hatali = {s.sayfa: s.hatalar for s in rapor.sayfalar if s.hatalar}
    assert set(hatali) == {3}


def test_yalniz_ara_kaydi_eksik_sayfalar_modele_gider(tmp_path):
    ara = tmp_path / "ara"
    ilk, _ = _calistir(ara)
    (ara / "sayfa_003.json").unlink()
    istemci = SahteIstemci(_yanitlar())
    ikinci, rapor = _calistir(ara, istemci)
    assert istemci.cagrilan_sayfalar == [3]
    assert rapor.devam_edilen_sayfalar == [1, 4]
    assert ikinci.model_dump() == ilk.model_dump()
    assert (ara / "sayfa_003.json").is_file()


def test_bozuk_ara_kayit_yok_sayilir_ve_sayfa_yeniden_calistirilir(tmp_path):
    ara = tmp_path / "ara"
    ilk, _ = _calistir(ara)
    (ara / "sayfa_003.json").write_text('{"sayfa": 3, "testl', encoding="utf-8")
    istemci = SahteIstemci(_yanitlar())
    ikinci, rapor = _calistir(ara, istemci)
    assert istemci.cagrilan_sayfalar == [3]
    assert 3 not in rapor.devam_edilen_sayfalar
    assert ikinci.model_dump() == ilk.model_dump()
    json.loads((ara / "sayfa_003.json").read_text(encoding="utf-8"))  # yeniden, sağlam yazıldı


def test_ara_kayittan_okunan_testin_kaynak_sayfasi_koddan_gelir(tmp_path):
    ara = tmp_path / "ara"
    ara.mkdir()
    (ara / "sayfa_003.json").write_text(json.dumps({
        "sayfa": 3, "sure_s": 1.0, "testler": [_test_json(sayfa=99)], "hatalar": [], "parmak_izi": "deneme",
    }), encoding="utf-8")
    dokuman, _ = _calistir(ara, CagrilmamaliIstemciDisinda3(), parmak_izi="deneme")
    assert {t.id: t.kaynak.sayfa for t in dokuman.testler}["viskozite"] == 3


def test_ara_kayittan_okunan_testlere_de_yon_dogrulamasi_uygulanir(tmp_path):
    kadmiyum = {
        "id": "lead_cadmium_content", "test_adi": "Lead and cadmium content",
        "sinir": {"kriter_turu": "sayisal", "alt": 0.001, "ust_dahil": False, "birim": "ppm",
                  "orijinal_metin": "≤ 1 ppm"},
        "kaynak": {"belge_no": "MIL-PRF-23377", "revizyon": "K", "madde": "3.4"}, "test_turleri": ["kabul"],
    }
    ara = tmp_path / "ara"
    ara.mkdir()
    (ara / "sayfa_004.json").write_text(json.dumps({
        "sayfa": 4, "sure_s": 2.0, "testler": [kadmiyum], "hatalar": [], "parmak_izi": "deneme",
    }), encoding="utf-8")
    dokuman, rapor = _calistir(ara, SahteIstemci({}), parmak_izi="deneme")
    testler = {t.id: t for t in dokuman.testler}
    assert testler["lead_cadmium_content"].sinir.yon == "belirsiz"
    assert [c["id"] for c in rapor.yon_celiskileri] == ["lead_cadmium_content"]
    assert 4 in rapor.devam_edilen_sayfalar


# --- Atomik yazım ------------------------------------------------------------------


def test_ara_kayit_atomik_yazilir_gecici_dosya_kalmaz(tmp_path, monkeypatch):
    degistirilenler: list[str] = []
    gercek_replace = os.replace

    def izle(kaynak, hedef, *args, **kwargs):
        degistirilenler.append(os.path.basename(os.fspath(hedef)))
        return gercek_replace(kaynak, hedef, *args, **kwargs)

    monkeypatch.setattr(os, "replace", izle)
    ara = tmp_path / "ara"
    _calistir(ara)
    # Her ara kayıt geçici dosyadan os.replace ile yerine konur.
    assert sorted(degistirilenler) == ["sayfa_001.json", "sayfa_003.json", "sayfa_004.json"]
    # Klasörde geçici dosya artığı yok.
    assert sorted(p.name for p in ara.iterdir()) == ["sayfa_001.json", "sayfa_003.json", "sayfa_004.json"]


def test_yarida_kalan_yazim_yarim_ara_kayit_birakmaz(tmp_path, monkeypatch):
    """Yerine koyma anında çökülürse sayfa dosyası hiç oluşmaz; sonraki çalıştırma sayfayı yeniden okur."""

    def coker(kaynak, hedef, *args, **kwargs):
        raise KeyboardInterrupt  # Colab oturumu koptu

    monkeypatch.setattr(os, "replace", coker)
    ara = tmp_path / "ara"
    with pytest.raises(KeyboardInterrupt):
        _calistir(ara)
    tamamlanan = [p.name for p in ara.iterdir() if re.fullmatch(r"sayfa_\d{3}\.json", p.name)] if ara.exists() else []
    assert tamamlanan == []


# --- ara_kayit verilmezse ----------------------------------------------------------


def test_ara_kayit_verilmezse_dosya_yazilmaz_ve_davranis_ayni(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    istemci = SahteIstemci(_yanitlar())
    dokuman, rapor = belgeden_cikar(_belge(), "MIL-PRF-23377", "K", istemci)
    assert list(tmp_path.iterdir()) == []
    assert istemci.cagrilan_sayfalar == [1, 3, 4]
    assert [t.id for t in dokuman.testler] == ["viskozite", "yogunluk"]
    assert rapor.devam_edilen_sayfalar == []


def test_rapor_sozlugu_devam_edilen_sayfalari_icerir(tmp_path):
    ara = tmp_path / "ara"
    _calistir(ara)
    _, rapor = _calistir(ara, CagrilmamaliIstemci())
    ozet = rapor.sozluk()
    assert ozet["devam_edilen_sayfalar"] == [1, 3, 4]
    json.dumps(ozet)


# --- İstek hatası (D1) -----------------------------------------------------------------


def test_istek_hatasinda_ara_kayit_yazilmaz(tmp_path):
    ara = tmp_path / "ara"
    _calistir(ara, SahteIstemci({**_yanitlar(), 3: TimeoutError("zaman aşımı")}))
    assert not (ara / "sayfa_003.json").exists()
    assert (ara / "sayfa_001.json").is_file() and (ara / "sayfa_004.json").is_file()


@pytest.mark.parametrize("hata", [TimeoutError("zaman aşımı"), ConnectionRefusedError("bağlantı yok"),
                                  OSError("ağ hatası")], ids=["zaman_asimi", "baglanti", "oserror"])
def test_istek_hatasi_alan_sayfa_sonraki_calistirmada_yeniden_istenir(tmp_path, hata):
    ara = tmp_path / "ara"
    _calistir(ara, SahteIstemci({**_yanitlar(), 3: hata}))
    istemci = SahteIstemci(_yanitlar())
    dokuman, rapor = _calistir(ara, istemci)
    assert istemci.cagrilan_sayfalar == [3]
    assert rapor.devam_edilen_sayfalar == [1, 4]
    assert [t.id for t in dokuman.testler] == ["viskozite", "yogunluk"]


def test_model_yanit_verdiyse_bozuk_json_da_ara_kayda_yazilir(tmp_path):
    """Yanıt geldi ama çözülemedi: bu bir istek hatası değildir, kayıt yazılır ve tekrar sorulmaz."""
    ara = tmp_path / "ara"
    _calistir(ara, SahteIstemci({3: "{bozuk"}))
    assert (ara / "sayfa_003.json").is_file()
    _, rapor = _calistir(ara, CagrilmamaliIstemci())
    assert 3 in rapor.devam_edilen_sayfalar


# --- Parmak izi (D2) -------------------------------------------------------------------


def test_ara_kayitta_parmak_izi_sha256_hex_olarak_yazilir(tmp_path):
    ara = tmp_path / "ara"
    _calistir(ara)
    izi = json.loads((ara / "sayfa_003.json").read_text(encoding="utf-8"))["parmak_izi"]
    assert re.fullmatch(r"[0-9a-f]{64}", izi)


def test_verilen_parmak_izi_dosyaya_yazilir(tmp_path):
    ara = tmp_path / "ara"
    _calistir(ara, parmak_izi="izi_a")
    assert json.loads((ara / "sayfa_003.json").read_text(encoding="utf-8"))["parmak_izi"] == "izi_a"


def test_ayni_parmak_iziyle_kayit_kullanilir(tmp_path):
    ara = tmp_path / "ara"
    _calistir(ara, parmak_izi="izi_a")
    _, rapor = _calistir(ara, CagrilmamaliIstemci(), parmak_izi="izi_a")
    assert rapor.devam_edilen_sayfalar == [1, 3, 4]


def test_parmak_izi_farkliysa_kayit_kullanilmaz_ve_uzerine_yazilir(tmp_path):
    ara = tmp_path / "ara"
    _calistir(ara, parmak_izi="izi_a")
    istemci = SahteIstemci(_yanitlar())
    _, rapor = _calistir(ara, istemci, parmak_izi="izi_b")
    assert istemci.cagrilan_sayfalar == [1, 3, 4]
    assert rapor.devam_edilen_sayfalar == []
    for ad in ("sayfa_001.json", "sayfa_003.json", "sayfa_004.json"):
        assert json.loads((ara / ad).read_text(encoding="utf-8"))["parmak_izi"] == "izi_b"


def test_parmak_izi_olmayan_eski_kayit_kullanilmaz(tmp_path):
    ara = tmp_path / "ara"
    _calistir(ara, parmak_izi="izi_a")
    yol = ara / "sayfa_003.json"
    veri = json.loads(yol.read_text(encoding="utf-8"))
    del veri["parmak_izi"]
    yol.write_text(json.dumps(veri), encoding="utf-8")
    istemci = SahteIstemci(_yanitlar())
    _, rapor = _calistir(ara, istemci, parmak_izi="izi_a")
    assert istemci.cagrilan_sayfalar == [3]
    assert json.loads(yol.read_text(encoding="utf-8"))["parmak_izi"] == "izi_a"


@pytest.mark.parametrize("degisen", [{"model": "qwen3:14b"}, {"arka_uc": "llamacpp"}, {"dusunme": None},
                                     {"baglam": 4096}], ids=["model", "arka_uc", "dusunme", "baglam"])
def test_parmak_izi_verilmezse_istemci_ayarlarindan_turetilir(tmp_path, monkeypatch, degisen):
    """Model, arka uç, düşünme ya da bağlam değişirse eski ara kayıtlar kullanılmaz."""
    from malzeme_kabul.cikarim.yerel_model import YerelModelIstemcisi

    sahte = SahteIstemci(_yanitlar())
    monkeypatch.setattr(YerelModelIstemcisi, "sohbet", lambda self, m, s: sahte.sohbet(m, s))
    ayar = {"model": "qwen3:8b", "arka_uc": "ollama", "dusunme": False, "baglam": 8192}
    ara = tmp_path / "ara"
    _calistir(ara, YerelModelIstemcisi(**ayar))
    _, ayni = _calistir(ara, YerelModelIstemcisi(**ayar))
    assert ayni.devam_edilen_sayfalar == [1, 3, 4]
    _, farkli = _calistir(ara, YerelModelIstemcisi(**{**ayar, **degisen}))
    assert farkli.devam_edilen_sayfalar == []
