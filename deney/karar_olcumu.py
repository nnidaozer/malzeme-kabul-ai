"""Karar motorunun ölçümü: yakalama oranı, yanlış kabul oranı, karışıklık matrisi.

Tanımlar (belge düzeyi):
- yanlis_kabul_orani: doğru kararı "kabul" OLMAYAN sertifikalardan motorun
  "kabul" dediklerinin oranı. Projenin ana güvenlik ölçütü.
- yakalama_orani: doğru kararı "red" olan sertifikalardan motorun "red"
  dediklerinin oranı.
- dogruluk: motor kararının doğru kararla aynı olduğu sertifikaların oranı.
- otomasyon_orani: motorun insana bırakmadığı ("inceleme" demediği)
  sertifikaların oranı.

Satır düzeyinde aynı ölçütler test kararlarıyla hesaplanır ("uygun" kabulün,
"uygun_degil" reddin karşılığıdır). Paydası sıfır olan oran None döner.

Yanlış kabul oranı hem parametre (satır) hem parti (belge) düzeyinde %95
Wilson güven aralığıyla raporlanır; birincil ölçüt parti düzeyidir
(docs/mimari.md madde 7). Wilson aralığı, oran 0 iken de anlamlı bir üst sınır
verir (ör. 0/150 için yaklaşık %0–%2,5).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from malzeme_kabul.kural.karar_motoru import BelgeKarari, Karar, KontrolSonucu

BELGE_KARARLARI = ("kabul", "red", "inceleme")
SATIR_KARARLARI = ("uygun", "uygun_degil", "insan_incelemeli")


class DogruKarar(BaseModel):
    """Bir sertifikanın doğru kararı (sertifika üreticisinin yazdığı cevap)."""

    model_config = ConfigDict(extra="forbid")

    sertifika_no: str
    belge_karari: BelgeKarari
    hata_turu: str | None = None
    hata_aciklamasi: str | None = None
    revizyon: Karar = "uygun"
    satirlar: dict[str, Karar] = Field(default_factory=dict)


class Oranlar(BaseModel):
    adet: int
    dogruluk: float | None
    yanlis_kabul_orani: float | None
    yanlis_kabul_araligi: tuple[float, float] | None = Field(default=None, description="%95 Wilson güven aralığı.")
    yakalama_orani: float | None
    otomasyon_orani: float | None
    karisiklik: dict[str, dict[str, int]] = Field(description="karisiklik[dogru][tahmin]")


class TurSkoru(BaseModel):
    adet: int
    dogru: int
    yanlis_kabul: int


class Olcum(BaseModel):
    belge: Oranlar
    satir: Oranlar
    hata_turune_gore: dict[str, TurSkoru]


def _oran(pay: int, payda: int) -> float | None:
    return pay / payda if payda else None


def wilson_araligi(pay: int, payda: int, z: float = 1.959964) -> tuple[float, float] | None:
    """Bir oran için Wilson skor güven aralığı (varsayılan %95). Payda sıfırsa None."""
    if payda <= 0:
        return None
    if not 0 <= pay <= payda:
        raise ValueError(f"pay 0 ile payda arasında olmalı: {pay}/{payda}")
    p = pay / payda
    z2 = z * z
    merkez = (p + z2 / (2 * payda)) / (1 + z2 / payda)
    yari = z * math.sqrt(p * (1 - p) / payda + z2 / (4 * payda * payda)) / (1 + z2 / payda)
    alt = 0.0 if pay == 0 else max(0.0, merkez - yari)  # uçlarda kayan nokta artığı kalmasın
    ust = 1.0 if pay == payda else min(1.0, merkez + yari)
    return alt, ust


def _oranlar(ciftler: list[tuple[str, str]], etiketler: tuple[str, str, str]) -> Oranlar:
    kabul, red, inceleme = etiketler
    k = {d: {t: 0 for t in etiketler} for d in etiketler}
    for d, t in ciftler:
        k[d][t] += 1
    n = len(ciftler)
    kabul_olmayan = [(d, t) for d, t in ciftler if d != kabul]
    red_olan = [(d, t) for d, t in ciftler if d == red]
    yanlis_kabul = sum(t == kabul for _, t in kabul_olmayan)
    return Oranlar(
        adet=n,
        dogruluk=_oran(sum(d == t for d, t in ciftler), n),
        yanlis_kabul_orani=_oran(yanlis_kabul, len(kabul_olmayan)),
        yanlis_kabul_araligi=wilson_araligi(yanlis_kabul, len(kabul_olmayan)),
        yakalama_orani=_oran(sum(t == red for _, t in red_olan), len(red_olan)),
        otomasyon_orani=_oran(sum(t != inceleme for _, t in ciftler), n),
        karisiklik=k,
    )


def olc(tahminler: Sequence[KontrolSonucu], dogrular: Sequence[DogruKarar]) -> Olcum:
    """Motor kararlarını doğru kararlarla karşılaştırır."""
    tahmin = {t.sertifika_no: t for t in tahminler}
    eksik = [d.sertifika_no for d in dogrular if d.sertifika_no not in tahmin]
    if eksik:
        raise ValueError(f"tahmini olmayan sertifikalar: {eksik[:5]}{' ...' if len(eksik) > 5 else ''}")

    belge: list[tuple[str, str]] = []
    satir: list[tuple[str, str]] = []
    turler: dict[str, TurSkoru] = {}
    for d in dogrular:
        t = tahmin[d.sertifika_no]
        belge.append((d.belge_karari, t.belge_karari))
        tahmin_satir = {s.test_id: s.karar for s in t.satirlar}
        for test_id, karar in d.satirlar.items():
            satir.append((karar, tahmin_satir.get(test_id, "insan_incelemeli")))
        tur = turler.setdefault(d.hata_turu or "temiz", TurSkoru(adet=0, dogru=0, yanlis_kabul=0))
        tur.adet += 1
        tur.dogru += d.belge_karari == t.belge_karari
        tur.yanlis_kabul += d.belge_karari != "kabul" and t.belge_karari == "kabul"

    return Olcum(
        belge=_oranlar(belge, BELGE_KARARLARI),
        satir=_oranlar(satir, SATIR_KARARLARI),
        hata_turune_gore=dict(sorted(turler.items())),
    )
