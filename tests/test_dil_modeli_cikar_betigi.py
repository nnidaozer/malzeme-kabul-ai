"""deney/dil_modeli_cikar.py komut satırının kilit, etiket ve OCR davranışı.

Gerçek model ve tesseract çağrılmaz: YerelModelIstemcisi ve TesseractMotoru
betik modülünde sahteleriyle değiştirilir. Geçici bir bolunme.yaml kullanılır.
"""

from __future__ import annotations

import builtins
import json
import os
import shutil
from pathlib import Path

import pytest

from conftest import betik_yukle
from pdf_uretici import pdf_yaz

BOLUNME = """test_kumesi_acik: false
test_durumu: secildi
tohum: 1

gelistirme:
  - MIL-PRF-11111A
  - MIL-PRF-44444D
  - MIL-S-22222B

yeni_standartlar:
  - MIL-PRF-33333C

test:
  - MIL-PRF-33333C

kilitli_klasorler:
  - kilitli_klasor

ocr_gerekli:
  - MIL-S-22222B
"""

METIN = "3.6.3 Viscosity. The maximum viscosity shall be 40 seconds through a cup."


@pytest.fixture
def bolunme(tmp_path) -> Path:
    yol = tmp_path / "bolunme.yaml"
    yol.write_text(BOLUNME, encoding="utf-8")
    return yol


class _KayitliIstemci:
    """Kurulan her istemciyi kaydeder; model hep boş liste döner."""

    kurulanlar: list[_KayitliIstemci] = []

    def __init__(self, model, arka_uc="ollama", adres=None, baglam=8192, dusunme=None, **k):
        self.model, self.arka_uc, self.adres, self.baglam, self.dusunme = model, arka_uc, adres, baglam, dusunme
        _KayitliIstemci.kurulanlar.append(self)

    def sohbet(self, mesajlar, sema):
        return json.dumps({"testler": []})


class _SahteTesseract:
    """sayfa_oku çağrılarını kaydeden sahte motor."""

    cagrilar: list[int] = []

    def __init__(self, *a, **k):
        pass

    def sayfa_oku(self, pdf_yolu, sayfa_no):
        from malzeme_kabul.belge.ocr import OcrKelime, OcrSonucu

        _SahteTesseract.cagrilar.append(sayfa_no)
        return OcrSonucu(METIN, (OcrKelime("Viscosity.", 90.0),))


class _BozukTesseract:
    def __init__(self, *a, **k):
        pass

    def sayfa_oku(self, pdf_yolu, sayfa_no):
        from malzeme_kabul.belge.ocr import OcrKullanilamaz

        raise OcrKullanilamaz("tesseract hata koduyla bitti (1): Failed loading language 'eng'")


@pytest.fixture
def betik(monkeypatch):
    modul = betik_yukle("deney/dil_modeli_cikar.py")
    _KayitliIstemci.kurulanlar = []
    _SahteTesseract.cagrilar = []
    monkeypatch.setattr(modul, "YerelModelIstemcisi", _KayitliIstemci)
    monkeypatch.setattr(modul, "TesseractMotoru", _SahteTesseract)
    monkeypatch.setattr(modul, "tesseract_var_mi", lambda *a, **k: True)
    return modul


def _metin_pdf(klasor: Path, ad: str) -> Path:
    klasor.mkdir(parents=True, exist_ok=True)
    return pdf_yaz(klasor / ad, [{"metin": [METIN]}])


def _taranmis_pdf(klasor: Path, ad: str) -> Path:
    klasor.mkdir(parents=True, exist_ok=True)
    return pdf_yaz(klasor / ad, [{"gorsel": True}])


def _calistir(betik, pdf: Path, bolunme: Path, cikti: Path, *ek: str) -> int:
    return betik.main([str(pdf), "--model", "deneme:7b", "--bolunme", str(bolunme), "--cikti", str(cikti), *ek])


def test_gelistirme_belgesi_islenir(betik, tmp_path, bolunme):
    # Kurulumun kendisi doğru: aynı sahtelerle geliştirme belgesi 0 döner.
    pdf = _metin_pdf(tmp_path / "girdi", "MIL-PRF-11111A.pdf")
    assert _calistir(betik, pdf, bolunme, tmp_path / "cikti") == 0
    assert len(_KayitliIstemci.kurulanlar) == 1


# --- Etiket taklidi ---------------------------------------------------------------------


def test_verilen_etiket_test_kumesindeki_dosya_adini_gizleyemez(betik, tmp_path, bolunme):
    pdf = _metin_pdf(tmp_path / "girdi", "MIL-PRF-33333C.pdf")
    cikti = tmp_path / "cikti"
    kod = _calistir(betik, pdf, bolunme, cikti, "--belge-no", "MIL-PRF-11111", "--revizyon", "A")
    assert kod == 2
    assert _KayitliIstemci.kurulanlar == []
    assert not cikti.exists()


def test_verilen_etiket_ile_ocr_test_kumesindeki_dosyayi_okumaz(betik, tmp_path, bolunme):
    pdf = _taranmis_pdf(tmp_path / "girdi", "MIL-PRF-33333C.pdf")
    kod = _calistir(betik, pdf, bolunme, tmp_path / "cikti", "--belge-no", "MIL-PRF-11111", "--revizyon", "A",
                    "--ocr")
    assert kod == 2
    assert _SahteTesseract.cagrilar == []
    assert _KayitliIstemci.kurulanlar == []


def test_dosya_adi_etiketi_verilenden_farkliysa_2_doner_ve_iki_etiketi_yazar(betik, tmp_path, bolunme, capsys):
    pdf = _metin_pdf(tmp_path / "girdi", "MIL-PRF-44444D.pdf")
    kod = _calistir(betik, pdf, bolunme, tmp_path / "cikti", "--belge-no", "MIL-PRF-11111", "--revizyon", "A")
    assert kod == 2
    hata = capsys.readouterr().err
    assert "MIL-PRF-44444D" in hata and "MIL-PRF-11111A" in hata
    assert _KayitliIstemci.kurulanlar == []


@pytest.fixture
def ham(tmp_path) -> Path:
    """Geçici ham klasör: test kümesindeki MIL-PRF-33333C'nin sahte PDF'i (içerik kilidi için)."""
    kok = tmp_path / "ham"
    kok.mkdir()
    pdf_yaz(kok / "MIL-PRF-33333C.pdf", [{"metin": ["3.1 Test kumesi belgesi otuz uc bin uc yuz otuz uc."]}])
    return kok


def test_dosya_adi_cozulemiyorsa_verilen_etiket_kullanilir(betik, tmp_path, bolunme, ham):
    # İçeriği test kümesinde olmayan adsız belge verilen etiketle işlenir (davranış korunur).
    pdf = _metin_pdf(tmp_path / "girdi", "adsiz_belge.pdf")
    kod = _calistir(betik, pdf, bolunme, tmp_path / "cikti", "--belge-no", "MIL-PRF-11111", "--revizyon", "A",
                    "--ham-klasor", str(ham))
    assert kod == 0
    assert (tmp_path / "cikti" / "MIL-PRF-11111A_dil_modeli_deneme_7b.json").is_file()


def test_adsiz_test_belgesi_kopyasi_verilen_etiketle_reddedilir(betik, tmp_path, bolunme, ham):
    kopya = tmp_path / "girdi" / "x.pdf"
    kopya.parent.mkdir(parents=True)
    shutil.copyfile(ham / "MIL-PRF-33333C.pdf", kopya)
    cikti = tmp_path / "cikti"
    kod = _calistir(betik, kopya, bolunme, cikti, "--belge-no", "MIL-PRF-11111", "--revizyon", "A",
                    "--ham-klasor", str(ham), "--ocr")
    assert kod == 2
    assert _KayitliIstemci.kurulanlar == []
    assert _SahteTesseract.cagrilar == []
    assert not cikti.exists()


# --- data/gold koruması ------------------------------------------------------------------

GOLD = (Path(__file__).resolve().parents[1] / "data" / "gold").resolve()


@pytest.fixture
def gold_yazma_yasak(monkeypatch):
    """Koruma ağı: betik data/gold altına yazmaya kalkarsa (hata varsa) yazmadan önce test düşer."""

    def koru(yol):
        try:
            Path(os.path.abspath(os.fspath(yol))).relative_to(GOLD)
        except (ValueError, TypeError):
            return
        raise AssertionError(f"data/gold altına yazma girişimi: {yol}")

    gercek_open, gercek_mkdir, gercek_path_open = builtins.open, Path.mkdir, Path.open
    gercek_write_text, gercek_write_bytes = Path.write_text, Path.write_bytes
    gercek_makedirs, gercek_os_open = os.makedirs, os.open

    def open_(dosya, mode="r", *a, **k):
        if isinstance(dosya, (str, os.PathLike)) and any(c in mode for c in "wax+"):
            koru(dosya)
        return gercek_open(dosya, mode, *a, **k)

    def path_open_(self, mode="r", *a, **k):
        if any(c in mode for c in "wax+"):
            koru(self)
        return gercek_path_open(self, mode, *a, **k)

    def mkdir_(self, *a, **k):
        koru(self)
        return gercek_mkdir(self, *a, **k)

    def write_text_(self, *a, **k):
        koru(self)
        return gercek_write_text(self, *a, **k)

    def write_bytes_(self, *a, **k):
        koru(self)
        return gercek_write_bytes(self, *a, **k)

    def makedirs_(yol, *a, **k):
        koru(yol)
        return gercek_makedirs(yol, *a, **k)

    def os_open_(yol, flags, *a, **k):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            koru(yol)
        return gercek_os_open(yol, flags, *a, **k)

    monkeypatch.setattr(builtins, "open", open_)
    monkeypatch.setattr(Path, "open", path_open_)
    monkeypatch.setattr(Path, "mkdir", mkdir_)
    monkeypatch.setattr(Path, "write_text", write_text_)
    monkeypatch.setattr(Path, "write_bytes", write_bytes_)
    monkeypatch.setattr(os, "makedirs", makedirs_)
    monkeypatch.setattr(os, "open", os_open_)


def test_cikti_data_gold_altindaysa_2_doner_ve_hicbir_sey_yazilmaz(betik, tmp_path, bolunme, ham,
                                                                   gold_yazma_yasak):
    hedef = GOLD / "dil_modeli_deneme"
    pdf = _metin_pdf(tmp_path / "girdi", "MIL-PRF-11111A.pdf")
    assert not hedef.exists()
    assert _calistir(betik, pdf, bolunme, hedef, "--ham-klasor", str(ham)) == 2
    assert not hedef.exists()
    assert _KayitliIstemci.kurulanlar == []


# --- Kilitli klasör ---------------------------------------------------------------------


def test_kilitli_klasordeki_pdf_reddedilir_istemci_kurulmaz(betik, tmp_path, bolunme):
    pdf = _metin_pdf(tmp_path / "kilitli_klasor", "MIL-PRF-11111A.pdf")  # etiket geliştirmede, klasör kilitli
    cikti = tmp_path / "cikti"
    assert _calistir(betik, pdf, bolunme, cikti) == 2
    assert _KayitliIstemci.kurulanlar == []
    assert not cikti.exists()


# --- OCR ---------------------------------------------------------------------------------


def test_taranmis_belge_ocr_olmadan_2_doner(betik, tmp_path, bolunme, capsys):
    pdf = _taranmis_pdf(tmp_path / "girdi", "MIL-S-22222B.pdf")
    assert _calistir(betik, pdf, bolunme, tmp_path / "cikti") == 2
    assert "OCR gerekli" in capsys.readouterr().err
    assert _KayitliIstemci.kurulanlar == []


def test_taranmis_belge_ocr_ile_okunur(betik, tmp_path, bolunme):
    pdf = _taranmis_pdf(tmp_path / "girdi", "MIL-S-22222B.pdf")
    cikti = tmp_path / "cikti"
    assert _calistir(betik, pdf, bolunme, cikti, "--ocr") == 0
    assert _SahteTesseract.cagrilar == [1]
    assert (cikti / "MIL-S-22222B_dil_modeli_deneme_7b.json").is_file()


def test_ocr_motoru_hata_verirse_2_doner_yigin_izi_vermez(betik, tmp_path, bolunme, monkeypatch, capsys):
    monkeypatch.setattr(betik, "TesseractMotoru", _BozukTesseract)
    pdf = _taranmis_pdf(tmp_path / "girdi", "MIL-S-22222B.pdf")
    assert _calistir(betik, pdf, bolunme, tmp_path / "cikti", "--ocr") == 2
    hata = capsys.readouterr().err
    assert "Failed loading language" in hata
    assert "Traceback" not in hata
