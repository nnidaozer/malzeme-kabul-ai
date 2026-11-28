"""Dizüstü ölçüm betiği (deney/dizustu_olcum.py): Ollama ile küçük modellerde belge başına süre ve F1.

Gerçek model ve gerçek ağ kullanılmaz: sahte istemci, sahte ağ denetimi, sahte
Ollama durumu ve küçük sentetik PDF'ler kullanılır. Bölünme dosyası ve gold'lar
pytest'in geçici kökünde üretilir; data/gold/ altına hiçbir şey yazılmaz
(yazılmaya kalkışılırsa test hata verir). Test kümesindeki gerçek belgeler açılmaz.
"""

from __future__ import annotations

import builtins
import csv
import email.message
import http.client
import http.server
import io
import json
import sys
import types
import os
import shutil
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from pdf_uretici import pdf_yaz

from malzeme_kabul.cikarim.kural_cikarici import cikar
from malzeme_kabul.cikarim.yerel_model import ModelYanitHatasi

KOK = Path(__file__).resolve().parents[1]
GOLD = (KOK / "data" / "gold").resolve()

M15 = "qwen2.5:1.5b-instruct-q4_K_M"
M3 = "qwen2.5:3b-instruct-q4_K_M"
M3_KLASOR = "qwen2.5_3b-instruct-q4_K_M"
MODLAR = ("kural", "dil_modeli", "hibrit")
# Sözleşme değişikliği (gözden geçirme): mevcut sütunlardan sonra sona basarisiz_sayfa ve devam_edilen_sayfa.
SATIR_SUTUNLARI = ["model", "belge", "mod", "sayfa_sayisi", "test_sayisi", "sure_s", "sayfa_basi_s",
                   "f1_gold_taslak", "f1_gold_codex", "basarisiz_sayfa", "devam_edilen_sayfa"]

KOKU_METNI = "The odor shall not be objectionable."
VISKOZITE_METNI = "The maximum viscosity shall be 40 seconds through a cup."


def _dizustu():
    from deney import dizustu_olcum

    return dizustu_olcum


# --- Koruma ağı ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def gold_yazma_yasak(monkeypatch):
    """data/gold/ altına yazma girişimi testi hata ile düşürür."""

    def koru(yol):
        try:
            Path(os.path.abspath(os.fspath(yol))).relative_to(GOLD)
        except (ValueError, TypeError):
            return
        raise AssertionError(f"data/gold altına yazma girişimi: {yol}")

    gercek_open, gercek_mkdir, gercek_path_open = builtins.open, Path.mkdir, Path.open
    gercek_os_open, gercek_makedirs, gercek_replace = os.open, os.makedirs, os.replace

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

    gercek_rmtree, gercek_remove, gercek_rmdir, gercek_unlink = shutil.rmtree, os.remove, os.rmdir, os.unlink

    def rmtree_(yol, *a, **k):
        koru(yol)
        return gercek_rmtree(yol, *a, **k)

    def tekli_sil(gercek):
        def sil(yol, *a, **k):
            koru(yol)
            return gercek(yol, *a, **k)
        return sil

    monkeypatch.setattr(shutil, "rmtree", rmtree_)
    monkeypatch.setattr(os, "remove", tekli_sil(gercek_remove))
    monkeypatch.setattr(os, "rmdir", tekli_sil(gercek_rmdir))
    monkeypatch.setattr(os, "unlink", tekli_sil(gercek_unlink))


# --- Sahte veri ------------------------------------------------------------------


def _pdf(yol: Path, baslik: str) -> Path:
    """Kural çıkarıcısının iki test bulduğu, ayrıca 'odor' maddesi olan iki sayfalık belge."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    return pdf_yaz(yol, [
        {"metin": [baslik, "3.6.3 Viscosity. The maximum viscosity shall be", "40 seconds through a cup.",
                   "3.6.9 Lead content. The lead content shall be not greater than 1 ppm.",
                   f"3.6.10 Odor. {KOKU_METNI}"]},
        {"metin": [baslik, "TABLE II. Tests"],
         "tablo": [["Requirement", "Req para", "Test method", "Test para"],
                   ["Viscosity", "3.6.3", "4.6.3", "ASTM D1200"],
                   ["Lead content", "3.6.9", "4.6.9", "ASTM D3335"]]},
    ])


def _test_json(id_, ad, madde, sinir) -> dict:
    return {
        "id": id_, "test_adi": ad, "sinir": sinir,
        "kaynak": {"belge_no": "MIL-PRF-23377", "revizyon": "K", "madde": madde, "sayfa": 1},
        "test_turleri": ["kabul"],
    }


def _sayfa1_yaniti() -> str:
    return json.dumps({"testler": [
        _test_json("viscosity", "Viscosity", "3.6.3",
                   {"kriter_turu": "sayisal", "ust": 30, "birim": "s", "orijinal_metin": VISKOZITE_METNI}),
        _test_json("odor", "Odor", "3.6.10", {"kriter_turu": "metinsel", "orijinal_metin": KOKU_METNI}),
    ]})


def _isinma_mi(mesajlar) -> bool:
    """Isınma çağrısının user mesajı "ısınma" kelimesini içerir (sözleşme)."""
    return "ısınma" in mesajlar[-1]["content"]


class SahteIstemci:
    """Isınma çağrısına kısa bir JSON, sayfa çağrılarına sabit yanıt döner.

    `cagrilar` ısınma dahil bütün çağrıları, `sayfa_cagrilari` yalnız sayfa çağrılarını sayar;
    `mesajlar` her çağrının (mesajlar, şema) çiftidir.
    """

    arka_uc, dusunme, baglam = "ollama", False, 8192

    def __init__(self, model: str = M3):
        self.model = model
        self.cagrilar = 0
        self.sayfa_cagrilari = 0
        self.mesajlar: list[tuple[list[dict], object]] = []

    def sohbet(self, mesajlar, sema):
        self.cagrilar += 1
        self.mesajlar.append((mesajlar, sema))
        if _isinma_mi(mesajlar):
            return self.isinma(mesajlar, sema)
        self.sayfa_cagrilari += 1
        return self.sayfa(mesajlar, sema)

    def isinma(self, mesajlar, sema):
        return json.dumps({"tamam": True})

    def sayfa(self, mesajlar, sema):
        if "sayfa 1." in mesajlar[1]["content"]:
            return _sayfa1_yaniti()
        return json.dumps({"testler": []})


class HataliIstemci(SahteIstemci):
    """Isınma geçer; sayfa çağrısında sunucu beklenmedik yanıt döner (ModelYanitHatasi).

    Sözleşme değişikliği (ısınma): önceden her çağrıda hata veriyordu; ısınma eklenince
    o model hiç ölçülmezdi. Belge düzeyindeki hata davranışı korunsun diye ısınma geçer.
    """

    def sayfa(self, mesajlar, sema):
        raise ModelYanitHatasi("sunucu yanıtı beklenen yapıda değil")


def _http_500(*a):
    hdrs = email.message.Message()
    return urllib.error.HTTPError("http://127.0.0.1:11434/api/chat", 500, "model requires more system memory",
                                  hdrs, None)


class Http500Istemci(SahteIstemci):
    """Isınma geçer; her sayfa isteği HTTP 500 (bellek yetmiyor) ile düşer."""

    def sayfa(self, mesajlar, sema):
        raise _http_500()


class ZamanAsimiIstemci(SahteIstemci):
    """Isınma geçer; her sayfa isteği zaman aşımına uğrar."""

    def sayfa(self, mesajlar, sema):
        raise TimeoutError("timed out")


class CagrilmamaliIstemci(SahteIstemci):
    def sohbet(self, mesajlar, sema):
        raise AssertionError("model çağrılmamalıydı")


class IstemciUretici:
    """istemci_uret(model) sahtesi; hangi modeller için istemci üretildiğini kaydeder."""

    def __init__(self, sinif=SahteIstemci):
        self.sinif = sinif
        self.modeller: list[str] = []
        self.istemciler: list[SahteIstemci] = []

    def __call__(self, model):
        self.modeller.append(model)
        istemci = self.sinif(model)
        self.istemciler.append(istemci)
        return istemci


def _ag(kapali: bool) -> dict:
    return {"kapali": kapali, "denemeler": [
        {"deneme": "DNS pypi.org", "basarili": not kapali, "ayrinti": "gaierror" if kapali else "151.101.0.223"},
        {"deneme": "TCP 1.1.1.1:443", "basarili": False, "ayrinti": "OSError"},
    ]}


class AgDenetleyici:
    """ag_denetle() sahtesi; çağrı sayısını sayar."""

    def __init__(self, kapali: bool = True):
        self.kapali = kapali
        self.cagri = 0

    def __call__(self):
        self.cagri += 1
        return _ag(self.kapali)


class SiraliAgDenetleyici:
    """ag_denetle() sahtesi; sırayla verilen durumları döner, sonuncusunu tekrarlar."""

    def __init__(self, *durumlar: bool):
        self.durumlar = list(durumlar)
        self.cagri = 0

    def __call__(self):
        durum = self.durumlar[min(self.cagri, len(self.durumlar) - 1)]
        self.cagri += 1
        return _ag(durum)


def _ollama(*modeller) -> dict:
    return {"surum": "0.5.7", "modeller": list(modeller), "hata": None}


def _tohum_87937_teste() -> tuple[int, list[str], list[str]]:
    """87937 ailesini test kümesine koyan tohum; (tohum, yeni_standartlar, test)."""
    from deney.bolunme import yariyi_sec

    yeni = ["MIL-PRF-81309G", "MIL-PRF-81309H", "MIL-PRF-87937D", "MIL-PRF-87937E"]
    for tohum in range(1000):
        test = yariyi_sec(yeni, tohum)
        if "MIL-PRF-87937E" in test:
            return tohum, yeni, test
    raise AssertionError("uygun tohum bulunamadı")


def _bolunme_yaz(kok: Path, gelistirme: list[str]) -> Path:
    """Geçerli bir bölünme: verilen geliştirme listesi + 81309 ailesi; 87937 ailesi test kümesinde."""
    tohum, yeni, test = _tohum_87937_teste()
    kalan = [b for b in yeni if b not in test]
    satirlar = ["test_kumesi_acik: false", "test_durumu: secildi", f"tohum: {tohum}", "", "gelistirme:"]
    satirlar += [f"  - {b}" for b in gelistirme + kalan]
    satirlar += ["", "yeni_standartlar:"] + [f"  - {b}" for b in yeni]
    satirlar += ["", "test:"] + [f"  - {b}" for b in test]
    satirlar += ["", "kilitli_klasorler:", "  - gercek_coc_havacilik", ""]
    yol = kok / "data" / "bolunme.yaml"
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text("\n".join(satirlar), encoding="utf-8")
    return yol


@pytest.fixture
def kok(tmp_path):
    """Geçici depo kökü: bölünme, iki geliştirme PDF'i (23377K gold'lu, 81733D gold'suz), bir test PDF'i."""
    k = tmp_path / "kok"
    _bolunme_yaz(k, ["MIL-PRF-23377K", "MIL-PRF-81733D", "MIL-PRF-85285E"])
    raw = k / "data" / "raw"
    pdf = _pdf(raw / "MIL-PRF-23377K.pdf", "MIL-PRF-23377K")
    _pdf(raw / "MIL-PRF-81733D.pdf", "MIL-PRF-81733D")
    _pdf(raw / "MIL-PRF-87937E.pdf", "MIL-PRF-87937E")
    gold = k / "data" / "gold_taslak" / "MIL-PRF-23377K.json"
    gold.parent.mkdir(parents=True)
    # Gold kural çıktısının kendisi: kural modunun F1'i 1 olmalı.
    gold.write_text(cikar(pdf, "MIL-PRF-23377", "K").model_dump_json(indent=2), encoding="utf-8")
    return k


def _bolunme(kok: Path) -> Path:
    return kok / "data" / "bolunme.yaml"


def _belge(kok: Path, ad: str) -> Path:
    return kok / "data" / "raw" / f"{ad}.pdf"


def _olc(kok: Path, cikti: Path, belgeler=None, modeller=(M3,), uretici=None, ag=None, ollama=None, **k):
    return _dizustu().olcum_yap(
        list(modeller),
        belgeler if belgeler is not None else [_belge(kok, "MIL-PRF-23377K")],
        cikti,
        istemci_uret=uretici or IstemciUretici(),
        ag_denetle=ag or AgDenetleyici(True),
        ollama=ollama or _ollama(M15, M3),
        bolunme=_bolunme(kok),
        kok=kok,
        **k,
    )


# --- Sabitler --------------------------------------------------------------------


def test_varsayilan_modeller_qwen25_1_5b_ve_3b_q4_k_m():
    assert _dizustu().VARSAYILAN_MODELLER == (M15, M3)


def test_varsayilan_cikti_deney_sonuclar_dizustu():
    assert Path(_dizustu().VARSAYILAN_CIKTI) == KOK / "deney" / "sonuclar" / "dizustu"


# --- varsayilan_belgeler ---------------------------------------------------------


def test_varsayilan_belgeler_gercek_depoda_gold_lu_uc_gelistirme_belgesini_doner():
    belgeler = _dizustu().varsayilan_belgeler()
    assert [Path(b).name for b in belgeler] == ["MIL-PRF-23377K.pdf", "MIL-PRF-81733D.pdf", "MIL-PRF-85285E.pdf"]


def test_varsayilan_belgeler_pdf_ve_gold_u_olan_gelistirme_belgelerini_bolunme_sirasiyla_doner(tmp_path):
    k = tmp_path / "kok"
    # Sıra: 85285E önce, 23377K sonra; 81733D'nin gold'u yok, 32239B'nin PDF'i yok.
    _bolunme_yaz(k, ["MIL-PRF-85285E", "MIL-PRF-81733D", "MIL-PRF-23377K", "MIL-PRF-32239B"])
    raw = k / "data" / "raw"
    raw.mkdir(parents=True)
    for ad in ("MIL-PRF-85285E", "MIL-PRF-81733D", "MIL-PRF-23377K", "MIL-PRF-87937D", "MIL-PRF-87937E"):
        (raw / f"{ad}.pdf").write_bytes(b"%PDF-1.4\n")
    for klasor, ad in (("gold_codex", "MIL-PRF-85285E"), ("gold_taslak", "MIL-PRF-23377K"),
                       ("gold_taslak", "MIL-PRF-32239B"), ("gold_taslak", "MIL-PRF-87937D"),
                       ("gold_codex", "MIL-PRF-87937E")):
        yol = k / "data" / klasor / f"{ad}.json"
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text("{}", encoding="utf-8")

    belgeler = _dizustu().varsayilan_belgeler(bolunme=_bolunme(k), kok=k)
    assert [Path(b) for b in belgeler] == [raw / "MIL-PRF-85285E.pdf", raw / "MIL-PRF-23377K.pdf"]


def test_varsayilan_belgeler_pdf_i_ve_gold_u_olsa_da_test_kumesindeki_belgeyi_donmez(tmp_path):
    k = tmp_path / "kok"
    _bolunme_yaz(k, ["MIL-PRF-23377K"])
    for ad in ("MIL-PRF-23377K", "MIL-PRF-87937E"):
        yol = k / "data" / "raw" / f"{ad}.pdf"
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_bytes(b"%PDF-1.4\n")
        gold = k / "data" / "gold_taslak" / f"{ad}.json"
        gold.parent.mkdir(parents=True, exist_ok=True)
        gold.write_text("{}", encoding="utf-8")
    adlar = [Path(b).stem for b in _dizustu().varsayilan_belgeler(bolunme=_bolunme(k), kok=k)]
    assert adlar == ["MIL-PRF-23377K"]


def test_varsayilan_belgeler_data_gold_klasorunu_gold_saymaz(tmp_path):
    k = tmp_path / "kok"
    _bolunme_yaz(k, ["MIL-PRF-23377K"])
    (k / "data" / "raw").mkdir(parents=True)
    (k / "data" / "raw" / "MIL-PRF-23377K.pdf").write_bytes(b"%PDF-1.4\n")
    (k / "data" / "gold").mkdir()
    (k / "data" / "gold" / "MIL-PRF-23377K.json").write_text("{}", encoding="utf-8")
    assert _dizustu().varsayilan_belgeler(bolunme=_bolunme(k), kok=k) == []


# --- ag_denetimi -----------------------------------------------------------------


def test_ag_denetimi_hicbir_deneme_basarili_degilse_kapali():
    sonuc = _dizustu().ag_denetimi(lambda: [("DNS pypi.org", False, "gaierror"), ("TCP 1.1.1.1:443", False, "OSError")])
    assert sonuc == {"kapali": True, "denemeler": [
        {"deneme": "DNS pypi.org", "basarili": False, "ayrinti": "gaierror"},
        {"deneme": "TCP 1.1.1.1:443", "basarili": False, "ayrinti": "OSError"},
    ]}


def test_ag_denetimi_tek_deneme_basariliysa_acik():
    sonuc = _dizustu().ag_denetimi(lambda: [("DNS pypi.org", False, "gaierror"), ("HTTPS https://pypi.org/simple/", True, "200")])
    assert sonuc["kapali"] is False
    assert [d["basarili"] for d in sonuc["denemeler"]] == [False, True]


def test_ag_denetimi_denemeler_verilmezse_ag_kapali_mi_betigininkileri_kullanir(monkeypatch):
    """Dış ağ yerine standart kütüphanenin çıkış noktaları sahtelenir: hiçbir deneme dışarı çıkmaz."""
    import urllib.request

    def dns_yok(ad):
        raise socket.gaierror("ağ yok")

    def tcp_yok(*a, **k):
        raise OSError("ağ yok")

    class Acici:
        def open(self, *a, **k):
            raise urllib.error.URLError("ağ yok")

    monkeypatch.setattr(socket, "gethostbyname", dns_yok)
    monkeypatch.setattr(socket, "create_connection", tcp_yok)
    monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: Acici())
    sonuc = _dizustu().ag_denetimi()
    assert sonuc["kapali"] is True
    adlar = [d["deneme"] for d in sonuc["denemeler"]]
    assert "DNS pypi.org" in adlar and "TCP 1.1.1.1:443" in adlar
    assert any(a.startswith("HTTPS") for a in adlar)


# --- ollama_durumu ---------------------------------------------------------------


class _Cevap:
    def __init__(self, veri):
        self._govde = json.dumps(veri).encode("utf-8")
        self.status = 200

    def read(self, *a):
        return self._govde

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class SahteAcici:
    def __init__(self, yanitlar=None, hata=None):
        self.yanitlar = yanitlar or {}
        self.hata = hata
        self.istekler: list[tuple[str, object]] = []

    def open(self, url, timeout=None, **k):
        url = getattr(url, "full_url", url)
        self.istekler.append((url, timeout))
        if self.hata is not None:
            raise self.hata
        for son, veri in self.yanitlar.items():
            if url.endswith(son):
                return _Cevap(veri)
        raise urllib.error.HTTPError(url, 404, "yok", {}, None)


def test_ollama_durumu_surum_ve_model_adlarini_okur():
    acici = SahteAcici({"/api/version": {"version": "0.5.7"},
                        "/api/tags": {"models": [{"name": M15, "model": M15}, {"name": M3, "model": M3}]}})
    sonuc = _dizustu().ollama_durumu("http://127.0.0.1:11434", acici=acici)
    assert sonuc == {"surum": "0.5.7", "modeller": [M15, M3], "hata": None}
    urller = [u for u, _ in acici.istekler]
    assert "http://127.0.0.1:11434/api/version" in urller and "http://127.0.0.1:11434/api/tags" in urller
    assert all(t is not None for _, t in acici.istekler)  # her istek zaman aşımıyla yapılır


def test_ollama_durumu_sunucu_yoksa_hata_dolu_modeller_bos():
    acici = SahteAcici(hata=urllib.error.URLError(ConnectionRefusedError(111, "Connection refused")))
    sonuc = _dizustu().ollama_durumu("http://127.0.0.1:11434", acici=acici)
    assert sonuc["modeller"] == []
    assert sonuc["hata"]


@pytest.mark.parametrize("adres", ["http://example.com:11434", "http://192.168.1.10:11434", "ftp://localhost:11434"])
def test_ollama_durumu_yerel_olmayan_adresi_istek_yapmadan_reddeder(adres):
    acici = SahteAcici(hata=AssertionError("istek yapılmamalıydı"))
    with pytest.raises(ValueError):
        _dizustu().ollama_durumu(adres, acici=acici)
    assert acici.istekler == []


@pytest.fixture
def yerel_ollama():
    """127.0.0.1'de /api/version ve /api/tags dönen geçici sunucu."""

    class Isleyici(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            yanitlar = {"/api/version": {"version": "0.6.0"}, "/api/tags": {"models": [{"name": M3}]}}
            if self.path not in yanitlar:
                self.send_response(404)
                self.end_headers()
                return
            govde = json.dumps(yanitlar[self.path]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)

        def log_message(self, *a):
            pass

    sunucu = http.server.HTTPServer(("127.0.0.1", 0), Isleyici)
    is_ = threading.Thread(target=sunucu.serve_forever, daemon=True)
    is_.start()
    yield f"http://127.0.0.1:{sunucu.server_address[1]}"
    sunucu.shutdown()
    sunucu.server_close()


def test_ollama_durumu_varsayilan_acici_ile_yerel_sunucudan_okur(yerel_ollama):
    assert _dizustu().ollama_durumu(yerel_ollama) == {"surum": "0.6.0", "modeller": [M3], "hata": None}


def test_ollama_durumu_varsayilan_acici_ile_kapali_porta_hata_doner():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    sonuc = _dizustu().ollama_durumu(f"http://127.0.0.1:{port}")
    assert sonuc["modeller"] == [] and sonuc["hata"]


# --- model_var_mi ----------------------------------------------------------------


def test_model_var_mi_tam_eslesmeyi_bulur():
    assert _dizustu().model_var_mi(M3, [M15, M3]) is True


def test_model_var_mi_etiketsiz_ad_latest_ile_eslesir():
    assert _dizustu().model_var_mi("foo", ["foo:latest"]) is True


def test_model_var_mi_etiketli_ad_latest_eklenerek_eslesmez():
    assert _dizustu().model_var_mi("qwen2.5:3b", ["qwen2.5:3b:latest"]) is False


def test_model_var_mi_on_ek_eslesmesi_saymaz():
    assert _dizustu().model_var_mi("qwen2.5:3b", [M3]) is False
    assert _dizustu().model_var_mi("qwen2.5:1.5b", [M15, M3]) is False


def test_model_var_mi_bos_listede_yok():
    assert _dizustu().model_var_mi(M3, []) is False


# --- sistem_bilgisi --------------------------------------------------------------


def test_sistem_bilgisi_isletim_sistemi_python_islemci_ve_ram_icerir():
    bilgi = _dizustu().sistem_bilgisi()
    assert {"isletim_sistemi", "python", "islemci_sayisi", "ram_gb"} <= set(bilgi)
    assert isinstance(bilgi["isletim_sistemi"], str) and bilgi["isletim_sistemi"]
    assert isinstance(bilgi["python"], str) and bilgi["python"]
    assert bilgi["ram_gb"] is None or (isinstance(bilgi["ram_gb"], float) and bilgi["ram_gb"] > 0)
    json.dumps(bilgi)  # rapora yazılabilir


# --- olcum_yap: ön denetimler -----------------------------------------------------


def test_ag_aciksa_izin_yokken_agacik_yukselir_model_cagrilmaz_hicbir_sey_yazilmaz(tmp_path, kok):
    cikti = tmp_path / "cikti"
    uretici = IstemciUretici(CagrilmamaliIstemci)
    with pytest.raises(_dizustu().AgAcik):
        _olc(kok, cikti, uretici=uretici, ag=AgDenetleyici(kapali=False))
    assert uretici.modeller == []
    assert not cikti.exists()


def test_agacik_bir_istisna_sinifidir():
    assert issubclass(_dizustu().AgAcik, Exception)


def test_data_gold_altina_cikti_yazmadan_reddedilir(kok):
    hedef = GOLD / "dizustu_deneme"
    uretici = IstemciUretici(CagrilmamaliIstemci)
    with pytest.raises(ValueError):
        _olc(kok, hedef, uretici=uretici)
    assert uretici.modeller == []
    assert not hedef.exists()


def test_test_kumesindeki_belge_varsa_hicbir_model_cagrilmadan_reddedilir(tmp_path, kok):
    from deney.bolunme import TestKumesiKilitli

    cikti = tmp_path / "cikti"
    uretici = IstemciUretici(CagrilmamaliIstemci)
    # Geliştirme belgesi önde olsa bile kilitli belge ölçüm başlamadan yakalanır.
    with pytest.raises(TestKumesiKilitli):
        _olc(kok, cikti, belgeler=[_belge(kok, "MIL-PRF-23377K"), _belge(kok, "MIL-PRF-87937E")], uretici=uretici)
    assert all(i.cagrilar == 0 for i in uretici.istemciler)
    assert not cikti.exists() or list(cikti.rglob("*")) == []


def test_kilitli_klasordeki_belge_hicbir_model_cagrilmadan_reddedilir(tmp_path, kok):
    from deney.bolunme import TestKumesiKilitli

    kilitli = _pdf(kok / "data" / "raw" / "gercek_coc_havacilik" / "MIL-PRF-23377K.pdf", "MIL-PRF-23377K")
    cikti = tmp_path / "cikti"
    uretici = IstemciUretici(CagrilmamaliIstemci)
    with pytest.raises(TestKumesiKilitli):
        _olc(kok, cikti, belgeler=[kilitli], uretici=uretici)
    assert all(i.cagrilar == 0 for i in uretici.istemciler)
    assert not cikti.exists() or list(cikti.rglob("*")) == []


def test_ollama_da_olmayan_model_atlanir_istemcisi_uretilmez_pull_onerilir(tmp_path, kok):
    uretici = IstemciUretici()
    rapor = _olc(kok, tmp_path / "cikti", modeller=(M15, M3), uretici=uretici, ollama=_ollama(M3))
    assert uretici.modeller == [M3]
    assert [a["model"] for a in rapor["atlananlar"]] == [M15]
    assert f"ollama pull {M15}" in rapor["atlananlar"][0]["neden"]
    assert {s["model"] for s in rapor["satirlar"]} == {M3}


# --- olcum_yap: ölçüm ------------------------------------------------------------


def test_her_model_ve_belge_icin_uc_mod_ciktilari_model_klasorune_yazilir(tmp_path, kok):
    cikti = tmp_path / "cikti"
    _olc(kok, cikti, modeller=(M15, M3), belgeler=[_belge(kok, "MIL-PRF-23377K"), _belge(kok, "MIL-PRF-81733D")])
    for klasor in ("qwen2.5_1.5b-instruct-q4_K_M", M3_KLASOR):
        for etiket in ("MIL-PRF-23377K", "MIL-PRF-81733D"):
            for mod in MODLAR:
                assert (cikti / klasor / f"{etiket}_{mod}.json").is_file()
            assert (cikti / klasor / f"{etiket}_uc_mod_rapor.json").is_file()


def test_model_klasoru_adinda_iki_nokta_ve_egik_cizgi_alt_cizgi_olur(tmp_path, kok):
    cikti = tmp_path / "cikti"
    _olc(kok, cikti, modeller=("ekip/model:etiket",), ollama=_ollama("ekip/model:etiket"))
    assert (cikti / "ekip_model_etiket" / "MIL-PRF-23377K_hibrit.json").is_file()


def test_her_model_belge_ve_mod_icin_bir_satir_uretilir(tmp_path, kok):
    rapor = _olc(kok, tmp_path / "cikti", modeller=(M15, M3),
                 belgeler=[_belge(kok, "MIL-PRF-23377K"), _belge(kok, "MIL-PRF-81733D")])
    anahtarlar = sorted((s["model"], s["belge"], s["mod"]) for s in rapor["satirlar"])
    assert anahtarlar == sorted((m, b, mod) for m in (M15, M3) for b in ("MIL-PRF-23377K", "MIL-PRF-81733D")
                                for mod in MODLAR)
    for s in rapor["satirlar"]:
        assert set(s) == set(SATIR_SUTUNLARI)


def test_satir_sure_uc_mod_raporundan_gelir_sayfa_basi_sure_sayfa_sayisina_boluner(tmp_path, kok):
    cikti = tmp_path / "cikti"
    rapor = _olc(kok, cikti)
    uc_mod_rapor = json.loads((cikti / M3_KLASOR / "MIL-PRF-23377K_uc_mod_rapor.json").read_text(encoding="utf-8"))
    for s in rapor["satirlar"]:
        assert s["sayfa_sayisi"] == 2
        assert s["sure_s"] == pytest.approx(uc_mod_rapor["modlar"][s["mod"]]["sure_s"])
        assert s["test_sayisi"] == uc_mod_rapor["modlar"][s["mod"]]["test_sayisi"]
        assert s["sayfa_basi_s"] == pytest.approx(s["sure_s"] / 2, abs=1e-3)


def test_f1_kok_altindaki_gold_taslaktan_olculur_olmayan_gold_icin_none(tmp_path, kok):
    rapor = _olc(kok, tmp_path / "cikti", belgeler=[_belge(kok, "MIL-PRF-23377K"), _belge(kok, "MIL-PRF-81733D")])
    satir = {(s["belge"], s["mod"]): s for s in rapor["satirlar"]}
    # Gold kural çıktısının kendisi: kural tam isabet, dil modeli değil.
    assert satir[("MIL-PRF-23377K", "kural")]["f1_gold_taslak"] == pytest.approx(1.0)
    assert satir[("MIL-PRF-23377K", "dil_modeli")]["f1_gold_taslak"] < 1.0
    assert satir[("MIL-PRF-23377K", "kural")]["f1_gold_codex"] is None
    for mod in MODLAR:
        assert satir[("MIL-PRF-81733D", mod)]["f1_gold_taslak"] is None
        assert satir[("MIL-PRF-81733D", mod)]["f1_gold_codex"] is None


def test_model_yanit_hatasi_hatalara_yazilir_satir_uretilmez(tmp_path, kok):
    rapor = _olc(kok, tmp_path / "cikti", uretici=IstemciUretici(HataliIstemci))
    assert len(rapor["hatalar"]) == 1
    hata = rapor["hatalar"][0]
    assert hata["model"] == M3 and "MIL-PRF-23377K" in hata["belge"] and hata["hata"]
    assert [s for s in rapor["satirlar"] if s["mod"] == "dil_modeli"] == []


def test_bir_belgedeki_hata_sonrasi_kalan_belgelerle_devam_edilir(tmp_path, kok):
    # 23377K'nin gold'u bozuk: uc_mod ValueError verir; 81733D yine ölçülür.
    (kok / "data" / "gold_taslak" / "MIL-PRF-23377K.json").write_text("{yarim", encoding="utf-8")
    rapor = _olc(kok, tmp_path / "cikti", belgeler=[_belge(kok, "MIL-PRF-23377K"), _belge(kok, "MIL-PRF-81733D")])
    assert [h["model"] for h in rapor["hatalar"]] == [M3]
    assert "MIL-PRF-23377K" in rapor["hatalar"][0]["belge"]
    assert {s["belge"] for s in rapor["satirlar"]} == {"MIL-PRF-81733D"}


def test_ag_once_ve_sonra_denetlenir(tmp_path, kok):
    # Sözleşme değişikliği (ara ağ denetimi): önce 1 + her model x belge sonrası 1 + sonra 1.
    ag = AgDenetleyici(True)
    rapor = _olc(kok, tmp_path / "cikti", ag=ag)
    assert ag.cagri == 1 + 1 + 1
    assert rapor["ag_once"]["kapali"] is True and rapor["ag_sonra"]["kapali"] is True
    assert rapor["ag_once"]["denemeler"]


def test_ag_kapaliyken_tamamlanan_olcum_ag_kapali_calisti_sayilir(tmp_path, kok):
    rapor = _olc(kok, tmp_path / "cikti")
    assert rapor["ag_kapali_calisti"] is True


def test_ag_acikken_izinle_calisan_olcum_ag_kapali_calisti_sayilmaz(tmp_path, kok):
    rapor = _olc(kok, tmp_path / "cikti", ag=AgDenetleyici(False), ag_acik_izin=True)
    assert [s for s in rapor["satirlar"] if s["mod"] == "dil_modeli"]
    assert rapor["ag_kapali_calisti"] is False


def test_ag_sonradan_acilirsa_ag_kapali_calisti_sayilmaz(tmp_path, kok):
    # Sözleşme değişikliği (ara ağ denetimi): önce, ara (kapalı) ve sonra (açık) olmak üzere üç denetim.
    durumlar = iter([True, True, False])
    rapor = _olc(kok, tmp_path / "cikti", ag=lambda: _ag(next(durumlar)))
    assert rapor["ag_once"]["kapali"] is True and rapor["ag_sonra"]["kapali"] is False
    assert rapor["ag_kapali_calisti"] is False


def test_hicbir_dil_modeli_olcumu_tamamlanmazsa_ag_kapali_calisti_sayilmaz(tmp_path, kok):
    rapor = _olc(kok, tmp_path / "cikti", uretici=IstemciUretici(HataliIstemci))
    assert rapor["ag_kapali_calisti"] is False


def test_rapor_sistem_ve_ollama_bilgisini_icerir(tmp_path, kok):
    ollama = _ollama(M15, M3)
    rapor = _olc(kok, tmp_path / "cikti", ollama=ollama)
    assert rapor["ollama"] == ollama
    assert {"isletim_sistemi", "python", "islemci_sayisi", "ram_gb"} <= set(rapor["sistem"])


# --- olcum_yap: dosyalar ---------------------------------------------------------


def test_json_dosyasi_donen_raporla_ayni(tmp_path, kok):
    cikti = tmp_path / "cikti"
    rapor = _olc(kok, cikti)
    dosya = json.loads((cikti / "dizustu_olcum.json").read_text(encoding="utf-8"))
    assert dosya == json.loads(json.dumps(rapor, ensure_ascii=False))


def test_csv_satirlari_basliklariyla_yazar(tmp_path, kok):
    cikti = tmp_path / "cikti"
    rapor = _olc(kok, cikti)
    with open(cikti / "dizustu_olcum.csv", encoding="utf-8", newline="") as f:
        okuyucu = csv.DictReader(f)
        assert okuyucu.fieldnames == SATIR_SUTUNLARI
        satirlar = list(okuyucu)
    assert [(s["model"], s["belge"], s["mod"]) for s in satirlar] == [
        (s["model"], s["belge"], s["mod"]) for s in rapor["satirlar"]]


def test_md_tablosu_dil_modeli_ve_hibrit_ile_ag_kapali_durumunu_gosterir(tmp_path, kok):
    cikti = tmp_path / "cikti"
    _olc(kok, cikti, modeller=(M15, M3))
    md = (cikti / "dizustu_olcum.md").read_text(encoding="utf-8")
    assert "|" in md
    assert M15 in md and M3 in md and "MIL-PRF-23377K" in md
    assert "dil_modeli" in md or "dil modeli" in md.lower()
    assert "hibrit" in md.lower()
    assert "ağ kapalı" in md
    assert "AĞ AÇIK" not in md


def test_md_ag_acikken_ag_acik_yazar(tmp_path, kok):
    cikti = tmp_path / "cikti"
    _olc(kok, cikti, ag=AgDenetleyici(False), ag_acik_izin=True)
    assert "AĞ AÇIK" in (cikti / "dizustu_olcum.md").read_text(encoding="utf-8")


# --- main ------------------------------------------------------------------------


class _MainOrtami:
    def __init__(self):
        self.ag_kapali = True
        self.ollama = _ollama(M15, M3)
        self.ollama_adresleri: list[str] = []
        self.kurulanlar: list[dict] = []
        self.istemciler: list[SahteIstemci] = []
        self.hatali = False
        self.sayfa_hatasi: BaseException | None = None  # verilirse ısınma geçer, sayfa istekleri bununla düşer


@pytest.fixture
def ortam(monkeypatch):
    """main'in dış dünyası: ağ denetimi, Ollama durumu ve yerel model istemcisi sahte."""
    modul = _dizustu()
    o = _MainOrtami()

    def ag_denetimi(denemeler=None):
        return _ag(o.ag_kapali)

    def ollama_durumu(adres="http://127.0.0.1:11434", acici=None):
        o.ollama_adresleri.append(adres)
        return o.ollama

    class SahteYerel(SahteIstemci):
        def __init__(self, model, arka_uc="ollama", adres=None, baglam=8192, **k):
            super().__init__(model)
            self.arka_uc, self.adres, self.baglam = arka_uc, adres, baglam
            o.kurulanlar.append({"model": model, "adres": adres, "baglam": baglam, **k})
            o.istemciler.append(self)

        def sohbet(self, mesajlar, sema):
            if o.hatali:
                raise ModelYanitHatasi("bozuk yanıt")
            return super().sohbet(mesajlar, sema)

        def sayfa(self, mesajlar, sema):
            if o.sayfa_hatasi is not None:
                raise o.sayfa_hatasi
            return super().sayfa(mesajlar, sema)

    monkeypatch.setattr(modul, "ag_denetimi", ag_denetimi)
    monkeypatch.setattr(modul, "ollama_durumu", ollama_durumu)
    monkeypatch.setattr(modul, "YerelModelIstemcisi", SahteYerel)
    return o


def _main(kok, cikti, *ek, belgeler=None):
    belgeler = belgeler or [str(_belge(kok, "MIL-PRF-23377K"))]
    return _dizustu().main(["--modeller", M3, "--belgeler", *belgeler, "--cikti", str(cikti),
                            "--bolunme", str(_bolunme(kok)), *ek])


def test_main_ag_kapaliyken_basarili_olcumde_0_doner_ve_dosyalari_yazar(tmp_path, kok, ortam):
    cikti = tmp_path / "cikti"
    assert _main(kok, cikti) == 0
    for ad in ("dizustu_olcum.json", "dizustu_olcum.csv", "dizustu_olcum.md"):
        assert (cikti / ad).is_file()
    assert (cikti / M3_KLASOR / "MIL-PRF-23377K_hibrit.json").is_file()


def test_main_istemciyi_model_adres_ve_varsayilan_baglam_8192_ile_kurar(tmp_path, kok, ortam):
    adres = "http://127.0.0.1:11500"
    assert _main(kok, tmp_path / "cikti", "--adres", adres) == 0
    assert ortam.ollama_adresleri == [adres]
    assert [k["model"] for k in ortam.kurulanlar] == [M3]
    assert ortam.kurulanlar[0]["adres"] == adres
    assert ortam.kurulanlar[0]["baglam"] == 8192


def test_main_baglam_parametresi_istemciye_gecer(tmp_path, kok, ortam):
    assert _main(kok, tmp_path / "cikti", "--baglam", "4096") == 0
    assert ortam.kurulanlar[0]["baglam"] == 4096


def test_main_ag_acik_ve_izin_yoksa_3_doner_wifi_kapatmayi_soyler(tmp_path, kok, ortam, capsys):
    ortam.ag_kapali = False
    cikti = tmp_path / "cikti"
    assert _main(kok, cikti) == 3
    assert "Wi-Fi" in capsys.readouterr().err
    assert ortam.kurulanlar == []
    assert not cikti.exists()


def test_main_ag_acik_izinle_tamamlaninca_0_doner_ve_kanitlamaz_uyarisi_verir(tmp_path, kok, ortam, capsys):
    ortam.ag_kapali = False
    assert _main(kok, tmp_path / "cikti", "--ag-acik-izin") == 0
    assert "internetsiz çalışmayı kanıtlamaz" in capsys.readouterr().out


def test_main_ollamaya_ulasilamazsa_4_doner_ollama_serve_onerir(tmp_path, kok, ortam, capsys):
    ortam.ollama = {"surum": None, "modeller": [], "hata": "URLError: Connection refused"}
    assert _main(kok, tmp_path / "cikti") == 4
    assert "ollama serve" in capsys.readouterr().err
    assert ortam.kurulanlar == []


def test_main_test_kumesindeki_belge_icin_2_doner(tmp_path, kok, ortam):
    kod = _main(kok, tmp_path / "cikti", belgeler=[str(_belge(kok, "MIL-PRF-87937E"))])
    assert kod == 2
    assert all(i.cagrilar == 0 for i in ortam.istemciler)  # istemci kurulmuş olsa bile model çağrılmaz


def test_main_data_gold_altina_cikti_icin_2_doner(kok, ortam):
    hedef = GOLD / "dizustu_deneme"
    assert _main(kok, hedef) == 2
    assert not hedef.exists()


def test_main_butun_modeller_atlanirsa_1_doner_ve_pull_onerir(tmp_path, kok, ortam, capsys):
    ortam.ollama = _ollama()  # sunucu çalışıyor ama model yok
    kod = _dizustu().main(["--belgeler", str(_belge(kok, "MIL-PRF-23377K")), "--cikti", str(tmp_path / "cikti"),
                           "--bolunme", str(_bolunme(kok))])
    assert kod == 1
    cikis = capsys.readouterr()
    # --modeller verilmezse varsayılan iki model denenir.
    assert f"ollama pull {M15}" in cikis.out + cikis.err
    assert f"ollama pull {M3}" in cikis.out + cikis.err
    assert ortam.kurulanlar == []


def test_main_butun_olcumler_hatali_ise_1_doner(tmp_path, kok, ortam):
    ortam.hatali = True
    assert _main(kok, tmp_path / "cikti") == 1


# === Gözden geçirme düzeltmeleri ================================================


def _satir(rapor, mod, belge="MIL-PRF-23377K", model=M3):
    return next(s for s in rapor["satirlar"] if s["mod"] == mod and s["belge"] == belge and s["model"] == model)


def _md_oku(cikti: Path) -> str:
    return (cikti / "dizustu_olcum.md").read_text(encoding="utf-8")


# --- 1. Başarısız sayfa ----------------------------------------------------------


@pytest.mark.parametrize("sinif", [Http500Istemci, ZamanAsimiIstemci], ids=["http_500", "zaman_asimi"])
def test_istek_basarisiz_sayfalar_dil_modeli_ve_hibrit_satirinda_sayilir_kuralda_0(tmp_path, kok, sinif):
    rapor = _olc(kok, tmp_path / "cikti", uretici=IstemciUretici(sinif))
    assert _satir(rapor, "dil_modeli")["basarisiz_sayfa"] == 2
    assert _satir(rapor, "hibrit")["basarisiz_sayfa"] == 2
    assert _satir(rapor, "kural")["basarisiz_sayfa"] == 0


def test_yalniz_bir_sayfa_basarisizsa_basarisiz_sayfa_1(tmp_path, kok):
    class BirinciSayfaDuser(SahteIstemci):
        def sayfa(self, mesajlar, sema):
            if "sayfa 1." in mesajlar[1]["content"]:
                raise TimeoutError("timed out")
            return super().sayfa(mesajlar, sema)

    rapor = _olc(kok, tmp_path / "cikti", uretici=IstemciUretici(BirinciSayfaDuser))
    assert _satir(rapor, "dil_modeli")["basarisiz_sayfa"] == 1
    assert _satir(rapor, "hibrit")["basarisiz_sayfa"] == 1


def test_istek_hatasi_olmayan_sayfa_basarisiz_sayilmaz(tmp_path, kok):
    rapor = _olc(kok, tmp_path / "cikti")
    assert all(s["basarisiz_sayfa"] == 0 for s in rapor["satirlar"])


@pytest.mark.parametrize("sinif", [Http500Istemci, ZamanAsimiIstemci], ids=["http_500", "zaman_asimi"])
def test_basarisiz_sayfali_model_belge_hatalara_istek_basarisiz_ve_sayiyla_yazilir(tmp_path, kok, sinif):
    rapor = _olc(kok, tmp_path / "cikti", uretici=IstemciUretici(sinif))
    hatalar = [h for h in rapor["hatalar"] if h["belge"] is not None and "MIL-PRF-23377K" in h["belge"]]
    assert len(hatalar) == 1
    h = hatalar[0]
    assert set(h) == {"model", "belge", "hata"}
    assert h["model"] == M3
    assert "istek başarısız" in h["hata"] and "2" in h["hata"]


@pytest.mark.parametrize("sinif", [Http500Istemci, ZamanAsimiIstemci], ids=["http_500", "zaman_asimi"])
def test_butun_olcumlerde_basarisiz_sayfa_varsa_ag_kapali_calisti_sayilmaz(tmp_path, kok, sinif):
    rapor = _olc(kok, tmp_path / "cikti", uretici=IstemciUretici(sinif))
    assert rapor["ag_kapali_calisti"] is False


def test_basarisiz_sayfali_olcum_varken_tamamlanan_baska_olcum_ag_kapali_calisti_sayilir(tmp_path, kok):
    class Duser81733(SahteIstemci):
        def sayfa(self, mesajlar, sema):
            if "MIL-PRF-81733" in mesajlar[1]["content"]:
                raise _http_500()
            return super().sayfa(mesajlar, sema)

    rapor = _olc(kok, tmp_path / "cikti", uretici=IstemciUretici(Duser81733),
                 belgeler=[_belge(kok, "MIL-PRF-23377K"), _belge(kok, "MIL-PRF-81733D")])
    assert rapor["ag_kapali_calisti"] is True
    assert [("MIL-PRF-81733D" in (h["belge"] or "")) for h in rapor["hatalar"]] == [True]
    assert _satir(rapor, "dil_modeli", belge="MIL-PRF-81733D")["basarisiz_sayfa"] == 2
    assert _satir(rapor, "dil_modeli", belge="MIL-PRF-23377K")["basarisiz_sayfa"] == 0


def test_md_basarisiz_sayfali_satirlari_gecersiz_isaretler_digerlerini_isaretlemez(tmp_path, kok):
    class Duser81733(SahteIstemci):
        def sayfa(self, mesajlar, sema):
            if "MIL-PRF-81733" in mesajlar[1]["content"]:
                raise TimeoutError("timed out")
            return super().sayfa(mesajlar, sema)

    cikti = tmp_path / "cikti"
    _olc(kok, cikti, uretici=IstemciUretici(Duser81733),
         belgeler=[_belge(kok, "MIL-PRF-23377K"), _belge(kok, "MIL-PRF-81733D")])
    tablo = [s for s in _md_oku(cikti).splitlines() if s.startswith("|") and M3 in s]
    for mod in ("dil_modeli", "hibrit"):
        hatali = [s for s in tablo if "MIL-PRF-81733D" in s and f"| {mod} |" in s]
        saglam = [s for s in tablo if "MIL-PRF-23377K" in s and f"| {mod} |" in s]
        assert len(hatali) == 1 and "geçersiz" in hatali[0]
        assert len(saglam) == 1 and "geçersiz" not in saglam[0]


def test_csv_sona_basarisiz_ve_devam_edilen_sayfa_sutunlarini_ekler(tmp_path, kok):
    cikti = tmp_path / "cikti"
    _olc(kok, cikti, uretici=IstemciUretici(ZamanAsimiIstemci))
    with open(cikti / "dizustu_olcum.csv", encoding="utf-8", newline="") as f:
        okuyucu = csv.DictReader(f)
        assert okuyucu.fieldnames[-2:] == ["basarisiz_sayfa", "devam_edilen_sayfa"]
        satirlar = {s["mod"]: s for s in okuyucu}
    assert satirlar["dil_modeli"]["basarisiz_sayfa"] == "2"
    assert satirlar["kural"]["basarisiz_sayfa"] == "0"


@pytest.mark.parametrize("hata", [_http_500(), TimeoutError("timed out")], ids=["http_500", "zaman_asimi"])
def test_main_butun_sayfa_istekleri_basarisizsa_1_doner(tmp_path, kok, ortam, hata):
    ortam.sayfa_hatasi = hata
    cikti = tmp_path / "cikti"
    assert _main(kok, cikti) == 1
    assert json.loads((cikti / "dizustu_olcum.json").read_text(encoding="utf-8"))["ag_kapali_calisti"] is False


# --- 2. Devam eden çalışma ---------------------------------------------------------


def test_ilk_calismada_devam_edilen_sayfa_yok(tmp_path, kok):
    rapor = _olc(kok, tmp_path / "cikti")
    assert rapor["devam_edildi"] is False
    assert all(s["devam_edilen_sayfa"] == 0 for s in rapor["satirlar"])


def test_ayni_ciktiyla_ikinci_calisma_ara_kayittan_devam_eder_sayfa_istemez(tmp_path, kok):
    cikti = tmp_path / "cikti"
    _olc(kok, cikti)
    uretici = IstemciUretici()
    rapor = _olc(kok, cikti, uretici=uretici)
    assert [i.sayfa_cagrilari for i in uretici.istemciler] == [0]
    assert _satir(rapor, "dil_modeli")["devam_edilen_sayfa"] == 2
    assert _satir(rapor, "hibrit")["devam_edilen_sayfa"] == 2


def test_devam_edilen_calisma_devam_edildi_ve_ag_kapali_calisti_sayilmaz(tmp_path, kok):
    cikti = tmp_path / "cikti"
    _olc(kok, cikti)
    rapor = _olc(kok, cikti, ag=AgDenetleyici(True))
    assert rapor["devam_edildi"] is True
    assert rapor["ag_kapali_calisti"] is False


def test_md_devam_edildigini_ve_sifirdan_onerisini_yazar(tmp_path, kok):
    cikti = tmp_path / "cikti"
    _olc(kok, cikti)
    assert "--sifirdan" not in _md_oku(cikti)
    _olc(kok, cikti)
    assert "--sifirdan" in _md_oku(cikti)


def test_sifirdan_ara_kaydi_siler_istemci_yeniden_cagrilir_ag_kapali_calisti(tmp_path, kok):
    cikti = tmp_path / "cikti"
    _olc(kok, cikti)
    uretici = IstemciUretici()
    rapor = _olc(kok, cikti, uretici=uretici, sifirdan=True)
    assert [i.sayfa_cagrilari for i in uretici.istemciler] == [2]
    assert rapor["devam_edildi"] is False
    assert all(s["devam_edilen_sayfa"] == 0 for s in rapor["satirlar"])
    assert rapor["ag_kapali_calisti"] is True


def test_sifirdan_yalniz_olculen_model_belge_ara_klasorunu_siler(tmp_path, kok):
    cikti = tmp_path / "cikti"
    klasor = cikti / M3_KLASOR
    eski = klasor / "MIL-PRF-23377K_ara" / "eski.txt"
    baska_belge = klasor / "MIL-PRF-81733D_ara" / "sayfa_001.json"
    baska_dosya = klasor / "notlar.txt"
    baska_model = cikti / "qwen2.5_1.5b-instruct-q4_K_M" / "MIL-PRF-23377K_ara" / "sayfa_001.json"
    for yol in (eski, baska_belge, baska_dosya, baska_model):
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text("{}", encoding="utf-8")
    _olc(kok, cikti, sifirdan=True)
    assert not eski.exists()
    assert baska_belge.is_file() and baska_dosya.is_file() and baska_model.is_file()


def test_sifirdan_silme_hatasi_hatalara_yazilir_belge_atlanir_calisma_surer(tmp_path, kok, monkeypatch):
    """Windows'ta kilitli dosya rmtree'yi düşürürse çalışma çökmez; o belge hatalara yazılır."""
    cikti = tmp_path / "cikti"
    _olc(kok, cikti)
    gercek = shutil.rmtree

    def kilitli(yol, *a, **k):
        if Path(yol).name == "MIL-PRF-23377K_ara":
            raise PermissionError(32, "dosya başka bir işlem tarafından kullanılıyor")
        return gercek(yol, *a, **k)

    monkeypatch.setattr(shutil, "rmtree", kilitli)
    rapor = _olc(kok, cikti, sifirdan=True)
    assert any(h["belge"] and "MIL-PRF-23377K" in h["belge"] and "PermissionError" in h["hata"]
               for h in rapor["hatalar"])
    assert not any(s["belge"] == "MIL-PRF-23377K" and s["mod"] == "dil_modeli" for s in rapor["satirlar"])
    assert (cikti / "dizustu_olcum.json").is_file()


def test_sifirdan_varsayilani_false(tmp_path, kok):
    import inspect

    assert inspect.signature(_dizustu().olcum_yap).parameters["sifirdan"].default is False


def test_main_sifirdan_secenegi_ara_kaydi_silip_yeniden_olcer(tmp_path, kok, ortam):
    cikti = tmp_path / "cikti"
    assert _main(kok, cikti) == 0
    ortam.istemciler.clear()
    assert _main(kok, cikti) == 0  # devam eder: sayfa istenmez
    assert [i.sayfa_cagrilari for i in ortam.istemciler] == [0]
    assert json.loads((cikti / "dizustu_olcum.json").read_text(encoding="utf-8"))["ag_kapali_calisti"] is False
    ortam.istemciler.clear()
    assert _main(kok, cikti, "--sifirdan") == 0
    assert [i.sayfa_cagrilari for i in ortam.istemciler] == [2]
    assert json.loads((cikti / "dizustu_olcum.json").read_text(encoding="utf-8"))["ag_kapali_calisti"] is True


# --- 3. Ara ağ denetimi ----------------------------------------------------------


def test_ag_her_model_belge_sonrasinda_da_denetlenir(tmp_path, kok):
    ag = AgDenetleyici(True)
    rapor = _olc(kok, tmp_path / "cikti", ag=ag, modeller=(M15, M3),
                 belgeler=[_belge(kok, "MIL-PRF-23377K"), _belge(kok, "MIL-PRF-81733D")])
    assert ag.cagri == 1 + 2 * 2 + 1
    assert len(rapor["ag_ara"]) == 4
    assert all(a["kapali"] is True and a["denemeler"] for a in rapor["ag_ara"])


def test_olcum_ortasinda_ag_acilirsa_ag_kapali_calisti_sayilmaz_md_ag_acik_yazar(tmp_path, kok):
    cikti = tmp_path / "cikti"
    rapor = _olc(kok, cikti, ag=SiraliAgDenetleyici(True, False, True))
    assert rapor["ag_once"]["kapali"] is True and rapor["ag_sonra"]["kapali"] is True
    assert [a["kapali"] for a in rapor["ag_ara"]] == [False]
    assert rapor["ag_kapali_calisti"] is False
    assert "AĞ AÇIK" in _md_oku(cikti)


def test_ag_hep_kapaliysa_ara_denetimlerle_ag_kapali_calisti(tmp_path, kok):
    rapor = _olc(kok, tmp_path / "cikti", ag=SiraliAgDenetleyici(True))
    assert [a["kapali"] for a in rapor["ag_ara"]] == [True]
    assert rapor["ag_kapali_calisti"] is True


# --- 4. Dizüstü ag_denetimi: vekil ------------------------------------------------


def test_ag_denetimi_varsayilanda_vekil_dahil_ister_ve_vekil_ayarini_ekler(monkeypatch):
    modul = _dizustu()
    cagrilar = []

    def denemeler(*a, **k):
        cagrilar.append((a, k))
        return [("DNS pypi.org", False, "gaierror")]

    vekil = {"https": "http://vekil.ornek:8080"}
    monkeypatch.setattr(modul, "_ag_betigi", lambda: types.SimpleNamespace(denemeler=denemeler))
    monkeypatch.setattr(urllib.request, "getproxies", lambda: dict(vekil))
    sonuc = modul.ag_denetimi()
    assert cagrilar == [((), {"vekil_dahil": True})]
    assert sonuc["vekil"] == vekil
    assert sonuc["kapali"] is True


def test_ag_denetimi_vekil_yoksa_bos_sozluk_yazar(monkeypatch):
    modul = _dizustu()
    monkeypatch.setattr(modul, "_ag_betigi",
                        lambda: types.SimpleNamespace(denemeler=lambda **k: [("DNS pypi.org", False, "gaierror")]))
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    assert modul.ag_denetimi()["vekil"] == {}


# --- 5. Model adı yedekleri ------------------------------------------------------


def test_yedek_adlar_sozlugu():
    assert _dizustu().YEDEK_ADLAR == {
        M15: ("qwen2.5:1.5b", "qwen2.5:1.5b-instruct"),
        M3: ("qwen2.5:3b", "qwen2.5:3b-instruct"),
    }


def test_model_coz_tam_ad_varsa_onu_doner():
    assert _dizustu().model_coz(M3, ["qwen2.5:3b", M3]) == M3


@pytest.mark.parametrize("model,mevcut,beklenen", [
    (M15, ["qwen2.5:1.5b"], "qwen2.5:1.5b"),
    (M15, ["qwen2.5:1.5b-instruct"], "qwen2.5:1.5b-instruct"),
    (M15, ["qwen2.5:1.5b-instruct", "qwen2.5:1.5b"], "qwen2.5:1.5b"),  # yedeklerin sırası belirler
    (M3, ["qwen2.5:3b"], "qwen2.5:3b"),
    (M3, ["qwen2.5:1.5b", "qwen2.5:3b-instruct"], "qwen2.5:3b-instruct"),
])
def test_model_coz_tam_ad_yoksa_mevcuttaki_ilk_yedegi_doner(model, mevcut, beklenen):
    assert _dizustu().model_coz(model, mevcut) == beklenen


@pytest.mark.parametrize("model,mevcut", [
    (M3, []),
    (M3, ["qwen2.5:1.5b", "qwen2.5:7b"]),  # başka modelin yedeği sayılmaz
    (M3, ["qwen2.5:3b-instruct-q8_0"]),     # ön ek eşleşmesi sayılmaz
    ("llama3.2:3b", ["qwen2.5:3b"]),        # yedeği tanımlı olmayan model
])
def test_model_coz_ne_tam_ad_ne_yedek_varsa_none(model, mevcut):
    assert _dizustu().model_coz(model, mevcut) is None


def test_istemci_cozulen_adla_uretilir_satirlarda_istenen_ad_kalir(tmp_path, kok):
    uretici = IstemciUretici()
    rapor = _olc(kok, tmp_path / "cikti", uretici=uretici, ollama=_ollama("qwen2.5:3b"))
    assert uretici.modeller == ["qwen2.5:3b"]
    assert {s["model"] for s in rapor["satirlar"]} == {M3}
    assert rapor["model_eslesmeleri"] == {M3: "qwen2.5:3b"}
    assert rapor["atlananlar"] == []


def test_model_eslesmeleri_tam_adda_kendisidir(tmp_path, kok):
    rapor = _olc(kok, tmp_path / "cikti", modeller=(M15, M3), ollama=_ollama(M3, "qwen2.5:1.5b-instruct"))
    assert rapor["model_eslesmeleri"] == {M3: M3, M15: "qwen2.5:1.5b-instruct"}


def test_ne_tam_ad_ne_yedek_varsa_atlanir_pull_onerilir(tmp_path, kok):
    uretici = IstemciUretici()
    rapor = _olc(kok, tmp_path / "cikti", uretici=uretici, ollama=_ollama("qwen2.5:7b"))
    assert uretici.modeller == []
    assert [a["model"] for a in rapor["atlananlar"]] == [M3]
    assert "ollama pull" in rapor["atlananlar"][0]["neden"]


# --- 6. Isınma -------------------------------------------------------------------


def test_isinma_belgelerden_once_bir_kez_system_ve_user_mesajiyla_yapilir(tmp_path, kok):
    uretici = IstemciUretici()
    _olc(kok, tmp_path / "cikti", uretici=uretici,
         belgeler=[_belge(kok, "MIL-PRF-23377K"), _belge(kok, "MIL-PRF-81733D")])
    istemci = uretici.istemciler[0]
    isinmalar = [i for i, (m, _) in enumerate(istemci.mesajlar) if _isinma_mi(m)]
    assert isinmalar == [0]
    mesajlar, sema = istemci.mesajlar[0]
    assert [m["role"] for m in mesajlar] == ["system", "user"]
    assert all(isinstance(m["content"], str) and m["content"] for m in mesajlar)
    assert sema == {"type": "object"}
    assert istemci.sayfa_cagrilari == 4


def test_isinma_suresi_her_model_icin_yukleme_s_e_yazilir(tmp_path, kok):
    rapor = _olc(kok, tmp_path / "cikti", modeller=(M15, M3))
    assert set(rapor["yukleme_s"]) == {M15, M3}
    assert all(isinstance(v, float) and v >= 0 for v in rapor["yukleme_s"].values())


@pytest.mark.parametrize("hata", [
    TimeoutError("timed out"),
    ConnectionRefusedError(111, "Connection refused"),
    http.client.RemoteDisconnected("kapandı"),
    ValueError("bozuk json"),
    ModelYanitHatasi("beklenmedik yanıt"),
], ids=["zaman_asimi", "baglanti", "http_exception", "value_error", "model_yanit"])
def test_isinma_hatasinda_model_hatalara_belgesiz_yazilir_belgeleri_olculmez(tmp_path, kok, hata):
    class IsinmadaDuser(SahteIstemci):
        def isinma(self, mesajlar, sema):
            raise hata

    uretici = IstemciUretici(IsinmadaDuser)
    rapor = _olc(kok, tmp_path / "cikti", uretici=uretici,
                 belgeler=[_belge(kok, "MIL-PRF-23377K"), _belge(kok, "MIL-PRF-81733D")])
    assert [(h["model"], h["belge"]) for h in rapor["hatalar"]] == [(M3, None)]
    assert rapor["hatalar"][0]["hata"]
    assert rapor["satirlar"] == []
    assert [i.cagrilar for i in uretici.istemciler] == [1]
    assert rapor["ag_kapali_calisti"] is False


def test_bir_modelin_isinma_hatasi_obur_modeli_durdurmaz(tmp_path, kok):
    class IsinmadaDuser(SahteIstemci):
        def isinma(self, mesajlar, sema):
            raise TimeoutError("timed out")

    class Uretici(IstemciUretici):
        def __call__(self, model):
            self.sinif = IsinmadaDuser if model == M15 else SahteIstemci
            return super().__call__(model)

    rapor = _olc(kok, tmp_path / "cikti", modeller=(M15, M3), uretici=Uretici())
    assert [(h["model"], h["belge"]) for h in rapor["hatalar"]] == [(M15, None)]
    assert {s["model"] for s in rapor["satirlar"]} == {M3}
    assert rapor["ag_kapali_calisti"] is True


# --- 7. Yardımcılar --------------------------------------------------------------


def _meminfo(tmp_path, kb: int) -> Path:
    yol = tmp_path / "meminfo"
    yol.write_text(f"MemTotal:        {kb} kB\nMemFree:          123456 kB\n", encoding="utf-8")
    return yol


def test_ram_gb_meminfo_dosyasindan_bir_ondalik_gib_okur(tmp_path):
    assert _dizustu()._ram_gb(meminfo=_meminfo(tmp_path, 8070000)) == 7.7


def test_ram_gb_bir_ondaliga_yuvarlar(tmp_path):
    # 8000000 kB = 7.629 GiB: iki ondalıkta 7.63, bir ondalıkta 7.6.
    assert _dizustu()._ram_gb(meminfo=_meminfo(tmp_path, 8000000)) == 7.6


def test_ram_gb_dosya_yok_windll_yoksa_none(tmp_path):
    assert _dizustu()._ram_gb(meminfo=tmp_path / "yok", windll=None) is None


class _SahteKernel32:
    def __init__(self, toplam: int, donus: int = 1):
        self.toplam, self.donus = toplam, donus
        self.cagri = 0

    def GlobalMemoryStatusEx(self, arg):  # noqa: N802
        self.cagri += 1
        durum = arg._obj if hasattr(arg, "_obj") else arg.contents  # byref ya da pointer
        durum.ullTotalPhys = self.toplam
        return self.donus


def test_ram_gb_windll_ile_globalmemorystatusex_ten_gib_okur(tmp_path):
    windll = types.SimpleNamespace(kernel32=_SahteKernel32(8_000_000_000))  # 7.45 GiB
    assert _dizustu()._ram_gb(meminfo=tmp_path / "yok", windll=windll) == 7.5
    assert windll.kernel32.cagri == 1


def test_ram_gb_windll_verilince_meminfodan_once_denenir(tmp_path):
    windll = types.SimpleNamespace(kernel32=_SahteKernel32(16 * 1024**3))
    assert _dizustu()._ram_gb(meminfo=_meminfo(tmp_path, 8070000), windll=windll) == 16.0


def test_model_klasoru_windowsta_gecersiz_butun_karakterleri_alt_cizgi_yapar():
    assert _dizustu()._model_klasoru('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"


@pytest.mark.parametrize("karakter", list('<>:"/\\|?*'))
def test_model_klasoru_her_gecersiz_karakteri_tek_tek_alt_cizgi_yapar(karakter):
    assert _dizustu()._model_klasoru(f"m{karakter}x") == "m_x"


# --- 8. main: dar kodlamalı konsol ---------------------------------------------------


def test_main_cp1252_konsolda_ag_acik_yolunda_unicode_hatasi_vermez(tmp_path, kok, ortam, monkeypatch):
    ortam.ag_kapali = False
    konsol = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", konsol)
    assert _main(kok, tmp_path / "cikti", "--ag-acik-izin") == 0
    konsol.flush()
    assert konsol.buffer.getvalue()  # çıktı yazıldı (sığmayan harfler yerine '?')
