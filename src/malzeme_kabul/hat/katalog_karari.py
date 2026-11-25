"""Katalogdan kabul dokümanı alıp sertifikaya karar veren hat (docs/mimari.md madde 2 ve 5).

Akış: malzeme kodu → katalogdaki en son onaylı kabul dokümanı sürümü ve
tip/sınıf → `kural.karar_motoru.kontrol_et` → parti kararı → (lot verilmişse)
katalogdaki parti durumu.

Kabul dokümanı dosyadan okunmaz; yalnız katalogdan, malzeme koduna göre gelir.

Kararı kural katmanı verir; bu modül yalnız bağlar. Katalogdan gelen iki ek
denetim de kesin kuraldır ve emin olunmayanı insana bırakır:

- `tedarikci`: sertifikadaki tedarikçi o malzeme için onaylı listede yoksa
  insan incelemeli (ad yazımı farklı olabilir; reddetmek yerine insana).
- `siparis_revizyonu`: partinin siparişteki revizyonu malzemenin kabul
  dokümanı revizyonundan farklıysa insan incelemeli.

Parti kararı katalog durumuna şöyle yansır: kabul → serbest, red → karantina,
inceleme → bekliyor.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from malzeme_kabul.katalog.veritabani import Katalog, PartiDurumu
from malzeme_kabul.kural.karar_motoru import (
    BelgeKarari,
    Karar,
    KararAyarlari,
    KararSatiri,
    KontrolSonucu,
    kontrol_et,
    parti_karari,
)
from malzeme_kabul.sozlesme.sertifika import Sertifika

PARTI_DURUMU: dict[str, PartiDurumu] = {"kabul": "serbest", "red": "karantina", "inceleme": "bekliyor"}


class KatalogKarari(BaseModel):
    """Katalogla verilen kararın tamamı."""

    model_config = ConfigDict(extra="forbid")

    malzeme_kodu: str
    lot_no: str | None
    dokuman_surumu: str  # ör. "MIL-PRF-23377K v2"
    dokuman_ozeti: str
    kontrol: KontrolSonucu
    ek_denetimler: list[KararSatiri]
    parti_karari: BelgeKarari
    parti_durumu: PartiDurumu


def _ad(metin: str) -> str:
    return " ".join(metin.split()).casefold()


def _tedarikci_denetimi(katalog: Katalog, malzeme_kodu: str, sertifika: Sertifika) -> KararSatiri | None:
    if not sertifika.tedarikci:
        return None
    onayli = katalog.onayli_tedarikciler(malzeme_kodu)
    ortak = {"test_id": "tedarikci", "test_adi": "Onaylı tedarikçi"}
    if _ad(sertifika.tedarikci) in {_ad(t) for t in onayli}:
        return KararSatiri(karar="uygun", gerekce=f"{sertifika.tedarikci} onaylı listede", **ortak)
    return KararSatiri(
        karar="insan_incelemeli",
        gerekce=f"sertifikadaki tedarikçi {sertifika.tedarikci!r} onaylı listede yok ({', '.join(onayli) or '-'})",
        **ortak,
    )


def malzeme_koduyla_kontrol(
    katalog: Katalog,
    malzeme_kodu: str,
    sertifika: Sertifika,
    lot_no: str | None = None,
    ayar: KararAyarlari | None = None,
    durumu_yaz: bool = True,
) -> KatalogKarari:
    """Sertifikayı malzeme kodunun onaylı kabul dokümanıyla karşılaştırır.

    `lot_no` verilir ve parti katalogda varsa, `durumu_yaz` ise parti durumu
    karara göre güncellenir.
    """
    malzeme = katalog.malzeme(malzeme_kodu)
    surum = katalog.gecerli_dokuman(malzeme_kodu)
    kontrol = kontrol_et(surum.dokuman, sertifika, ayar, tip=malzeme.tip, sinif=malzeme.sinif)

    ek: list[KararSatiri] = []
    if (t := _tedarikci_denetimi(katalog, malzeme_kodu, sertifika)) is not None:
        ek.append(t)
    parti = None
    if lot_no is not None:
        parti = katalog.parti(malzeme_kodu, lot_no)
        ortak = {"test_id": "siparis_revizyonu", "test_adi": "Sipariş revizyonu"}
        if parti.siparis_revizyonu != malzeme.revizyon:
            ek.append(KararSatiri(
                karar="insan_incelemeli",
                gerekce=f"sipariş revizyonu {parti.siparis_revizyonu}, kabul dokümanı {malzeme.standart_etiketi}",
                **ortak,
            ))
        else:
            ek.append(KararSatiri(karar="uygun", gerekce=f"sipariş revizyonu {parti.siparis_revizyonu}", **ortak))

    karar = parti_karari(_satir_kararlari(kontrol) + [s.karar for s in ek])
    durum = PARTI_DURUMU[karar]
    if parti is not None and durumu_yaz:
        katalog.parti_durumu_ata(malzeme_kodu, parti.lot_no, durum)
    return KatalogKarari(
        malzeme_kodu=malzeme_kodu,
        lot_no=lot_no,
        dokuman_surumu=surum.etiket,
        dokuman_ozeti=surum.ozet,
        kontrol=kontrol,
        ek_denetimler=ek,
        parti_karari=karar,
        parti_durumu=durum,
    )


def _satir_kararlari(kontrol: KontrolSonucu) -> list[Karar]:
    kararlar = [kontrol.revizyon.karar] + [s.karar for s in kontrol.satirlar]
    if kontrol.tip_sinif is not None:
        kararlar.append(kontrol.tip_sinif.karar)
    return kararlar


__all__ = ["KatalogKarari", "PARTI_DURUMU", "malzeme_koduyla_kontrol"]
