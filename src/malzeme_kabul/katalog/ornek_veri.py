"""Kataloğa örnek veri yükler (data/ornek/katalog.json).

Örnek veri dosyası kabul dokümanı JSON dosyalarının yollarını (depo köküne
göre), malzeme kodlarını, onaylı tedarikçileri ve partileri listeler. Yükleme
tekrar çalıştırılabilir: var olan malzeme ve parti atlanır, aynı içerikteki
doküman yeniden sürüm almaz.

Örnek veri M&P onayı değildir: dokümanlar `ORNEK_ONAYLAYAN` adıyla demo onayıyla
(`demo_onayi=True`) yazılır. Dosyadaki `onaylayan` tam `ORNEK_ONAYLAYAN`
değilse `KatalogHatasi` verilir ve hiçbir şey yazılmaz.

Bir standart + revizyonun gerçek (demo olmayan) onaylı sürümü varsa örnek
doküman onun üstüne demo sürüm olarak yazılmaz; etiketi
`YuklemeOzeti.atlanan_dokumanlar`'a eklenir. Yalnız demo sürümü olan standarda
yeni örnek içerik yeni demo sürüm olur.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from malzeme_kabul.katalog.veritabani import ORNEK_ONAYLAYAN, Katalog, KatalogHatasi, icerik_ozeti
from malzeme_kabul.sozlesme.sema import KabulDokumani


@dataclass
class YuklemeOzeti:
    dokuman_surumleri: list[str] = field(default_factory=list)
    malzemeler: list[str] = field(default_factory=list)
    partiler: list[str] = field(default_factory=list)
    atlanan_dokumanlar: list[str] = field(default_factory=list)  # gerçek onaylı sürümü olduğu için yazılmayanlar


def _ayni_icerik_var(katalog: Katalog, dokuman: KabulDokumani) -> bool:
    std = dokuman.standart
    yeni = icerik_ozeti(dokuman.model_copy(update={"durum": "onaylandi"}).model_dump_json())
    return any(s.ozet == yeni for s in katalog.dokuman_surumleri(std.belge_no, std.revizyon))


def ornek_yukle(katalog: Katalog, veri_yolu: str | Path, kok: str | Path) -> YuklemeOzeti:
    """`veri_yolu` dosyasındaki örnek veriyi kataloğa yükler; `kok` doküman yollarının kökü."""
    veri = json.loads(Path(veri_yolu).read_text(encoding="utf-8"))
    onaylayan = veri.get("onaylayan", ORNEK_ONAYLAYAN)
    if onaylayan != ORNEK_ONAYLAYAN:
        raise KatalogHatasi(f"örnek verinin onaylayanı {ORNEK_ONAYLAYAN!r} olmalı (demo onayı): {onaylayan!r}")
    kok = Path(kok)
    ozet = YuklemeOzeti()
    for goreli in veri.get("dokumanlar", []):
        dokuman = KabulDokumani.model_validate_json((kok / goreli).read_text(encoding="utf-8"))
        if _ayni_icerik_var(katalog, dokuman):
            continue
        std = dokuman.standart
        gercek = [s for s in katalog.dokuman_surumleri(std.belge_no, std.revizyon) if not s.demo_onayi]
        if gercek:
            ozet.atlanan_dokumanlar.append(f"{std.belge_no}{std.revizyon} (gerçek onaylı {gercek[-1].etiket} var)")
            continue
        s = katalog.dokuman_onayla(dokuman, ORNEK_ONAYLAYAN, veri.get("onay_notu"), demo_onayi=True)
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
