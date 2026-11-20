#!/usr/bin/env python3
"""CI kontrolü: bir PR data/gold/ klasörünü değiştiriyorsa başarısız olur.

PR'da `gold-guncelleme` etiketi varsa geçer. Proje sahibi doğru cevapları
bu etiketle ekler.

Kullanım:
  git diff --name-only --no-renames BASE...HEAD | python scripts/ci/gold_degisiklik_kontrol.py

Etiketler `PR_ETIKETLERI` ortam değişkeninde JSON listesi olarak verilir,
ör. '["gold-guncelleme"]'.
"""

from __future__ import annotations

import json
import os
import sys

GOLD_KLASORU = "data/gold/"
IZIN_ETIKETI = "gold-guncelleme"


def gold_dosyalari(degisen_dosyalar: list[str]) -> list[str]:
    """Değişen dosyalar arasından data/gold/ altındakileri döner."""
    sonuc = []
    for yol in degisen_dosyalar:
        yol = yol.strip().replace("\\", "/")
        if yol.startswith("./"):
            yol = yol[2:]
        if yol.startswith(GOLD_KLASORU) or yol == GOLD_KLASORU.rstrip("/"):
            sonuc.append(yol)
    return sonuc


def etiketleri_oku(ham: str | None) -> list[str]:
    """PR_ETIKETLERI ortam değişkenindeki JSON listesini okur."""
    if not ham:
        return []
    try:
        deger = json.loads(ham)
    except json.JSONDecodeError:
        return []
    return [str(e) for e in deger] if isinstance(deger, list) else []


def kontrol_et(degisen_dosyalar: list[str], etiketler: list[str]) -> tuple[bool, str]:
    """(geçti_mi, mesaj) döner."""
    gold = gold_dosyalari(degisen_dosyalar)
    if not gold:
        return True, "data/gold/ değişmedi."
    if IZIN_ETIKETI in etiketler:
        return True, f"data/gold/ değişti ({len(gold)} dosya), '{IZIN_ETIKETI}' etiketi var: geçti."
    liste = "\n".join(f"  - {y}" for y in gold)
    return False, (
        f"Bu PR data/gold/ klasörünü değiştiriyor:\n{liste}\n"
        f"data/gold/ yalnızca proje sahibi tarafından, '{IZIN_ETIKETI}' etiketli "
        "PR'larla güncellenir."
    )


def main() -> int:
    dosyalar = [s for s in sys.stdin.read().splitlines() if s.strip()]
    gecti, mesaj = kontrol_et(dosyalar, etiketleri_oku(os.environ.get("PR_ETIKETLERI")))
    print(mesaj)
    return 0 if gecti else 1


if __name__ == "__main__":
    sys.exit(main())
