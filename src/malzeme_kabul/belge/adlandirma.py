"""Belge dosya adından belge numarası ve revizyon harfi."""

from __future__ import annotations

import re
from pathlib import Path


def belge_no_ve_revizyon(dosya_adi: str) -> tuple[str, str]:
    """'MIL-PRF-23377K.pdf' -> ('MIL-PRF-23377', 'K')."""
    m = re.fullmatch(r"(.+\d)([A-Z])", Path(dosya_adi).stem)
    if not m:
        raise ValueError(f"dosya adından belge no ve revizyon çıkarılamadı: {dosya_adi}")
    return m.group(1), m.group(2)
