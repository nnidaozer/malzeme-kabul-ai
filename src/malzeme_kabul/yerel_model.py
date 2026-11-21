"""Yerel dil modeliyle şemaya zorlanmış çıkarma.

Dil modeli yalnızca belgeden değer okur (CLAUDE.md, kural 1). Her sayfa metni
modele verilir; model, `TestSarti` şemasına zorlanmış JSON döner. Çözülen
şartlar Pydantic ile doğrulanır; geçmeyenler atılır ve rapora yazılır. Birim
dönüşümü ve sınır karşılaştırması burada yapılmaz.

İstemci yalnızca localhost'a bağlanır (CLAUDE.md, kural 4). İki yerel sunucu
desteklenir:

- Ollama: /api/chat, şema `format` alanında verilir.
- llama.cpp (llama-server): /v1/chat/completions, şema `response_format`
  içinde `json_schema` olarak verilir.

İki sunucu da şemayı dilbilgisine (grammar) çevirip üretimi buna zorlar; yine
de çıktı ayrıca doğrulanır, çünkü şemanın bazı kuralları (pint birimi, madde
biçimi) yalnız Pydantic doğrulayıcılarında vardır.
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, ValidationError

from .kural_cikarici import metni_normallestir
from .pdf_okuyucu import Belge
from .sema import KabulDokumani, StandartBilgisi, TestSarti

ARKA_UCLAR = {
    "ollama": ("http://localhost:11434", "/api/chat"),
    "llamacpp": ("http://localhost:8080", "/v1/chat/completions"),
}
YEREL_ADRESLER = {"localhost", "127.0.0.1", "::1"}

Mesaj = dict[str, str]


def adres_yerel_mi(adres: str) -> bool:
    """Adres http(s) ile bu makineye (localhost) mı gidiyor?"""
    try:
        parca = urlparse(adres)
    except ValueError:
        return False
    return parca.scheme in {"http", "https"} and parca.hostname in YEREL_ADRESLER


# --- Şema ve istem ----------------------------------------------------------------


class CikarimYaniti(BaseModel):
    """Modelin bir sayfa için döndüğü yanıt: o sayfadaki test şartları."""

    model_config = ConfigDict(extra="forbid")

    testler: list[TestSarti]


def cikarim_semasi() -> dict[str, Any]:
    """Modelin çıktısını zorlayan JSON şeması (`CikarimYaniti`)."""
    return CikarimYaniti.model_json_schema()


_SISTEM = """Sen bir askeri malzeme standardından test şartlarını okuyan bir yardımcısın.
Görevin yalnızca okumak: sayfada yazan test adını, test metodunu, sınır değerlerini,
birimi ve madde numarasını olduğu gibi aktar.

Kurallar:
- Birimi dönüştürme, değerleri hesaplama ya da karşılaştırma yapma. Sayıyı sayfada
  yazdığı gibi, birimi pint biçiminde yaz (ör. "s", "minute", "hour", "°C", "g/L",
  "%", "ppm", "mil", "µm").
- "en az" yalnız alt sınır, "en çok"/"not greater than" yalnız üst sınırdır.
  Sayısal sınır yoksa kriter_turu "gecti_kaldi" ya da "metinsel" olur ve alt, ust,
  birim boş kalır.
- orijinal_metin alanına standarttaki kriter cümlesini aynen yaz.
- kaynak.madde, şartın yazdığı madde numarasıdır (ör. "3.6.3" ya da "TABLE I").
- test_turleri: her partide yapılan kabul (conformance) testi "kabul", yalnız
  yeterlilikte yapılan "yeterlilik", raf ömrü uzatma testi "omur_uzatma".
- id: test adından küçük harf, alt çizgili kısa ad (ör. "viscosity").
- Sayfada test şartı yoksa boş liste dön: {"testler": []}.
- Uydurma; sayfada olmayan bir şeyi yazma."""


def istem_olustur(sayfa_metni: str, sayfa_no: int, belge_no: str, revizyon: str) -> list[Mesaj]:
    """Bir sayfa için sistem ve kullanıcı mesajlarını kurar."""
    sema = json.dumps(cikarim_semasi(), ensure_ascii=False)
    kullanici = (
        f"Belge: {belge_no}, revizyon \"{revizyon}\". Aşağıdaki metin PDF'in sayfa {sayfa_no}. "
        f"Her şartın kaynağında belge_no=\"{belge_no}\", revizyon=\"{revizyon}\", sayfa={sayfa_no} yaz.\n\n"
        f"JSON şeması:\n{sema}\n\n"
        f"--- SAYFA {sayfa_no} ---\n{sayfa_metni}\n--- SAYFA SONU ---"
    )
    return [{"role": "system", "content": _SISTEM}, {"role": "user", "content": kullanici}]


# --- HTTP istekleri -----------------------------------------------------------------


def istek_govdesi(
    arka_uc: str,
    model: str,
    mesajlar: list[Mesaj],
    sema: dict[str, Any],
    sicaklik: float = 0.0,
    baglam: int = 8192,
    en_cok_token: int = 4096,
    dusunme: bool | None = None,
) -> tuple[str, dict[str, Any]]:
    """Arka uca göre (yol, istek gövdesi) döner.

    `dusunme` yalnız Ollama'da ve düşünme kipi olan modellerde (ör. Qwen3)
    verilir; None ise gövdeye konmaz.
    """
    if arka_uc == "ollama":
        govde: dict[str, Any] = {
            "model": model,
            "messages": mesajlar,
            "stream": False,
            "format": sema,
            "options": {"temperature": sicaklik, "num_ctx": baglam, "num_predict": en_cok_token},
        }
        if dusunme is not None:
            govde["think"] = dusunme
        return ARKA_UCLAR["ollama"][1], govde
    if arka_uc == "llamacpp":
        return ARKA_UCLAR["llamacpp"][1], {
            "model": model,
            "messages": mesajlar,
            "temperature": sicaklik,
            "max_tokens": en_cok_token,
            "response_format": {"type": "json_schema", "json_schema": {"name": "cikarim", "schema": sema}},
        }
    raise ValueError(f"bilinmeyen arka uç: {arka_uc!r} (ollama ya da llamacpp)")


def yanit_metni(arka_uc: str, yanit: dict[str, Any]) -> str:
    """Sunucu yanıtından modelin ürettiği metni alır."""
    if arka_uc == "ollama":
        return yanit["message"]["content"]
    return yanit["choices"][0]["message"]["content"]


class _YonlendirmeYok(urllib.request.HTTPRedirectHandler):
    """3xx yönlendirmelerini izlemez; yerel sunucu isteği dışarı yollayamasın."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError(f"yerel model sunucusu yönlendirme döndü ({code}), izlenmedi: {newurl}")


class YerelModelIstemcisi:
    """Yalnız localhost'taki Ollama ya da llama.cpp sunucusuna bağlanan istemci."""

    def __init__(
        self,
        model: str,
        arka_uc: str = "ollama",
        adres: str | None = None,
        sicaklik: float = 0.0,
        baglam: int = 8192,
        en_cok_token: int = 4096,
        zaman_asimi_s: float = 600,
        dusunme: bool | None = None,
    ):
        if arka_uc not in ARKA_UCLAR:
            raise ValueError(f"bilinmeyen arka uç: {arka_uc!r} (ollama ya da llamacpp)")
        adres = (adres or ARKA_UCLAR[arka_uc][0]).rstrip("/")
        if not adres_yerel_mi(adres):
            raise ValueError(f"yerel model yalnız localhost'a bağlanır, verilen adres: {adres!r}")
        self.model = model
        self.arka_uc = arka_uc
        self.adres = adres
        self.sicaklik = sicaklik
        self.baglam = baglam
        self.en_cok_token = en_cok_token
        self.zaman_asimi_s = zaman_asimi_s
        self.dusunme = dusunme

    def sohbet(self, mesajlar: list[Mesaj], sema: dict[str, Any]) -> str:
        """Mesajları şemayla birlikte gönderir, modelin ürettiği metni döner."""
        yol, govde = istek_govdesi(
            self.arka_uc, self.model, mesajlar, sema,
            sicaklik=self.sicaklik, baglam=self.baglam,
            en_cok_token=self.en_cok_token, dusunme=self.dusunme,
        )
        istek = urllib.request.Request(
            self.adres + yol,
            data=json.dumps(govde).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # Vekil sunucu ayarları yok sayılır ve yönlendirme izlenmez: istek bu makineden çıkmaz.
        acici = urllib.request.build_opener(urllib.request.ProxyHandler({}), _YonlendirmeYok())
        with acici.open(istek, timeout=self.zaman_asimi_s) as cevap:
            return yanit_metni(self.arka_uc, json.loads(cevap.read().decode("utf-8")))


# --- Yanıtı çözme -----------------------------------------------------------------


def _ilk_hata(hata: ValidationError) -> str:
    e = hata.errors()[0]
    yer = ".".join(str(p) for p in e["loc"])
    return f"{yer}: {e['msg']}" if yer else e["msg"]


def yaniti_coz(metin: str) -> tuple[list[TestSarti], list[str]]:
    """Model yanıtını test şartlarına çözer.

    Geçerli şartlar ve her geçersiz şart (ya da çözülemeyen yanıt) için bir
    hata açıklaması döner. Bir şartın geçersiz olması diğerlerini düşürmez.
    """
    try:
        veri = json.loads(metin)
    except json.JSONDecodeError as hata:
        return [], [f"JSON çözülemedi: {hata.msg} (konum {hata.pos})"]
    if not isinstance(veri, dict) or not isinstance(veri.get("testler"), list):
        return [], ["yanıtta 'testler' listesi yok"]

    testler: list[TestSarti] = []
    hatalar: list[str] = []
    for i, ham in enumerate(veri["testler"]):
        try:
            testler.append(TestSarti.model_validate(ham))
        except ValidationError as hata:
            ad = ham.get("id") if isinstance(ham, dict) else None
            hatalar.append(f"test {i} ({ad or '?'}): {_ilk_hata(hata)}")
    return testler, hatalar


# --- Belgeden çıkarma ---------------------------------------------------------------


class SohbetIstemcisi(Protocol):
    def sohbet(self, mesajlar: list[Mesaj], sema: dict[str, Any]) -> str: ...


@dataclass
class SayfaSonucu:
    sayfa: int
    sure_s: float
    test_sayisi: int
    hatalar: list[str] = field(default_factory=list)


@dataclass
class CikarimRaporu:
    sayfalar: list[SayfaSonucu] = field(default_factory=list)
    tekrar_edenler: list[str] = field(default_factory=list)
    toplam_sure_s: float = 0.0
    test_sayisi: int = 0

    def sozluk(self) -> dict[str, Any]:
        return asdict(self)


def belgeden_cikar(
    belge: Belge,
    belge_no: str,
    revizyon: str,
    istemci: SohbetIstemcisi,
    sayfalar: set[int] | None = None,
) -> tuple[KabulDokumani, CikarimRaporu]:
    """Belgeyi sayfa sayfa modele okutur, test şartlarını kabul dokümanında toplar.

    Metni boş sayfalar (taranmış) atlanır. Aynı `id` birden çok sayfada çıkarsa
    ilki tutulur, diğerleri `tekrar_edenler` listesine yazılır. Kaynağın belge
    no, revizyon ve sayfa alanları koddan yazılır (madde modelden gelir). Numune hazırlama
    bilgisi bu adımda çıkarılmadığı için testlerin numune bağlantısı boşaltılır.
    Bir sayfadaki bağlantı ya da zaman aşımı hatası rapora yazılır, kalan
    sayfalar okunmaya devam eder.
    """
    sema = cikarim_semasi()
    rapor = CikarimRaporu()
    testler: dict[str, TestSarti] = {}
    baslangic = time.perf_counter()

    for sayfa in belge.sayfalar:
        if sayfalar is not None and sayfa.no not in sayfalar:
            continue
        metin = metni_normallestir(sayfa.metin)
        if not metin:
            continue
        mesajlar = istem_olustur(metin, sayfa.no, belge_no, revizyon)
        t0 = time.perf_counter()
        try:
            bulunan, hatalar = yaniti_coz(istemci.sohbet(mesajlar, sema))
        except (OSError, http.client.HTTPException, ValueError, KeyError, IndexError) as hata:
            bulunan, hatalar = [], [f"istek başarısız: {type(hata).__name__}: {hata}"]
        sure = time.perf_counter() - t0

        for t in bulunan:
            if t.id in testler:
                rapor.tekrar_edenler.append(t.id)
                continue
            # Belge no, revizyon ve sayfa kodca bilinir; modelin yazdığı değil bunlar tutulur.
            kaynak = t.kaynak.model_copy(update={"belge_no": belge_no, "revizyon": revizyon, "sayfa": sayfa.no})
            testler[t.id] = t.model_copy(update={"numune_hazirlama_id": None, "kaynak": kaynak})
        rapor.sayfalar.append(SayfaSonucu(sayfa.no, round(sure, 3), len(bulunan), hatalar))

    rapor.toplam_sure_s = round(time.perf_counter() - baslangic, 3)
    rapor.test_sayisi = len(testler)
    dokuman = KabulDokumani(
        standart=StandartBilgisi(belge_no=belge_no, revizyon=revizyon),
        testler=list(testler.values()),
    )
    return dokuman, rapor
