"""Üç mod betiği (deney/uc_mod.py): kural, yalnız dil modeli ve hibrit çıktılar yan yana.

Gerçek model çalıştırılmaz: sahte istemci ve küçük sentetik PDF kullanılır.
Gold dosyaları pytest'in geçici klasöründe üretilir; data/gold/ altına hiçbir
şey yazılmaz (yazılmaya kalkışılırsa test hata verir).
"""

from __future__ import annotations

import builtins
import csv
import json
import os
import shutil
from pathlib import Path

import pytest

from pdf_uretici import pdf_yaz

from malzeme_kabul.cikarim.kural_cikarici import cikar
from malzeme_kabul.cikarim.yerel_model import YerelModelIstemcisi
from malzeme_kabul.sozlesme.sema import KabulDokumani

KOK = Path(__file__).resolve().parents[1]
GOLD = (KOK / "data" / "gold").resolve()
ETIKET = "MIL-PRF-23377K"

VISKOZITE_METNI = "The maximum viscosity shall be 40 seconds through a cup."
KOKU_METNI = "The odor shall not be objectionable."


def _uc_mod():
    from deney import uc_mod

    return uc_mod


# --- Sahte veri ------------------------------------------------------------------


def _pdf(klasor: Path, ad: str = f"{ETIKET}.pdf") -> Path:
    """Kural çıkarıcısının iki test (viscosity, lead_content) bulduğu, ayrıca 'odor' maddesi olan belge."""
    return pdf_yaz(klasor / ad, [
        {"metin": ["MIL-PRF-23377K", "3.6.3 Viscosity. The maximum viscosity shall be", "40 seconds through a cup.",
                   "3.6.9 Lead content. The lead content shall be not greater than 1 ppm.",
                   f"3.6.10 Odor. {KOKU_METNI}"]},
        {"metin": ["MIL-PRF-23377K", "TABLE II. Tests"],
         "tablo": [["Requirement", "Req para", "Test method", "Test para"],
                   ["Viscosity", "3.6.3", "4.6.3", "ASTM D1200"],
                   ["Lead content", "3.6.9", "4.6.9", "ASTM D3335"]]},
    ])


def _test_json(id_, ad, madde, sinir, sayfa=1) -> dict:
    return {
        "id": id_, "test_adi": ad, "sinir": sinir,
        "kaynak": {"belge_no": "MIL-PRF-23377", "revizyon": "K", "madde": madde, "sayfa": sayfa},
        "test_turleri": ["kabul"],
    }


def _sayfa1_yaniti() -> str:
    """Model: viskoziteyi kuraldan farklı (30 s) okur, kuralın bulmadığı 'odor'u ekler."""
    return json.dumps({"testler": [
        _test_json("viscosity", "Viscosity", "3.6.3",
                   {"kriter_turu": "sayisal", "ust": 30, "birim": "s", "orijinal_metin": VISKOZITE_METNI}),
        _test_json("odor", "Odor", "3.6.10", {"kriter_turu": "metinsel", "orijinal_metin": KOKU_METNI}),
    ]})


class SahteIstemci:
    # uc_mod ara kayıt parmak izini bu ayarlardan kurar; iki sahte istemci aynı izi vermeli.
    model, arka_uc, dusunme, baglam = "qwen3:8b", "ollama", False, 8192

    def __init__(self):
        self.cagrilar = 0

    def sohbet(self, mesajlar, sema):
        self.cagrilar += 1
        if "sayfa 1." in mesajlar[1]["content"]:
            return _sayfa1_yaniti()
        return json.dumps({"testler": []})


class CagrilmamaliIstemci:
    # uc_mod ara kayıt parmak izini bu ayarlardan kurar; iki sahte istemci aynı izi vermeli.
    model, arka_uc, dusunme, baglam = "qwen3:8b", "ollama", False, 8192

    def sohbet(self, mesajlar, sema):
        raise AssertionError("model çağrılmamalıydı")


@pytest.fixture(autouse=True)
def gold_yazma_yasak(monkeypatch):
    """data/gold/ altına yazma girişimi testi hata ile düşürür (koruma ağı)."""

    def altinda(yol) -> bool:
        try:
            Path(os.path.abspath(os.fspath(yol))).relative_to(GOLD)
            return True
        except (ValueError, TypeError):
            return False

    def koru(yol):
        if altinda(yol):
            raise AssertionError(f"data/gold altına yazma girişimi: {yol}")

    gercek_open, gercek_mkdir, gercek_path_open = builtins.open, Path.mkdir, Path.open
    gercek_os_open = os.open
    gercek_makedirs, gercek_replace = os.makedirs, os.replace

    def open_(dosya, mode="r", *a, **k):
        if isinstance(dosya, (str, os.PathLike)) and any(c in mode for c in "wax+"):
            koru(dosya)
        return gercek_open(dosya, mode, *a, **k)

    def path_open_(self, mode="r", *a, **k):
        if any(c in mode for c in "wax+"):
            koru(self)
        return gercek_path_open(self, mode, *a, **k)

    def os_open_(yol, flags, *a, **k):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            koru(yol)
        return gercek_os_open(yol, flags, *a, **k)

    def mkdir_(self, *a, **k):
        koru(self)
        return gercek_mkdir(self, *a, **k)

    def makedirs_(yol, *a, **k):
        koru(yol)
        return gercek_makedirs(yol, *a, **k)

    def replace_(kaynak, hedef, *a, **k):
        koru(hedef)
        return gercek_replace(kaynak, hedef, *a, **k)

    monkeypatch.setattr(builtins, "open", open_)
    monkeypatch.setattr(Path, "mkdir", mkdir_)
    monkeypatch.setattr(Path, "open", path_open_)
    monkeypatch.setattr(os, "open", os_open_)
    monkeypatch.setattr(os, "makedirs", makedirs_)
    monkeypatch.setattr(os, "replace", replace_)


@pytest.fixture
def pdf(tmp_path):
    klasor = tmp_path / "girdi"
    klasor.mkdir()
    return _pdf(klasor)


def _gold(tmp_path, pdf) -> Path:
    """Geçici gold: kural çıktısının kendisi (kural modunun F1'i 1 olmalı)."""
    yol = tmp_path / "goldlar" / f"{ETIKET}.json"
    yol.parent.mkdir()
    yol.write_text(cikar(pdf, "MIL-PRF-23377", "K").model_dump_json(indent=2), encoding="utf-8")
    return yol


# --- Çıktılar --------------------------------------------------------------------


def test_uc_kabul_dokumani_ve_rapor_yazilir(tmp_path, pdf):
    cikti = tmp_path / "cikti"
    _uc_mod().uc_mod_calistir(pdf, SahteIstemci(), cikti, model_adi="qwen3:8b")
    for mod in ("kural", "dil_modeli", "hibrit"):
        KabulDokumani.model_validate_json((cikti / f"{ETIKET}_{mod}.json").read_text(encoding="utf-8"))
    assert (cikti / f"{ETIKET}_uc_mod_rapor.json").is_file()


def test_her_mod_dokumani_beklenen_testleri_icerir(tmp_path, pdf):
    cikti = tmp_path / "cikti"
    _uc_mod().uc_mod_calistir(pdf, SahteIstemci(), cikti, model_adi="qwen3:8b")

    def idler(mod):
        d = KabulDokumani.model_validate_json((cikti / f"{ETIKET}_{mod}.json").read_text(encoding="utf-8"))
        return sorted(t.id for t in d.testler)

    assert idler("kural") == ["lead_content", "viscosity"]
    assert idler("dil_modeli") == ["odor", "viscosity"]
    assert idler("hibrit") == ["lead_content", "odor", "viscosity"]


def test_rapor_model_belge_mod_sayilari_ve_alt_raporlari_icerir(tmp_path, pdf):
    cikti = tmp_path / "cikti"
    donen = _uc_mod().uc_mod_calistir(pdf, SahteIstemci(), cikti, model_adi="qwen3:8b")
    rapor = json.loads((cikti / f"{ETIKET}_uc_mod_rapor.json").read_text(encoding="utf-8"))

    assert rapor["model"] == "qwen3:8b"
    assert rapor["belge"] == ETIKET
    assert rapor["sayfa_sayisi"] == 2
    modlar = rapor["modlar"]
    assert set(modlar) == {"kural", "dil_modeli", "hibrit"}
    assert {m: modlar[m]["test_sayisi"] for m in modlar} == {"kural": 2, "dil_modeli": 2, "hibrit": 3}
    for m in modlar:
        assert modlar[m]["sure_s"] >= 0
    # Hibrit süresi kural ve dil modeli sürelerini içerir.
    assert modlar["hibrit"]["sure_s"] >= modlar["kural"]["sure_s"] + modlar["dil_modeli"]["sure_s"] - 1e-3

    dm = rapor["dil_modeli_raporu"]
    assert {"sayfalar", "yon_celiskileri", "devam_edilen_sayfalar"} <= set(dm)
    assert [s["sayfa"] for s in dm["sayfalar"]] == [1, 2]
    assert rapor["hibrit_raporu"]["eklenen"] == ["odor"]
    assert donen == rapor  # gold yokken dönen sözlük rapordakiyle aynı


def test_rapor_anlasmazlik_sayilarini_ve_insan_incelemeli_sinirlari_icerir(tmp_path, pdf):
    """Viskozitede kural 40 s, model 30 s: bir anlaşmazlık; hibritte viskozite yon=belirsiz."""
    cikti = tmp_path / "cikti"
    _uc_mod().uc_mod_calistir(pdf, SahteIstemci(), cikti, model_adi="qwen3:8b")
    rapor = json.loads((cikti / f"{ETIKET}_uc_mod_rapor.json").read_text(encoding="utf-8"))
    assert rapor["anlasmazlik_sayisi"] == 1
    assert rapor["anlasmazlikli_test_sayisi"] == 1
    assert {m: rapor["modlar"][m]["insan_incelemeli_sinir"] for m in rapor["modlar"]} == {
        "kural": 0, "dil_modeli": 0, "hibrit": 1,
    }
    hibrit = KabulDokumani.model_validate_json((cikti / f"{ETIKET}_hibrit.json").read_text(encoding="utf-8"))
    viskozite = {t.id: t for t in hibrit.testler}["viscosity"]
    assert (viskozite.sinir.ust, viskozite.sinir.yon) == (40, "belirsiz")


def test_ara_kayit_cikti_altinda_tutulur_ve_ikinci_calistirmada_model_cagrilmaz(tmp_path, pdf):
    cikti = tmp_path / "cikti"
    _uc_mod().uc_mod_calistir(pdf, SahteIstemci(), cikti, model_adi="qwen3:8b")
    assert (cikti / f"{ETIKET}_ara" / "sayfa_001.json").is_file()

    rapor = _uc_mod().uc_mod_calistir(pdf, CagrilmamaliIstemci(), cikti, model_adi="qwen3:8b")
    assert rapor["dil_modeli_raporu"]["devam_edilen_sayfalar"] == [1, 2]
    assert rapor["modlar"]["hibrit"]["test_sayisi"] == 3


def test_belge_no_ve_revizyon_verilirse_dosya_adindan_okunmaz(tmp_path):
    klasor = tmp_path / "girdi"
    klasor.mkdir()
    yol = _pdf(klasor, ad="adsiz_belge.pdf")
    cikti = tmp_path / "cikti"
    _uc_mod().uc_mod_calistir(yol, SahteIstemci(), cikti, model_adi="qwen3:8b",
                              belge_no="MIL-PRF-23377", revizyon="K")
    assert (cikti / f"{ETIKET}_hibrit.json").is_file()


# --- Ölçüm -----------------------------------------------------------------------


def test_gold_verilirse_her_mod_her_golde_karsi_olculur(tmp_path, pdf):
    cikti = tmp_path / "cikti"
    gold = _gold(tmp_path, pdf)
    donen = _uc_mod().uc_mod_calistir(pdf, SahteIstemci(), cikti, model_adi="qwen3:8b",
                                      goldlar={"gold_taslak": gold, "gold_codex": gold})
    with open(cikti / f"{ETIKET}_uc_mod_olcum.csv", encoding="utf-8", newline="") as f:
        okuyucu = csv.DictReader(f)
        assert okuyucu.fieldnames == ["gold", "mod", "alan", "dp", "yp", "yn", "precision", "recall", "f1"]
        satirlar = list(okuyucu)
    assert {(s["gold"], s["mod"]) for s in satirlar} == {
        (g, m) for g in ("gold_taslak", "gold_codex") for m in ("kural", "dil_modeli", "hibrit")
    }
    genel = [s for s in satirlar if s["alan"].startswith("GENEL")]
    assert {(s["gold"], s["mod"]) for s in genel} == {(s["gold"], s["mod"]) for s in satirlar}

    olcum = donen["olcum"]
    assert set(olcum) == {"gold_taslak", "gold_codex"}
    assert set(olcum["gold_taslak"]) == {"kural", "dil_modeli", "hibrit"}
    # Gold kural çıktısının kendisi: kural tam isabet, dil modeli değil.
    assert olcum["gold_taslak"]["kural"] == pytest.approx(1.0)
    assert olcum["gold_taslak"]["dil_modeli"] < 1.0


def test_olcum_hizali_yapilir_benzer_adli_test_eslesir(tmp_path, pdf):
    """Gold'daki kimlik farklı ama ad aynıysa (benzerlik eşleşmesi) kural yine tam isabet alır."""
    gold = KabulDokumani.model_validate_json(_gold(tmp_path, pdf).read_text(encoding="utf-8"))
    veri = gold.model_dump(mode="json")
    for t in veri["testler"]:
        t["id"] = t["id"] + "_gold"
    yol = tmp_path / "goldlar" / "yeniden_adli.json"
    yol.write_text(json.dumps(veri), encoding="utf-8")
    donen = _uc_mod().uc_mod_calistir(pdf, SahteIstemci(), tmp_path / "cikti", model_adi="qwen3:8b",
                                      goldlar={"gold_taslak": yol})
    assert donen["olcum"]["gold_taslak"]["kural"] == pytest.approx(1.0)


def test_gold_dosyasi_yalniz_okunur(tmp_path, pdf):
    gold = _gold(tmp_path, pdf)
    once = (gold.read_bytes(), gold.stat().st_mtime_ns)
    _uc_mod().uc_mod_calistir(pdf, SahteIstemci(), tmp_path / "cikti", model_adi="qwen3:8b",
                              goldlar={"gold_taslak": gold})
    assert (gold.read_bytes(), gold.stat().st_mtime_ns) == once
    assert sorted(p.name for p in gold.parent.iterdir()) == [gold.name]


def test_gold_verilmezse_olcum_csv_yazilmaz(tmp_path, pdf):
    cikti = tmp_path / "cikti"
    donen = _uc_mod().uc_mod_calistir(pdf, SahteIstemci(), cikti, model_adi="qwen3:8b")
    assert not (cikti / f"{ETIKET}_uc_mod_olcum.csv").exists()
    assert "olcum" not in donen


# --- Kilitler --------------------------------------------------------------------


def test_test_kumesindeki_belge_reddedilir_model_cagrilmaz(tmp_path):
    from deney.bolunme import TestKumesiKilitli

    klasor = tmp_path / "girdi"
    klasor.mkdir()
    kilitli = _pdf(klasor, ad="MIL-PRF-87937E.pdf")
    cikti = tmp_path / "cikti"
    with pytest.raises(TestKumesiKilitli):
        _uc_mod().uc_mod_calistir(kilitli, CagrilmamaliIstemci(), cikti, model_adi="qwen3:8b")
    assert not cikti.exists() or list(cikti.iterdir()) == []


def test_data_gold_altina_cikti_reddedilir(tmp_path, pdf):
    hedef = GOLD / "uc_mod_deneme"
    with pytest.raises((ValueError, PermissionError)):
        _uc_mod().uc_mod_calistir(pdf, CagrilmamaliIstemci(), hedef, model_adi="qwen3:8b")
    assert not hedef.exists()


# --- Komut satırı ----------------------------------------------------------------


@pytest.fixture
def sahte_yerel_model(monkeypatch):
    """YerelModelIstemcisi ağa çıkmaz; kurulduğu ayarlar kaydedilir."""
    kurulanlar: list[YerelModelIstemcisi] = []

    def sohbet(self, mesajlar, sema):
        if self not in kurulanlar:
            kurulanlar.append(self)
        return SahteIstemci().sohbet(mesajlar, sema)

    monkeypatch.setattr(YerelModelIstemcisi, "sohbet", sohbet)
    return kurulanlar


def test_main_basarili_calisinca_0_doner_ve_cikti_yazar(tmp_path, pdf, sahte_yerel_model):
    cikti = tmp_path / "cikti"
    kod = _uc_mod().main([str(pdf), "--model", "qwen3:8b", "--dusunme-kapali", "--baglam", "8192",
                          "--arka-uc", "ollama", "--cikti", str(cikti), "--gold-yok"])
    assert kod == 0
    assert (cikti / f"{ETIKET}_hibrit.json").is_file()
    assert not (cikti / f"{ETIKET}_uc_mod_olcum.csv").exists()
    istemci = sahte_yerel_model[0]
    assert istemci.model == "qwen3:8b" and istemci.dusunme is False and istemci.baglam == 8192
    assert istemci.adres.startswith("http://localhost")


def test_main_test_kumesindeki_belge_icin_2_doner(tmp_path, sahte_yerel_model):
    klasor = tmp_path / "girdi"
    klasor.mkdir()
    kilitli = _pdf(klasor, ad="MIL-PRF-87937E.pdf")
    kod = _uc_mod().main([str(kilitli), "--model", "qwen3:8b", "--cikti", str(tmp_path / "cikti"), "--gold-yok"])
    assert kod == 2
    assert sahte_yerel_model == []


def test_main_data_gold_altina_cikti_icin_2_doner(pdf, sahte_yerel_model):
    hedef = GOLD / "uc_mod_deneme"
    kod = _uc_mod().main([str(pdf), "--model", "qwen3:8b", "--cikti", str(hedef), "--gold-yok"])
    assert kod == 2
    assert not hedef.exists()
    assert sahte_yerel_model == []


# --- Süre (D3) ---------------------------------------------------------------------


def test_devam_eden_calismada_dil_modeli_suresi_sayfa_surelerinin_toplamidir(tmp_path, pdf):
    cikti = tmp_path / "cikti"
    _uc_mod().uc_mod_calistir(pdf, SahteIstemci(), cikti, model_adi="qwen3:8b")
    yol = cikti / f"{ETIKET}_ara" / "sayfa_001.json"
    veri = json.loads(yol.read_text(encoding="utf-8"))
    veri["sure_s"] = 100.0  # Colab'da önceki oturumda ölçülen süre
    yol.write_text(json.dumps(veri), encoding="utf-8")

    rapor = _uc_mod().uc_mod_calistir(pdf, CagrilmamaliIstemci(), cikti, model_adi="qwen3:8b")
    sayfa_sureleri = [s["sure_s"] for s in rapor["dil_modeli_raporu"]["sayfalar"]]
    assert 100.0 in sayfa_sureleri
    modlar = rapor["modlar"]
    assert modlar["dil_modeli"]["sure_s"] == pytest.approx(sum(sayfa_sureleri), abs=1e-3)
    assert modlar["hibrit"]["sure_s"] >= modlar["kural"]["sure_s"] + modlar["dil_modeli"]["sure_s"] - 1e-3


# --- Gold doğrulama ve varsayılan goldlar (D6) -------------------------------------------


@pytest.mark.parametrize("icerik", ["{yarim", json.dumps({"standart": {"belge_no": "X"}})],
                         ids=["json_bozuk", "sema_disi"])
def test_gecersiz_gold_model_cagrilmadan_reddedilir(tmp_path, pdf, icerik):
    bozuk = tmp_path / "bozuk_gold.json"
    bozuk.write_text(icerik, encoding="utf-8")
    with pytest.raises(ValueError):
        _uc_mod().uc_mod_calistir(pdf, CagrilmamaliIstemci(), tmp_path / "cikti", model_adi="qwen3:8b",
                                  goldlar={"gold_taslak": bozuk})
    assert not (tmp_path / "cikti" / f"{ETIKET}_ara").exists()


def test_main_gecersiz_gold_icin_2_doner_model_cagrilmaz(tmp_path, pdf, sahte_yerel_model, monkeypatch):
    uc_mod = _uc_mod()
    bozuk = tmp_path / "bozuk_gold.json"
    bozuk.write_text("{yarim", encoding="utf-8")
    monkeypatch.setattr(uc_mod, "varsayilan_goldlar", lambda etiket, kok=None: {"gold_taslak": bozuk})
    kod = uc_mod.main([str(pdf), "--model", "qwen3:8b", "--cikti", str(tmp_path / "cikti")])
    assert kod == 2
    assert sahte_yerel_model == []


def _gold_klasoru(kok: Path, ad: str) -> Path:
    yol = kok / "data" / ad / f"{ETIKET}.json"
    yol.parent.mkdir(parents=True)
    yol.write_text("{}", encoding="utf-8")
    return yol


def test_varsayilan_goldlar_ikisi_de_varsa_ikisini_doner(tmp_path):
    taslak, codex = _gold_klasoru(tmp_path, "gold_taslak"), _gold_klasoru(tmp_path, "gold_codex")
    assert _uc_mod().varsayilan_goldlar(ETIKET, kok=tmp_path) == {"gold_taslak": taslak, "gold_codex": codex}


def test_varsayilan_goldlar_yalniz_var_olanlari_doner(tmp_path):
    taslak = _gold_klasoru(tmp_path, "gold_taslak")
    assert _uc_mod().varsayilan_goldlar(ETIKET, kok=tmp_path) == {"gold_taslak": taslak}


def test_varsayilan_goldlar_hic_yoksa_bos_doner(tmp_path):
    assert _uc_mod().varsayilan_goldlar(ETIKET, kok=tmp_path) == {}


def test_varsayilan_goldlar_data_gold_klasorunu_kullanmaz(tmp_path):
    _gold_klasoru(tmp_path, "gold")
    assert _uc_mod().varsayilan_goldlar(ETIKET, kok=tmp_path) == {}


# --- OCR (docs/ocr.md, tasarım 4) ----------------------------------------------------


def _ocr_bolunme(tmp_path) -> Path:
    """MIL-PRF-23377K geliştirmede ve taranmış (ocr_gerekli) sayılıyor."""
    yol = tmp_path / "bolunme_ocr.yaml"
    yol.write_text("gelistirme:\n  - MIL-PRF-23377K\nocr_gerekli:\n  - MIL-PRF-23377K\n", encoding="utf-8")
    return yol


def _taranmis_sayfali_pdf(klasor: Path) -> Path:
    """_pdf'in iki sayfası ve ardından yalnız resimden oluşan (taranmış) 3. sayfa."""
    return pdf_yaz(klasor / f"{ETIKET}.pdf", [
        {"metin": ["MIL-PRF-23377K", "3.6.3 Viscosity. The maximum viscosity shall be", "40 seconds through a cup.",
                   "3.6.9 Lead content. The lead content shall be not greater than 1 ppm.",
                   f"3.6.10 Odor. {KOKU_METNI}"]},
        {"metin": ["MIL-PRF-23377K", "TABLE II. Tests"],
         "tablo": [["Requirement", "Req para", "Test method", "Test para"],
                   ["Viscosity", "3.6.3", "4.6.3", "ASTM D1200"],
                   ["Lead content", "3.6.9", "4.6.9", "ASTM D3335"]]},
        {"gorsel": True},
    ])


class SahteOcrMotoru:
    def __init__(self):
        self.sayfalar: list[int] = []

    def sayfa_oku(self, pdf_yolu, sayfa_no):
        from malzeme_kabul.belge.ocr import OcrKelime, OcrSonucu

        self.sayfalar.append(sayfa_no)
        return OcrSonucu("MIL-PRF-23377K\n3.6.11 Color. The color shall be white.",
                         (OcrKelime("Color.", 90.0), OcrKelime("white.", 80.0)))


@pytest.fixture
def taranmis_pdf(tmp_path):
    klasor = tmp_path / "girdi"
    klasor.mkdir()
    return _taranmis_sayfali_pdf(klasor)


def test_ocr_verilince_taranmis_gelistirme_belgesi_reddedilmez(tmp_path, taranmis_pdf):
    motor = SahteOcrMotoru()
    cikti = tmp_path / "cikti"
    rapor = _uc_mod().uc_mod_calistir(taranmis_pdf, SahteIstemci(), cikti, model_adi="qwen3:8b",
                                      bolunme=_ocr_bolunme(tmp_path), ocr=motor)
    assert (cikti / f"{ETIKET}_hibrit.json").is_file()
    assert motor.sayfalar and set(motor.sayfalar) == {3}  # yalnız taranmış sayfa OCR'a gider
    assert rapor["sayfa_sayisi"] == 3


def test_ocr_verilmezse_taranmis_belge_model_cagrilmadan_reddedilir(tmp_path, taranmis_pdf):
    from deney.bolunme import OcrGerekli

    cikti = tmp_path / "cikti"
    with pytest.raises(OcrGerekli):
        _uc_mod().uc_mod_calistir(taranmis_pdf, CagrilmamaliIstemci(), cikti, model_adi="qwen3:8b",
                                  bolunme=_ocr_bolunme(tmp_path))
    assert not cikti.exists() or list(cikti.iterdir()) == []


def test_ocr_raporu_ocr_bayragi_ve_ocr_sayfalarini_icerir(tmp_path, taranmis_pdf):
    cikti = tmp_path / "cikti"
    donen = _uc_mod().uc_mod_calistir(taranmis_pdf, SahteIstemci(), cikti, model_adi="qwen3:8b",
                                      bolunme=_ocr_bolunme(tmp_path), ocr=SahteOcrMotoru())
    rapor = json.loads((cikti / f"{ETIKET}_uc_mod_rapor.json").read_text(encoding="utf-8"))
    assert rapor["ocr"] is True
    assert rapor["ocr_sayfalari"] == [3]
    assert donen == rapor


def test_ocr_verilse_de_test_kumesindeki_belge_reddedilir(tmp_path):
    from deney.bolunme import TestKumesiKilitli

    klasor = tmp_path / "girdi"
    klasor.mkdir()
    kilitli = _pdf(klasor, ad="MIL-PRF-87937E.pdf")
    motor = SahteOcrMotoru()
    with pytest.raises(TestKumesiKilitli):
        _uc_mod().uc_mod_calistir(kilitli, CagrilmamaliIstemci(), tmp_path / "cikti", model_adi="qwen3:8b",
                                  ocr=motor)
    assert motor.sayfalar == []


def test_main_ocr_bayragi_tesseract_yoksa_2_doner_ve_mesaj_yazar(tmp_path, taranmis_pdf, sahte_yerel_model,
                                                                  monkeypatch, capsys):
    bos = tmp_path / "bos_path"
    bos.mkdir()
    monkeypatch.setenv("PATH", str(bos))  # tesseract bulunamaz
    kod = _uc_mod().main([str(taranmis_pdf), "--model", "qwen3:8b", "--cikti", str(tmp_path / "cikti"),
                          "--gold-yok", "--bolunme", str(_ocr_bolunme(tmp_path)), "--ocr"])
    assert kod == 2
    assert "tesseract" in capsys.readouterr().err.lower()
    assert sahte_yerel_model == []


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract kurulu değil")
def test_main_ocr_bayragiyla_taranmis_belgeyi_isler(tmp_path, taranmis_pdf, sahte_yerel_model):
    cikti = tmp_path / "cikti"
    kod = _uc_mod().main([str(taranmis_pdf), "--model", "qwen3:8b", "--cikti", str(cikti),
                          "--gold-yok", "--bolunme", str(_ocr_bolunme(tmp_path)), "--ocr"])
    assert kod == 0
    rapor = json.loads((cikti / f"{ETIKET}_uc_mod_rapor.json").read_text(encoding="utf-8"))
    assert rapor["ocr"] is True and rapor["ocr_sayfalari"] == [3]


# --- Etiket taklidi ve OCR hatası (gözden geçirme düzeltmeleri) ---------------------------

TAKLIT_BOLUNMESI = """test_kumesi_acik: false
test_durumu: secildi
tohum: 1

gelistirme:
  - MIL-PRF-11111A
  - MIL-PRF-44444D

yeni_standartlar:
  - MIL-PRF-33333C

test:
  - MIL-PRF-33333C
"""


@pytest.fixture
def taklit_bolunmesi(tmp_path) -> Path:
    yol = tmp_path / "bolunme_taklit.yaml"
    yol.write_text(TAKLIT_BOLUNMESI, encoding="utf-8")
    return yol


def _adli_pdf(tmp_path, ad: str) -> Path:
    klasor = tmp_path / "girdi"
    klasor.mkdir(exist_ok=True)
    return _pdf(klasor, ad=ad)


def test_verilen_etiket_test_kumesindeki_dosya_adini_gizleyemez(tmp_path, taklit_bolunmesi):
    from deney.bolunme import TestKumesiKilitli

    pdf = _adli_pdf(tmp_path, "MIL-PRF-33333C.pdf")  # dosya adı test kümesinde
    motor = SahteOcrMotoru()
    cikti = tmp_path / "cikti"
    with pytest.raises(TestKumesiKilitli):
        _uc_mod().uc_mod_calistir(pdf, CagrilmamaliIstemci(), cikti, model_adi="qwen3:8b",
                                  belge_no="MIL-PRF-11111", revizyon="A", bolunme=taklit_bolunmesi, ocr=motor)
    assert motor.sayfalar == []
    assert not cikti.exists() or list(cikti.iterdir()) == []


def test_dosya_adi_etiketi_verilen_etiketten_farkliysa_reddedilir(tmp_path, taklit_bolunmesi):
    pdf = _adli_pdf(tmp_path, "MIL-PRF-44444D.pdf")  # ikisi de geliştirmede ama farklı
    cikti = tmp_path / "cikti"
    with pytest.raises(ValueError) as hata:
        _uc_mod().uc_mod_calistir(pdf, CagrilmamaliIstemci(), cikti, model_adi="qwen3:8b",
                                  belge_no="MIL-PRF-11111", revizyon="A", bolunme=taklit_bolunmesi)
    assert "MIL-PRF-44444D" in str(hata.value) and "MIL-PRF-11111A" in str(hata.value)
    assert not cikti.exists() or list(cikti.iterdir()) == []


def test_dosya_adi_etiketi_verilenle_ayniysa_kabul_edilir(tmp_path, taklit_bolunmesi):
    pdf = _adli_pdf(tmp_path, "MIL-PRF-11111A.pdf")
    rapor = _uc_mod().uc_mod_calistir(pdf, SahteIstemci(), tmp_path / "cikti", model_adi="qwen3:8b",
                                      belge_no="MIL-PRF-11111", revizyon="A", bolunme=taklit_bolunmesi)
    assert rapor["belge"] == "MIL-PRF-11111A"


def test_main_verilen_etiketle_test_kumesindeki_dosya_icin_2_doner(tmp_path, taklit_bolunmesi, sahte_yerel_model):
    pdf = _adli_pdf(tmp_path, "MIL-PRF-33333C.pdf")
    kod = _uc_mod().main([str(pdf), "--model", "qwen3:8b", "--belge-no", "MIL-PRF-11111", "--revizyon", "A",
                          "--cikti", str(tmp_path / "cikti"), "--gold-yok", "--bolunme", str(taklit_bolunmesi)])
    assert kod == 2
    assert sahte_yerel_model == []


def test_main_etiket_uyusmazliginda_2_doner_ve_iki_etiketi_yazar(tmp_path, taklit_bolunmesi, sahte_yerel_model,
                                                                 capsys):
    pdf = _adli_pdf(tmp_path, "MIL-PRF-44444D.pdf")
    kod = _uc_mod().main([str(pdf), "--model", "qwen3:8b", "--belge-no", "MIL-PRF-11111", "--revizyon", "A",
                          "--cikti", str(tmp_path / "cikti"), "--gold-yok", "--bolunme", str(taklit_bolunmesi)])
    assert kod == 2
    hata = capsys.readouterr().err
    assert "MIL-PRF-44444D" in hata and "MIL-PRF-11111A" in hata
    assert sahte_yerel_model == []


class _BozukTesseract:
    """Her sayfada OcrKullanilamaz atan motor (ör. tesseract dil paketi yok)."""

    def __init__(self, *a, **k):
        pass

    def sayfa_oku(self, pdf_yolu, sayfa_no):
        from malzeme_kabul.belge.ocr import OcrKullanilamaz

        raise OcrKullanilamaz("tesseract hata koduyla bitti (1): Failed loading language 'eng'")


def test_main_ocr_motoru_hata_verirse_2_doner_yigin_izi_vermez(tmp_path, taranmis_pdf, sahte_yerel_model,
                                                               monkeypatch, capsys):
    uc_mod = _uc_mod()
    monkeypatch.setattr(uc_mod, "TesseractMotoru", _BozukTesseract)
    monkeypatch.setattr(uc_mod, "tesseract_var_mi", lambda *a, **k: True)
    kod = uc_mod.main([str(taranmis_pdf), "--model", "qwen3:8b", "--cikti", str(tmp_path / "cikti"),
                       "--gold-yok", "--bolunme", str(_ocr_bolunme(tmp_path)), "--ocr"])
    assert kod == 2
    hata = capsys.readouterr().err
    assert "Failed loading language" in hata
    assert "Traceback" not in hata
    assert sahte_yerel_model == []


# --- İçerik kilidi, kilitli klasör ve ham klasör (ikinci gözden geçirme turu) -------------


@pytest.fixture
def ham_klasor(tmp_path) -> Path:
    """Geçici ham klasör: test kümesindeki MIL-PRF-33333C'nin sahte PDF'i."""
    kok = tmp_path / "ham"
    kok.mkdir()
    pdf_yaz(kok / "MIL-PRF-33333C.pdf", [{"metin": ["3.1 Test kumesi belgesi otuz uc bin uc yuz otuz uc."]}])
    return kok


def _adsiz_kopya(tmp_path, ham_klasor) -> Path:
    klasor = tmp_path / "girdi"
    klasor.mkdir(exist_ok=True)
    hedef = klasor / "x.pdf"
    shutil.copyfile(ham_klasor / "MIL-PRF-33333C.pdf", hedef)
    return hedef


def test_test_belgesinin_adsiz_kopyasi_verilen_etiketle_reddedilir(tmp_path, taklit_bolunmesi, ham_klasor):
    from deney.bolunme import TestKumesiKilitli

    kopya = _adsiz_kopya(tmp_path, ham_klasor)
    motor = SahteOcrMotoru()
    cikti = tmp_path / "cikti"
    with pytest.raises(TestKumesiKilitli):
        _uc_mod().uc_mod_calistir(kopya, CagrilmamaliIstemci(), cikti, model_adi="qwen3:8b",
                                  belge_no="MIL-PRF-11111", revizyon="A", bolunme=taklit_bolunmesi,
                                  ocr=motor, ham_klasor=ham_klasor)
    assert motor.sayfalar == []
    assert not cikti.exists() or list(cikti.iterdir()) == []


def test_adsiz_yeni_belge_verilen_etiketle_islenir(tmp_path, taklit_bolunmesi, ham_klasor):
    klasor = tmp_path / "girdi"
    klasor.mkdir()
    yol = _pdf(klasor, ad="x.pdf")  # içeriği test kümesinde yok
    rapor = _uc_mod().uc_mod_calistir(yol, SahteIstemci(), tmp_path / "cikti", model_adi="qwen3:8b",
                                      belge_no="MIL-PRF-11111", revizyon="A", bolunme=taklit_bolunmesi,
                                      ham_klasor=ham_klasor)
    assert rapor["belge"] == "MIL-PRF-11111A"


def test_kilitli_klasordeki_belge_reddedilir_model_cagrilmaz(tmp_path):
    from deney.bolunme import TestKumesiKilitli

    bolunme = tmp_path / "bolunme_kilitli.yaml"
    bolunme.write_text(f"gelistirme:\n  - {ETIKET}\nkilitli_klasorler:\n  - kilitli_klasor\n", encoding="utf-8")
    klasor = tmp_path / "kilitli_klasor"
    klasor.mkdir()
    yol = _pdf(klasor)  # adı geliştirme kümesinde, klasör kilitli
    motor = SahteOcrMotoru()
    cikti = tmp_path / "cikti"
    with pytest.raises(TestKumesiKilitli):
        _uc_mod().uc_mod_calistir(yol, CagrilmamaliIstemci(), cikti, model_adi="qwen3:8b", bolunme=bolunme,
                                  ocr=motor)
    assert motor.sayfalar == []
    assert not cikti.exists() or list(cikti.iterdir()) == []


def test_main_ham_klasor_secenegiyle_adsiz_kopya_icin_2_doner(tmp_path, taklit_bolunmesi, ham_klasor,
                                                             sahte_yerel_model):
    kopya = _adsiz_kopya(tmp_path, ham_klasor)
    cikti = tmp_path / "cikti"
    kod = _uc_mod().main([str(kopya), "--model", "qwen3:8b", "--belge-no", "MIL-PRF-11111", "--revizyon", "A",
                          "--cikti", str(cikti), "--gold-yok", "--bolunme", str(taklit_bolunmesi),
                          "--ham-klasor", str(ham_klasor)])
    assert kod == 2
    assert sahte_yerel_model == []
    assert not cikti.exists() or list(cikti.iterdir()) == []
