"""Gold taslağında yönü belirsiz sınırlar (etiketleme kılavuzu K2a)."""

from __future__ import annotations

from pathlib import Path

from malzeme_kabul.arayuz.dokuman_uretici import YON_BELIRSIZ_NOTU, sinir_metni
from malzeme_kabul.sozlesme.sema import KabulDokumani

TASLAK = Path(__file__).resolve().parents[1] / "data" / "gold_taslak" / "MIL-PRF-23377K.json"


def test_23377k_3_11_bekleme_suresi_yonu_belirsiz_ve_insan_incelemeli():
    # Nida'nın kararı (28 Kasım): "30 minutes" en az mı tam mı belli değil.
    d = KabulDokumani.model_validate_json(TASLAK.read_text(encoding="utf-8"))
    [k] = [k for k in d.kosullar if k.kaynak.madde == "3.11" and k.sinir and k.sinir.birim == "minute"]
    assert k.sinir.yon == "belirsiz"
    assert k.sinir.alt == 30
    assert YON_BELIRSIZ_NOTU in sinir_metni(k.sinir)
