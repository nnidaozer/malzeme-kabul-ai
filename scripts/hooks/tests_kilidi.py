#!/usr/bin/env python3
"""PreToolUse hook'u: uygulayici alt ajanının tests/ klasörüne yazmasını engeller.

Claude Code, alt ajan içindeki her araç çağrısında hook girdisine
`agent_type` alanını (ajanın frontmatter `name` değeri) ekler. Bu hook
yalnızca `agent_type == "uygulayici"` olduğunda devreye girer; ana oturum ve
test-yazari dahil diğer ajanlar tests/ altına yazmaya devam edebilir.
uygulayici testleri okuyabilir ve çalıştırabilir (pytest).

Çıkış kodları: 0 izin ver, 2 engelle.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _yazma_analizi import arac_korunana_yaziyor_mu  # noqa: E402

KILITLI_AJANLAR = {"uygulayici"}
KORUNAN = "tests"
MESAJ = (
    "Engellendi: uygulayici ajanı tests/ klasörünü değiştiremez. Testi geçirmek "
    "için kodu (src/) düzelt. Test yanlışsa dur ve ana oturuma bildir; testi "
    "test-yazari değiştirir."
)


def karar_ver(girdi: dict) -> int:
    """Hook girdisine göre çıkış kodunu döner: 0 izin, 2 engel."""
    if girdi.get("agent_type") not in KILITLI_AJANLAR:
        return 0
    return 2 if arac_korunana_yaziyor_mu(girdi, KORUNAN) else 0


def main() -> int:
    try:
        girdi = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("tests_kilidi: hook girdisi okunamadı, güvenli tarafta kalınıyor.", file=sys.stderr)
        return 2
    kod = karar_ver(girdi)
    if kod == 2:
        print(MESAJ, file=sys.stderr)
    return kod


if __name__ == "__main__":
    sys.exit(main())
