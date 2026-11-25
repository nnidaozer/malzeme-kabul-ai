"""Kataloğa örnek veri yükler (data/ornek/katalog.json).

Örnek veri dosyası kabul dokümanı JSON dosyalarının yollarını (depo köküne
göre), malzeme kodlarını, onaylı tedarikçileri ve partileri listeler. Yükleme
tekrar çalıştırılabilir: var olan malzeme ve parti atlanır, aynı içerikteki
doküman yeniden sürüm almaz.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from malzeme_kabul.katalog.veritabani import Katalog, KatalogHatasi, icerik_ozeti
from malzeme_kabul.sozlesme.sema import KabulDokumani


@dataclass
class YuklemeOzeti:
    dokuman_surumleri: list[str] = field(default_factory=list)
    malzemeler: list[str] = field(default_factory=list)
    partiler: list[str] = field(default_factory=list)


def _ayni_icerik_var(katalog: Katalog, dokuman: KabulDokumani) -> bool:
    std = dokuman.standart
    yeni = icerik_ozeti(dokuman.model_copy(update={"durum": "onaylandi"}).model_dump_json())
    return any(s.ozet == yeni for s in katalog.dokuman_surumleri(std.belge_no, std.revizyon))


def ornek_yukle(katalog: Katalog, veri_yolu: str | Path, kok: str | Path) -> YuklemeOzeti:
    """`veri_yolu` dosyasındaki örnek veriyi kataloğa yükler; `kok` doküman yollarının kökü."""
    veri = json.loads(Path(veri_yolu).read_text(encoding="utf-8"))
    kok = Path(kok)
    ozet = YuklemeOzeti()
    for goreli in veri.get("dokumanlar", []):
        dokuman = KabulDokumani.model_validate_json((kok / goreli).read_text(encoding="utf-8"))
        if _ayni_icerik_var(katalog, dokuman):
            continue
        s = katalog.dokuman_onayla(dokuman, veri.get("onaylayan", "ornek-veri"), veri.get("onay_notu"))
        ozet.dokuman_surumleri.append(s.etiket)
    for m in veri.get("malzemeler", []):
        try:
            katalog.malzeme(m["kod"])
            continue
        except KatalogHatasi:
            pass
        katalog.malzeme_ekle(**m)
        ozet.malzemeler.append(m["kod"])
    for o in veri.get("onayli_tedarikciler", []):
        katalog.tedarikci_onayla(o["malzeme_kodu"], o["tedarikci"])
    for p in veri.get("partiler", []):
        try:
            katalog.parti(p["malzeme_kodu"], p["lot_no"])
            continue
        except KatalogHatasi:
            pass
        katalog.parti_ekle(**p)
        ozet.partiler.append(f"{p['malzeme_kodu']}/{p['lot_no']}")
    return ozet


__all__ = ["YuklemeOzeti", "ornek_yukle"]
