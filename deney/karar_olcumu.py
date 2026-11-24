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
"""

from __future__ import annotations

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


def _oranlar(ciftler: list[tuple[str, str]], etiketler: tuple[str, str, str]) -> Oranlar:
    kabul, red, inceleme = etiketler
    k = {d: {t: 0 for t in etiketler} for d in etiketler}
    for d, t in ciftler:
        k[d][t] += 1
    n = len(ciftler)
    kabul_olmayan = [(d, t) for d, t in ciftler if d != kabul]
    red_olan = [(d, t) for d, t in ciftler if d == red]
    return Oranlar(
        adet=n,
        dogruluk=_oran(sum(d == t for d, t in ciftler), n),
        yanlis_kabul_orani=_oran(sum(t == kabul for _, t in kabul_olmayan), len(kabul_olmayan)),
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
