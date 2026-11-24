"""Yerel dil modeli istemcisinin ve şemaya zorlanmış çıkarmanın testleri.

Gerçek model çalıştırılmaz: HTTP istemcisi 127.0.0.1 üzerinde açılan sahte bir
sunucuyla, çıkarma akışı da sahte bir istemciyle denenir.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from conftest import betik_yukle

from malzeme_kabul.belge.pdf_okuyucu import Belge, Sayfa
from malzeme_kabul.sozlesme.sema import KabulDokumani, TestSarti
from malzeme_kabul.cikarim.yerel_model import YerelModelIstemcisi, adres_yerel_mi, istek_govdesi, yanit_metni
from deney.yalniz_dil_modeli import CikarimYaniti, belgeden_cikar, cikarim_semasi, istem_olustur, yaniti_coz


def _test_json(id_="viskozite", madde="3.6.3", birim="s", sayfa=7) -> dict:
    return {
        "id": id_,
        "test_adi": "Viscosity",
        "test_metodu": "ASTM D1200",
        "sinir": {
            "kriter_turu": "sayisal",
            "alt": 15,
            "ust": 30,
            "birim": birim,
            "orijinal_metin": "The viscosity shall be 15 to 30 seconds.",
        },
        "kaynak": {"belge_no": "MIL-PRF-23377", "revizyon": "K", "madde": madde, "sayfa": sayfa},
        "test_turleri": ["kabul", "yeterlilik"],
    }


# --- Adres denetimi --------------------------------------------------------------


@pytest.mark.parametrize(
    "adres", ["http://localhost:11434", "http://127.0.0.1:8080", "http://[::1]:11434/"]
)
def test_yerel_adres_kabul_edilir(adres):
    assert adres_yerel_mi(adres)


@pytest.mark.parametrize(
    "adres",
    ["https://api.example.com", "http://192.168.1.5:11434", "http://localhost.evil.com", "ftp://localhost", ""],
)
def test_yerel_olmayan_adres_reddedilir(adres):
    assert not adres_yerel_mi(adres)


def test_istemci_yerel_olmayan_adresi_reddeder():
    with pytest.raises(ValueError, match="localhost"):
        YerelModelIstemcisi(model="m", adres="http://10.0.0.2:11434")


def test_istemci_bilinmeyen_arka_ucu_reddeder():
    with pytest.raises(ValueError, match="arka uç"):
        YerelModelIstemcisi(model="m", arka_uc="bulut")


@pytest.mark.parametrize(("arka_uc", "port"), [("ollama", 11434), ("llamacpp", 8080)])
def test_istemci_varsayilan_adresi_yereldir(arka_uc, port):
    istemci = YerelModelIstemcisi(model="m", arka_uc=arka_uc)
    assert istemci.adres == f"http://localhost:{port}"


# --- Şema ve istem ----------------------------------------------------------------


def test_cikarim_semasi_test_sarti_semasini_kullanir():
    sema = cikarim_semasi()
    assert sema["required"] == ["testler"]
    assert sema["properties"]["testler"]["type"] == "array"
    assert "TestSarti" in sema["$defs"]
    assert sema["$defs"]["TestSarti"]["additionalProperties"] is False
    json.dumps(sema)  # JSON'a çevrilebilmeli


def test_cikarim_yaniti_fazla_alani_reddeder():
    with pytest.raises(ValueError):
        CikarimYaniti.model_validate({"testler": [], "fazla": 1})


def test_istem_sayfa_ve_belge_bilgisini_icerir():
    mesajlar = istem_olustur("3.6.3 Viscosity. 15 to 30 seconds.", sayfa_no=7, belge_no="MIL-PRF-23377", revizyon="K")
    assert [m["role"] for m in mesajlar] == ["system", "user"]
    kullanici = mesajlar[1]["content"]
    assert "3.6.3 Viscosity" in kullanici
    assert "sayfa 7." in kullanici and "sayfa=7" in kullanici and "MIL-PRF-23377" in kullanici and '"K"' in kullanici
    # Dil modeli yalnız okur: birim dönüşümü ve karşılaştırma ona yaptırılmaz.
    assert "dönüştürme" in mesajlar[0]["content"]


def test_ollama_istek_govdesi_semayi_format_olarak_verir():
    sema = cikarim_semasi()
    yol, govde = istek_govdesi("ollama", "qwen2.5:7b", [{"role": "user", "content": "x"}], sema,
                               sicaklik=0.0, baglam=8192, en_cok_token=2048)
    assert yol == "/api/chat"
    assert govde["format"] == sema
    assert govde["stream"] is False
    assert govde["options"] == {"temperature": 0.0, "num_ctx": 8192, "num_predict": 2048}
    assert "think" not in govde


def test_ollama_istek_govdesi_dusunmeyi_kapatabilir():
    _, govde = istek_govdesi("ollama", "qwen3:8b", [], {}, dusunme=False)
    assert govde["think"] is False


def test_llamacpp_istek_govdesi_json_schema_kullanir():
    sema = cikarim_semasi()
    yol, govde = istek_govdesi("llamacpp", "yerel", [], sema, sicaklik=0.0, en_cok_token=1024)
    assert yol == "/v1/chat/completions"
    assert govde["response_format"]["type"] == "json_schema"
    assert govde["response_format"]["json_schema"]["schema"] == sema
    assert govde["temperature"] == 0.0 and govde["max_tokens"] == 1024


def test_yanit_metni_iki_arka_uc_icin():
    assert yanit_metni("ollama", {"message": {"content": "{}"}}) == "{}"
    assert yanit_metni("llamacpp", {"choices": [{"message": {"content": "[]"}}]}) == "[]"


# --- Yanıtı çözme ----------------------------------------------------------------


def test_gecerli_yanit_test_sartlarina_cozulur():
    testler, hatalar = yaniti_coz(json.dumps({"testler": [_test_json()]}))
    assert hatalar == []
    assert len(testler) == 1 and isinstance(testler[0], TestSarti)
    assert testler[0].sinir.alt == 15 and testler[0].sinir.birim == "s"


def test_gecersiz_test_atlanir_digerleri_korunur():
    bozuk = _test_json(id_="bozuk", birim="saniyecik")  # pint tanımaz
    testler, hatalar = yaniti_coz(json.dumps({"testler": [bozuk, _test_json()]}))
    assert [t.id for t in testler] == ["viskozite"]
    assert len(hatalar) == 1 and "bozuk" in hatalar[0]


@pytest.mark.parametrize("metin", ["", "{yarim", "[]", '{"baska": 1}', '{"testler": 3}'])
def test_cozulemeyen_yanit_hata_olarak_doner(metin):
    testler, hatalar = yaniti_coz(metin)
    assert testler == [] and len(hatalar) == 1


# --- HTTP istemcisi (sahte yerel sunucu) -----------------------------------------


@pytest.fixture
def sahte_sunucu():
    """127.0.0.1'de çalışan, Ollama ya da llama.cpp gibi yanıt veren sunucu."""
    kayit: dict = {}

    class Isleyici(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            if self.path.startswith("/yonlendir"):
                self.send_response(307)
                self.send_header("Location", "http://example.com/api/chat")
                self.end_headers()
                return
            uzunluk = int(self.headers["Content-Length"])
            kayit["yol"] = self.path
            kayit["govde"] = json.loads(self.rfile.read(uzunluk))
            icerik = json.dumps({"testler": [_test_json()]})
            if self.path == "/api/chat":
                yanit = {"message": {"role": "assistant", "content": icerik}}
            else:
                yanit = {"choices": [{"message": {"role": "assistant", "content": icerik}}]}
            veri = json.dumps(yanit).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(veri)))
            self.end_headers()
            self.wfile.write(veri)

        def log_message(self, *args):
            pass

    sunucu = ThreadingHTTPServer(("127.0.0.1", 0), Isleyici)
    is_parcacigi = threading.Thread(target=sunucu.serve_forever, daemon=True)
    is_parcacigi.start()
    yield f"http://127.0.0.1:{sunucu.server_address[1]}", kayit
    sunucu.shutdown()
    sunucu.server_close()


@pytest.mark.parametrize("arka_uc", ["ollama", "llamacpp"])
def test_istemci_yerel_sunucuya_semayla_istek_atar(sahte_sunucu, arka_uc):
    adres, kayit = sahte_sunucu
    istemci = YerelModelIstemcisi(model="deneme", arka_uc=arka_uc, adres=adres)
    metin = istemci.sohbet([{"role": "user", "content": "oku"}], cikarim_semasi())
    assert json.loads(metin)["testler"][0]["id"] == "viskozite"
    assert kayit["govde"]["model"] == "deneme"
    assert kayit["yol"] == ("/api/chat" if arka_uc == "ollama" else "/v1/chat/completions")


def test_istemci_yonlendirmeyi_izlemez(sahte_sunucu):
    adres, _ = sahte_sunucu
    istemci = YerelModelIstemcisi(model="deneme", adres=adres + "/yonlendir")
    with pytest.raises(ValueError, match="yönlendirme"):
        istemci.sohbet([{"role": "user", "content": "oku"}], {})


# --- Belgeden çıkarma akışı ------------------------------------------------------


class SahteIstemci:
    """Sayfa numarasına göre hazır yanıt döner; çağrıları kaydeder."""

    def __init__(self, yanitlar: dict[int, str]):
        self.yanitlar = yanitlar
        self.cagrilar: list[list[dict]] = []

    def sohbet(self, mesajlar, sema):
        self.cagrilar.append(mesajlar)
        for sayfa_no, yanit in self.yanitlar.items():
            if f"sayfa {sayfa_no}." in mesajlar[1]["content"]:
                if isinstance(yanit, Exception):
                    raise yanit
                return yanit
        return json.dumps({"testler": []})


def _belge() -> Belge:
    return Belge(
        dosya="sahte.pdf",
        sayfalar=[
            Sayfa(1, "MIL-PRF-23377K\n1. SCOPE"),
            Sayfa(2, ""),  # taranmış ya da boş sayfa: modele gönderilmez
            Sayfa(3, "3.6.3 Viscosity (cid:113)C"),
            Sayfa(4, "TABLE II"),
        ],
    )


def test_belgeden_cikar_sayfalari_birlestirir_ve_rapor_uretir():
    t = _test_json()
    t["numune_hazirlama_id"] = "panel_A"  # numune listesi çıkarılmadığı için düşürülür
    istemci = SahteIstemci({
        3: json.dumps({"testler": [t]}),
        4: json.dumps({"testler": [_test_json(madde="TABLE II"), _test_json(id_="yogunluk", madde="3.6.4")]}),
    })
    dokuman, rapor = belgeden_cikar(_belge(), "MIL-PRF-23377", "K", istemci)

    assert isinstance(dokuman, KabulDokumani)
    assert dokuman.standart.belge_no == "MIL-PRF-23377" and dokuman.standart.revizyon == "K"
    assert [t.id for t in dokuman.testler] == ["viskozite", "yogunluk"]
    assert dokuman.testler[0].kaynak.madde == "3.6.3"  # ilk görülen korunur
    assert dokuman.testler[0].numune_hazirlama_id is None
    # Model sayfa 7 yazdı ama şart 3. sayfadan okundu: kaynak sayfası koddan gelir.
    assert dokuman.testler[0].kaynak.sayfa == 3 and dokuman.testler[1].kaynak.sayfa == 4

    assert len(istemci.cagrilar) == 3  # boş sayfa atlandı
    assert "°C" in istemci.cagrilar[1][1]["content"]  # glif kodu düzeltildi

    assert [s.sayfa for s in rapor.sayfalar] == [1, 3, 4]
    assert rapor.tekrar_edenler == ["viskozite"]
    assert rapor.test_sayisi == 2
    assert rapor.toplam_sure_s >= 0
    ozet = rapor.sozluk()
    assert ozet["test_sayisi"] == 2 and len(ozet["sayfalar"]) == 3
    json.dumps(ozet)


def test_belgeden_cikar_sayfa_hatasini_kaydedip_devam_eder():
    istemci = SahteIstemci({1: TimeoutError("zaman aşımı"), 3: "{bozuk", 4: json.dumps({"testler": [_test_json()]})})
    dokuman, rapor = belgeden_cikar(_belge(), "MIL-PRF-23377", "K", istemci)
    assert [t.id for t in dokuman.testler] == ["viskozite"]
    hatali = {s.sayfa: s.hatalar for s in rapor.sayfalar if s.hatalar}
    assert set(hatali) == {1, 3}
    assert "zaman aşımı" in hatali[1][0]


def test_belgeden_cikar_yalniz_istenen_sayfalari_okur():
    istemci = SahteIstemci({})
    _, rapor = belgeden_cikar(_belge(), "MIL-PRF-23377", "K", istemci, sayfalar={3})
    assert [s.sayfa for s in rapor.sayfalar] == [3]


# --- Komut satırı betiği ----------------------------------------------------------


def test_betik_sayfa_araligini_cozer():
    betik = betik_yukle("deney/dil_modeli_cikar.py")
    assert betik.sayfa_araligi("3-5,8") == {3, 4, 5, 8}
    with pytest.raises(ValueError):
        betik.sayfa_araligi("5-3")


def test_betik_model_adini_dosya_adina_cevirir():
    betik = betik_yukle("deney/dil_modeli_cikar.py")
    assert betik.dosya_eki("qwen2.5:7b-instruct-q4_K_M") == "qwen2.5_7b-instruct-q4_K_M"


def test_betik_sahte_sunucuyla_cikti_yazar(sahte_sunucu, tmp_path):
    from pdf_uretici import pdf_yaz

    adres, _ = sahte_sunucu
    pdf = tmp_path / "MIL-PRF-23377K.pdf"
    pdf_yaz(pdf, [{"metin": ["3.6.3 Viscosity. The viscosity shall be 15 to 30 seconds."]}])
    betik = betik_yukle("deney/dil_modeli_cikar.py")
    kod = betik.main([str(pdf), "--model", "deneme:7b", "--adres", adres, "--cikti", str(tmp_path / "cikti")])
    assert kod == 0
    dokuman = KabulDokumani.model_validate_json(
        (tmp_path / "cikti" / "MIL-PRF-23377K_dil_modeli_deneme_7b.json").read_text(encoding="utf-8")
    )
    assert [t.id for t in dokuman.testler] == ["viskozite"]
    rapor = json.loads((tmp_path / "cikti" / "MIL-PRF-23377K_dil_modeli_deneme_7b_rapor.json").read_text())
    assert rapor["model"] == "deneme:7b" and rapor["arka_uc"] == "ollama" and rapor["test_sayisi"] == 1
