#!/usr/bin/env python3
"""PreToolUse hook'u: data/gold/ klasörüne yazmayı engeller.

Ana oturum ve tüm alt ajanlar için geçerlidir. data/gold/ altındaki doğru
cevapları yalnızca proje sahibi elle etiketler.

Çıkış kodları (Claude Code hook sözleşmesi):
  0  izin ver
  2  engelle (stderr'deki mesaj Claude'a gösterilir)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _yazma_analizi import arac_korunana_yaziyor_mu  # noqa: E402

KORUNAN = "data/gold"
MESAJ = (
    "Engellendi: data/gold/ klasörüne yazılamaz. Doğru cevapları yalnızca "
    "proje sahibi elle etiketler (bkz. CLAUDE.md). data/gold/ dosyalarını "
    "yalnızca okuyabilirsin."
)


def karar_ver(girdi: dict) -> int:
    """Hook girdisine göre çıkış kodunu döner: 0 izin, 2 engel."""
    return 2 if arac_korunana_yaziyor_mu(girdi, KORUNAN) else 0


def main() -> int:
    try:
        girdi = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("gold_koruma: hook girdisi okunamadı, güvenli tarafta kalınıyor.", file=sys.stderr)
        return 2
    kod = karar_ver(girdi)
    if kod == 2:
        print(MESAJ, file=sys.stderr)
    return kod


if __name__ == "__main__":
    sys.exit(main())
