"""Belgenin kullanılabilirlik denetimi (deney/bolunme.py, ikinci gözden geçirme turu).

- dosya_etiketi: dosya adından etiket.
- yol_kilitli_mi: göreli yol, sembolik bağ ve harf farkı kilidi atlatamaz.
- icerik_kilitli_mi: test belgesinin yeniden adlandırılmış / kopyalanmış /
  bağlanmış hâli içerik özetiyle (SHA-256) yakalanır.
- belgeyi_denetle: tek giriş noktası; sıra yol kilidi -> içerik kilidi ->
  dosya adı etiketi -> verilen etiket -> uyuşma.
- gold_altinda_mi: data/gold koruması tek yerde.

Test belgeleri tmp_path'te üretilen sahte PDF'lerdir; gerçek test kümesi
dosyaları kopyalanmaz. Yalnız bir test depodaki data/raw ile çalışır (içerik
çıkarılmaz; denetim dosyaları yalnız özet için okur).
"""

from __future__ import annotations

import ast
import os
import shutil
from pathlib import Path

import pytest

from pdf_uretici import pdf_yaz

from deney.bolunme import (
    VARSAYILAN_HAM,
    Bolunme,
    OcrGerekli,
    TestKumesiKilitli,
    bolunme_oku,
    dosya_etiketi,
    gold_altinda_mi,
)

KOK = Path(__file__).resolve().parents[1]
GOLD = KOK / "data" / "gold"
sembolik_bag_yok = pytest.mark.skipif(os.name == "nt", reason="sembolik bağ için yönetici izni gerekebilir")


def _bolunme(**ek) -> Bolunme:
    alanlar = dict(
        gelistirme=["MIL-PRF-11111A", "MIL-PRF-44444D", "MIL-S-22222B"],
        yeni_standartlar=["MIL-PRF-33333C", "MIL-PRF-55555E"],
        test=["MIL-PRF-33333C", "MIL-PRF-55555E"],
        test_durumu="secildi",
        kilitli_klasorler=["gercek_coc_havacilik"],
        ocr_gerekli=["MIL-S-22222B"],
    )
    alanlar.update(ek)
    return Bolunme(**alanlar)


@pytest.fixture
def ham(tmp_path) -> Path:
    """Geçici ham klasör: test belgeleri (biri alt klasörde, ekli adla), kilitli klasör ve geliştirme belgesi."""
    kok = tmp_path / "ham"
    pdf_yaz(_klasor(kok) / "MIL-PRF-33333C.pdf", [{"metin": ["3.1 Test kumesi belgesi otuz uc bin uc yuz otuz uc."]}])
    pdf_yaz(_klasor(kok / "alt") / "MIL-PRF-55555E_Amendment1.pdf",
            [{"metin": ["3.2 Ikinci test belgesi elli bes bin bes yuz elli bes."]}])
    pdf_yaz(_klasor(kok / "gercek_coc_havacilik") / "tedarikci_CoC.pdf",
            [{"metin": ["Certificate of conformance lot 778899 kilitli klasor."]}])
    pdf_yaz(_klasor(kok) / "MIL-PRF-11111A.pdf", [{"metin": ["3.3 Gelistirme belgesi on bir bin yuz on bir."]}])
    pdf_yaz(_klasor(kok) / "MIL-S-22222B.pdf", [{"gorsel": True}])
    return kok


def _klasor(yol: Path) -> Path:
    yol.mkdir(parents=True, exist_ok=True)
    return yol


def _kopya(kaynak: Path, hedef: Path) -> Path:
    _klasor(hedef.parent)
    shutil.copyfile(kaynak, hedef)
    return hedef


def _yeni_pdf(yol: Path, metin: str = "Hic bir yerde gecmeyen yepyeni bir belge metni 424242.") -> Path:
    _klasor(yol.parent)
    return pdf_yaz(yol, [{"metin": [metin]}])


# --- A. dosya_etiketi ------------------------------------------------------------------


@pytest.mark.parametrize(
    "yol, beklenen",
    [
        ("MIL-PRF-81309H_Amendment1.pdf", "MIL-PRF-81309H"),
        ("MIL-PRF-16173E_InterimAmendment2.pdf", "MIL-PRF-16173E"),
        ("data/raw/MIL-S-81733C.pdf", "MIL-S-81733C"),
        (Path("a") / "MIL-PRF-23377K.pdf", "MIL-PRF-23377K"),
        ("x.pdf", None),
        ("adsiz_belge.pdf", None),
        ("mil-prf-23377k.pdf", None),       # BELGE_ETIKETI büyük harf ister
        ("MIL-PRF-23377.pdf", None),        # revizyon harfi yok
        ("MIL-PRF-23377K-kopya.pdf", None),  # ayırıcı alt çizgi değil
    ],
)
def test_dosya_etiketi_dosya_adinin_ilk_parcasidir(yol, beklenen):
    assert dosya_etiketi(yol) == beklenen


# --- B. yol_kilitli_mi -------------------------------------------------------------------


def test_cwd_kilitli_klasordeyken_goreli_yol_kilitlidir(tmp_path, monkeypatch):
    klasor = _klasor(tmp_path / "data" / "raw" / "gercek_coc_havacilik")
    (klasor / "dosya.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.chdir(klasor)
    assert _bolunme().yol_kilitli_mi("dosya.pdf")


@sembolik_bag_yok
def test_kilitli_klasore_isaret_eden_sembolik_bag_kilitlidir(tmp_path):
    klasor = _klasor(tmp_path / "data" / "raw" / "gercek_coc_havacilik")
    (klasor / "a.pdf").write_bytes(b"%PDF-1.4\n")
    bag = tmp_path / "baglanti"
    bag.symlink_to(klasor, target_is_directory=True)
    assert _bolunme().yol_kilitli_mi(bag / "a.pdf")


@sembolik_bag_yok
def test_kilitli_dosyaya_isaret_eden_dosya_bagi_kilitlidir(tmp_path):
    klasor = _klasor(tmp_path / "data" / "raw" / "gercek_coc_havacilik")
    (klasor / "a.pdf").write_bytes(b"%PDF-1.4\n")
    bag = tmp_path / "masum.pdf"
    bag.symlink_to(klasor / "a.pdf")
    assert _bolunme().yol_kilitli_mi(bag)


@pytest.mark.parametrize("ad", ["GERCEK_COC_HAVACILIK", "Gercek_Coc_Havacilik"])
def test_kilitli_klasor_adi_harf_farkiyla_atlatilamaz(ad):
    assert _bolunme().yol_kilitli_mi(f"data/raw/{ad}/a.pdf")


def test_benzer_adli_klasor_kilitli_degildir():
    b = _bolunme()
    assert not b.yol_kilitli_mi("data/raw/gercek_coc_havacilik_eski/a.pdf")
    assert not b.yol_kilitli_mi("data/raw/gercek_coa/a.pdf")


def test_kilit_acikken_yol_kilitli_degildir(tmp_path, monkeypatch):
    klasor = _klasor(tmp_path / "gercek_coc_havacilik")
    monkeypatch.chdir(klasor)
    assert not _bolunme(test_kumesi_acik=True).yol_kilitli_mi("dosya.pdf")


# --- C. icerik_kilitli_mi ----------------------------------------------------------------


def test_yeniden_adlandirilmis_test_belgesi_icerikten_yakalanir(tmp_path, ham):
    kopya = _kopya(ham / "MIL-PRF-33333C.pdf", tmp_path / "baska" / "x.pdf")
    assert _bolunme().icerik_kilitli_mi(kopya, ham)


def test_alt_klasordeki_ekli_adli_test_belgesinin_kopyasi_yakalanir(tmp_path, ham):
    kopya = _kopya(ham / "alt" / "MIL-PRF-55555E_Amendment1.pdf", tmp_path / "baska" / "rapor.pdf")
    assert _bolunme().icerik_kilitli_mi(kopya, ham)


def test_kilitli_klasordeki_belgenin_kopyasi_yakalanir(tmp_path, ham):
    kopya = _kopya(ham / "gercek_coc_havacilik" / "tedarikci_CoC.pdf", tmp_path / "baska" / "coc.pdf")
    assert _bolunme().icerik_kilitli_mi(kopya, ham)


@sembolik_bag_yok
def test_test_belgesine_sembolik_bag_icerikten_yakalanir(tmp_path, ham):
    bag = _klasor(tmp_path / "baska") / "bag.pdf"
    bag.symlink_to(ham / "MIL-PRF-33333C.pdf")
    assert _bolunme().icerik_kilitli_mi(bag, ham)


def test_gelistirme_belgesinin_kopyasi_icerik_kilitli_degildir(tmp_path, ham):
    kopya = _kopya(ham / "MIL-PRF-11111A.pdf", tmp_path / "baska" / "x.pdf")
    assert not _bolunme().icerik_kilitli_mi(kopya, ham)


def test_yeni_belge_icerik_kilitli_degildir(tmp_path, ham):
    assert not _bolunme().icerik_kilitli_mi(_yeni_pdf(tmp_path / "baska" / "x.pdf"), ham)


def test_kilit_acikken_icerik_kilitli_degildir(tmp_path, ham):
    kopya = _kopya(ham / "MIL-PRF-33333C.pdf", tmp_path / "baska" / "x.pdf")
    assert not _bolunme(test_kumesi_acik=True).icerik_kilitli_mi(kopya, ham)


# --- D. belgeyi_denetle -------------------------------------------------------------------


def test_varsayilan_ham_klasor_data_raw():
    assert Path(VARSAYILAN_HAM).resolve() == (KOK / "data" / "raw").resolve()


def test_dosya_adi_etiketi_doner(tmp_path, ham):
    yol = _yeni_pdf(tmp_path / "girdi" / "MIL-PRF-11111A.pdf")
    assert _bolunme().belgeyi_denetle(yol, ham_klasor=ham) == "MIL-PRF-11111A"


def test_verilen_etiket_dosya_adiyla_ayniysa_doner(tmp_path, ham):
    yol = _yeni_pdf(tmp_path / "girdi" / "MIL-PRF-11111A.pdf")
    assert _bolunme().belgeyi_denetle(yol, "MIL-PRF-11111A", ham_klasor=ham) == "MIL-PRF-11111A"


def test_adi_cozulemeyen_yeni_belge_verilen_etiketle_kullanilir(tmp_path, ham):
    yol = _yeni_pdf(tmp_path / "girdi" / "x.pdf")
    assert _bolunme().belgeyi_denetle(yol, "MIL-PRF-11111A", ham_klasor=ham) == "MIL-PRF-11111A"


def test_adi_cozulemeyen_ve_etiket_verilmeyen_belge_reddedilir(tmp_path, ham):
    with pytest.raises(ValueError):
        _bolunme().belgeyi_denetle(_yeni_pdf(tmp_path / "girdi" / "x.pdf"), ham_klasor=ham)


def test_etiketler_uyusmazsa_iki_etiketle_reddedilir(tmp_path, ham):
    yol = _yeni_pdf(tmp_path / "girdi" / "MIL-PRF-44444D.pdf")
    with pytest.raises(ValueError) as hata:
        _bolunme().belgeyi_denetle(yol, "MIL-PRF-11111A", ham_klasor=ham)
    assert not isinstance(hata.value, TestKumesiKilitli)
    assert "MIL-PRF-44444D" in str(hata.value) and "MIL-PRF-11111A" in str(hata.value)


def test_test_kumesindeki_dosya_adi_verilen_etiketle_gizlenemez(tmp_path, ham):
    yol = _yeni_pdf(tmp_path / "girdi" / "MIL-PRF-33333C.pdf")
    with pytest.raises(TestKumesiKilitli):
        _bolunme().belgeyi_denetle(yol, "MIL-PRF-11111A", ham_klasor=ham)


def test_verilen_etiket_test_kumesindeyse_reddedilir(tmp_path, ham):
    yol = _yeni_pdf(tmp_path / "girdi" / "x.pdf")
    with pytest.raises(TestKumesiKilitli):
        _bolunme().belgeyi_denetle(yol, "MIL-PRF-33333C", ham_klasor=ham)


def test_test_belgesinin_adsiz_kopyasi_verilen_etiketle_reddedilir(tmp_path, ham):
    kopya = _kopya(ham / "MIL-PRF-33333C.pdf", tmp_path / "girdi" / "x.pdf")
    with pytest.raises(TestKumesiKilitli):
        _bolunme().belgeyi_denetle(kopya, "MIL-PRF-11111A", ham_klasor=ham)


def test_test_belgesinin_gelistirme_adli_kopyasi_reddedilir(tmp_path, ham):
    kopya = _kopya(ham / "MIL-PRF-33333C.pdf", tmp_path / "girdi" / "MIL-PRF-11111A.pdf")
    with pytest.raises(TestKumesiKilitli):
        _bolunme().belgeyi_denetle(kopya, ham_klasor=ham)


def test_yol_kilidi_etiket_denetiminden_once_gelir(tmp_path, ham):
    # Adı bölünmede olmayan bir etiket: yol kilidi olmasa ValueError olurdu.
    yol = _yeni_pdf(tmp_path / "gercek_coc_havacilik" / "MIL-PRF-99999Z.pdf")
    with pytest.raises(TestKumesiKilitli):
        _bolunme().belgeyi_denetle(yol, ham_klasor=ham)


def test_icerik_kilidi_etiket_denetiminden_once_gelir(tmp_path, ham):
    kopya = _kopya(ham / "MIL-PRF-33333C.pdf", tmp_path / "girdi" / "MIL-PRF-99999Z.pdf")
    with pytest.raises(TestKumesiKilitli):
        _bolunme().belgeyi_denetle(kopya, ham_klasor=ham)


def test_kilitli_klasordeki_belge_gelistirme_adiyla_da_reddedilir(tmp_path, ham):
    yol = _yeni_pdf(tmp_path / "gercek_coc_havacilik" / "MIL-PRF-11111A.pdf")
    with pytest.raises(TestKumesiKilitli):
        _bolunme().belgeyi_denetle(yol, "MIL-PRF-11111A", ham_klasor=ham)


def test_taranmis_belge_ocr_olmadan_reddedilir_ocr_ile_kabul_edilir(tmp_path, ham):
    yol = _kopya(ham / "MIL-S-22222B.pdf", tmp_path / "girdi" / "MIL-S-22222B.pdf")
    with pytest.raises(OcrGerekli):
        _bolunme().belgeyi_denetle(yol, ham_klasor=ham)
    assert _bolunme().belgeyi_denetle(yol, ocr=True, ham_klasor=ham) == "MIL-S-22222B"


def test_kilit_acikken_test_belgesinin_kopyasi_kullanilir(tmp_path, ham):
    kopya = _kopya(ham / "MIL-PRF-33333C.pdf", tmp_path / "girdi" / "x.pdf")
    assert _bolunme(test_kumesi_acik=True).belgeyi_denetle(kopya, "MIL-PRF-33333C", ham_klasor=ham) == \
        "MIL-PRF-33333C"


AMENDMENT = KOK / "data" / "raw" / "MIL-PRF-81309H_Amendment1.pdf"


@pytest.mark.skipif(not AMENDMENT.exists(), reason="data/raw/MIL-PRF-81309H_Amendment1.pdf yok")
def test_depoda_test_belgesi_baska_etiketle_kullanilamaz():
    with pytest.raises(TestKumesiKilitli):
        bolunme_oku().belgeyi_denetle(AMENDMENT, "MIL-PRF-23377K")


# --- F. gold_altinda_mi ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "yol",
    [GOLD, GOLD / "x.json", GOLD / "alt" / "klasor", KOK / "data" / "GOLD" / "x", KOK / "data" / "gold" / ".." / "gold"],
    ids=["kendisi", "dosya", "alt_klasor", "harf_farki", "nokta_nokta"],
)
def test_gold_altindaki_yollar_yakalanir(yol):
    assert gold_altinda_mi(yol) is True


def test_goreli_gold_yolu_yakalanir(monkeypatch):
    monkeypatch.chdir(KOK)
    assert gold_altinda_mi("data/gold/x.json") is True


@sembolik_bag_yok
def test_golde_isaret_eden_sembolik_bag_yakalanir(tmp_path):
    bag = tmp_path / "bag"
    bag.symlink_to(GOLD, target_is_directory=True)
    assert gold_altinda_mi(bag / "x.json") is True


@pytest.mark.parametrize(
    "yol", [KOK / "data" / "gold_taslak" / "x.json", KOK / "data" / "gold_codex", KOK / "deney" / "sonuclar"],
    ids=["gold_taslak", "gold_codex", "sonuclar"],
)
def test_gold_disindaki_yollar_serbest(yol):
    assert gold_altinda_mi(yol) is False


def test_gecici_klasor_gold_degildir(tmp_path):
    assert gold_altinda_mi(tmp_path / "cikti") is False


@pytest.mark.parametrize("betik", ["deney/uc_mod.py", "deney/ocr_olcumu.py", "deney/dil_modeli_cikar.py"])
def test_betikler_gold_denetimini_kopyalamaz(betik):
    kaynak = (KOK / betik).read_text(encoding="utf-8")
    tanimlar = [d.name for d in ast.walk(ast.parse(kaynak)) if isinstance(d, ast.FunctionDef) and "gold" in d.name
                and "altinda" in d.name]
    assert tanimlar == [], f"{betik} kendi gold denetimini tanımlıyor; deney.bolunme.gold_altinda_mi kullanılmalı"
    assert "gold_altinda_mi" in kaynak


# --- data/raw her zaman taranır; ham_klasor yalnız ektir (son tur) ------------------------


@pytest.fixture
def bos_ham(tmp_path) -> Path:
    return _klasor(tmp_path / "bos_ham")


@pytest.mark.skipif(not AMENDMENT.exists(), reason="data/raw/MIL-PRF-81309H_Amendment1.pdf yok")
def test_bos_ham_klasor_verilse_de_data_raw_taranir(tmp_path, bos_ham):
    # Test kümesindeki gerçek belgenin geliştirme adlı kopyası; yalnız özet için okunur.
    kopya = _kopya(AMENDMENT, tmp_path / "girdi" / "MIL-PRF-23377K.pdf")
    b = bolunme_oku()
    assert b.icerik_kilitli_mi(kopya, bos_ham)
    with pytest.raises(TestKumesiKilitli):
        b.belgeyi_denetle(kopya, ham_klasor=bos_ham)
    with pytest.raises(TestKumesiKilitli):
        b.belgeyi_denetle(kopya, "MIL-PRF-23377K", ham_klasor=bos_ham)


@pytest.mark.skipif(not AMENDMENT.exists(), reason="data/raw/MIL-PRF-81309H_Amendment1.pdf yok")
def test_ek_ham_klasor_data_raw_ile_birlesir(tmp_path, ham):
    # Gerçek data/raw'daki test kopyası ve geçici ham klasördeki test kopyası aynı çağrıda yakalanır.
    b = bolunme_oku()
    gercek = _kopya(AMENDMENT, tmp_path / "girdi" / "MIL-PRF-23377K.pdf")
    assert b.icerik_kilitli_mi(gercek, ham)
    gecici = _bolunme()
    sahte = _kopya(ham / "MIL-PRF-33333C.pdf", tmp_path / "girdi" / "x.pdf")
    assert gecici.icerik_kilitli_mi(sahte, ham)


def test_olmayan_ham_klasor_reddedilir(tmp_path):
    yol = _yeni_pdf(tmp_path / "girdi" / "MIL-PRF-11111A.pdf")
    olmayan = tmp_path / "yok_klasor"
    with pytest.raises(ValueError) as hata:
        _bolunme().belgeyi_denetle(yol, ham_klasor=olmayan)
    assert not isinstance(hata.value, TestKumesiKilitli)
    with pytest.raises(ValueError):
        _bolunme().icerik_kilitli_mi(yol, olmayan)


def test_klasor_olmayan_ham_yolu_reddedilir(tmp_path):
    yol = _yeni_pdf(tmp_path / "girdi" / "MIL-PRF-11111A.pdf")
    dosya = tmp_path / "ham.txt"
    dosya.write_text("klasör değil", encoding="utf-8")
    with pytest.raises(ValueError):
        _bolunme().belgeyi_denetle(yol, ham_klasor=dosya)
    with pytest.raises(ValueError):
        _bolunme().icerik_kilitli_mi(yol, dosya)


def test_ham_klasor_verilmezse_yalniz_data_raw_taranir(tmp_path):
    yol = _yeni_pdf(tmp_path / "girdi" / "MIL-PRF-11111A.pdf")
    assert _bolunme().belgeyi_denetle(yol) == "MIL-PRF-11111A"
    assert _bolunme().belgeyi_denetle(yol, ham_klasor=None) == "MIL-PRF-11111A"


def test_uc_mod_main_olmayan_ham_klasor_icin_2_doner(tmp_path, monkeypatch, capsys):
    from deney import uc_mod
    from malzeme_kabul.cikarim.yerel_model import YerelModelIstemcisi

    def sohbet(self, mesajlar, sema):
        raise AssertionError("model çağrılmamalıydı")

    monkeypatch.setattr(YerelModelIstemcisi, "sohbet", sohbet)
    bolunme = tmp_path / "bolunme.yaml"
    bolunme.write_text("gelistirme:\n  - MIL-PRF-11111A\n", encoding="utf-8")
    pdf = _yeni_pdf(tmp_path / "girdi" / "MIL-PRF-11111A.pdf")
    cikti = tmp_path / "cikti"
    kod = uc_mod.main([str(pdf), "--model", "qwen3:8b", "--cikti", str(cikti), "--gold-yok",
                       "--bolunme", str(bolunme), "--ham-klasor", str(tmp_path / "yok_klasor")])
    assert kod == 2
    assert "yok_klasor" in capsys.readouterr().err
    assert not cikti.exists() or list(cikti.iterdir()) == []


def test_dil_modeli_cikar_main_olmayan_ham_klasor_icin_2_doner(tmp_path, monkeypatch):
    from conftest import betik_yukle

    betik = betik_yukle("deney/dil_modeli_cikar.py")
    kurulanlar = []

    class KayitliIstemci:
        def __init__(self, *a, **k):
            kurulanlar.append(k)

        def sohbet(self, mesajlar, sema):
            raise AssertionError("model çağrılmamalıydı")

    monkeypatch.setattr(betik, "YerelModelIstemcisi", KayitliIstemci)
    bolunme = tmp_path / "bolunme.yaml"
    bolunme.write_text("gelistirme:\n  - MIL-PRF-11111A\n", encoding="utf-8")
    pdf = _yeni_pdf(tmp_path / "girdi" / "MIL-PRF-11111A.pdf")
    cikti = tmp_path / "cikti"
    kod = betik.main([str(pdf), "--model", "deneme:7b", "--bolunme", str(bolunme), "--cikti", str(cikti),
                      "--ham-klasor", str(tmp_path / "yok_klasor")])
    assert kod == 2
    assert kurulanlar == []
    assert not cikti.exists()
