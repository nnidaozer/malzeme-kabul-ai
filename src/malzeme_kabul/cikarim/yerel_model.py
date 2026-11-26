"""Yerel dil modeli istemcisi (yalnız localhost).

Ürünün içindeki tek ağ kodu budur (CLAUDE.md, kural 4). İstemci yalnızca
localhost'a bağlanır, vekil sunucu ayarlarını yok sayar ve yönlendirme
izlemez. İki yerel sunucu desteklenir:

- Ollama: /api/chat, şema `format` alanında verilir.
- llama.cpp (llama-server): /v1/chat/completions, şema `response_format`
  içinde `json_schema` olarak verilir.

İki sunucu da şemayı dilbilgisine (grammar) çevirip üretimi buna zorlar.
Hangi şemanın verileceği çağıranın işidir: üründe dil modeli yalnız ham
okuma döndürür (`malzeme_kabul.sozlesme.okuma`, docs/mimari.md madde 6);
"yalnız dil modeli" deneyi `deney/yalniz_dil_modeli.py` içindedir.
"""

from __future__ import annotations

import http.client
import json
import urllib.request
from typing import Any, Protocol
from urllib.parse import urlparse

ARKA_UCLAR = {
    "ollama": ("http://localhost:11434", "/api/chat"),
    "llamacpp": ("http://localhost:8080", "/v1/chat/completions"),
}
YEREL_ADRESLER = {"localhost", "127.0.0.1", "::1"}

Mesaj = dict[str, str]



class ModelYanitHatasi(Exception):
    """Yerel model çağrısı beklenmedik biçimde bitti: sunucu yanıtı beklenen yapıda değil ya da yarım."""


# `sohbet` çağrısından gelip `ModelYanitHatasi`'na sarılan hatalar (cikarim/sertifika_okuyucu,
# retro H10, K4): beklenmedik sunucu yanıtı (KeyError, TypeError, IndexError: ör. {"error": ...},
# boş "choices") ve yarım HTTP yanıtı (HTTPException, ör. IncompleteRead). Yalnız çağrının kendisi
# sarılır; ayrıştırma kodundaki aynı türden hatalar sarılmaz. AttributeError bilerek yoktur.
SOHBET_HATALARI: tuple[type[BaseException], ...] = (KeyError, TypeError, IndexError, http.client.HTTPException)

# Hattın kural okumasına düştüğü hatalar (hat/hibrit_hat): bağlantı yok ve zaman aşımı (OSError),
# şemaya uymayan yanıt (ValueError) ve sarılmış sunucu yanıtı hatası (ModelYanitHatasi).
YEDEK_HATALARI: tuple[type[BaseException], ...] = (OSError, ValueError, ModelYanitHatasi)

def adres_yerel_mi(adres: str) -> bool:
    """Adres http(s) ile bu makineye (localhost) mı gidiyor?"""
    try:
        parca = urlparse(adres)
    except ValueError:
        return False
    return parca.scheme in {"http", "https"} and parca.hostname in YEREL_ADRESLER


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


class SohbetIstemcisi(Protocol):
    """`YerelModelIstemcisi` ve testlerdeki sahte istemcilerin ortak arayüzü."""

    def sohbet(self, mesajlar: list[Mesaj], sema: dict[str, Any]) -> str: ...
