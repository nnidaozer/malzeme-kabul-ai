"""Depodaki partilerin raf ömrü raporu (katalog + kural/raf_omru).

Her parti için malzemenin onaylı kabul dokümanındaki raf ömrüyle son
kullanma tarihi hesaplanır, 30 gün (ya da verilen eşik) kala uyarı verilir ve
o tip/sınıfa uygulanan ömür uzatma testleri listelenir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from malzeme_kabul.katalog.veritabani import Katalog, KatalogHatasi, Parti
from malzeme_kabul.kural.karar_motoru import kod_normallestir
from malzeme_kabul.kural.raf_omru import UYARI_ESIGI_GUN, RafDurumBilgisi, omur_uzatma_testleri, raf_durumu
from malzeme_kabul.sozlesme.sema import TestSarti


@dataclass(frozen=True)
class RafSatiri:
    parti: Parti
    dokuman_surumu: str | None
    raf: RafDurumBilgisi
    omur_uzatma_testleri: list[TestSarti]
    demo_onayi: bool = False  # kabul dokümanı örnek verinin demo onayıyla mı (onaylı doküman yoksa False)


def raf_raporu(
    katalog: Katalog, bugun: date | None = None, uyari_esigi_gun: int = UYARI_ESIGI_GUN, yalniz_uyari: bool = False
) -> list[RafSatiri]:
    """Bütün partilerin raf durumu; en yakın son kullanma tarihi önce (bilinmeyenler sonda)."""
    bugun = bugun or date.today()
    satirlar: list[RafSatiri] = []
    for parti in katalog.partiler():
        m = katalog.malzeme(parti.malzeme_kodu)
        tip, sinif = kod_normallestir(m.tip), kod_normallestir(m.sinif)
        try:
            surum = katalog.gecerli_dokuman(parti.malzeme_kodu)
        except KatalogHatasi as hata:
            satirlar.append(RafSatiri(parti, None, RafDurumBilgisi("bilinmiyor", None, None, None, [str(hata)]), []))
            continue
        raf = raf_durumu(surum.dokuman, parti.uretim_tarihi, bugun, parti.kap_turu, tip, sinif, uyari_esigi_gun)
        uzatma = omur_uzatma_testleri(surum.dokuman, tip, sinif) if raf.uyari else []
        satirlar.append(RafSatiri(parti, surum.etiket, raf, uzatma, surum.demo_onayi))
    if yalniz_uyari:
        satirlar = [s for s in satirlar if s.raf.uyari]
    return sorted(satirlar, key=lambda s: (s.raf.son_kullanma is None, s.raf.son_kullanma or date.max))


__all__ = ["RafSatiri", "raf_raporu"]
