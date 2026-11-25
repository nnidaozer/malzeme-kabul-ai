#!/usr/bin/env python3
"""Bu makineden (konteynerden) dış ağa çıkılamadığını gösterir. Ağ kapalıysa 0, bir çıkış bulunursa 1 döner.

Denenenler: DNS çözümleme (pypi.org, github.com), adresle TCP bağlantısı
(1.1.1.1:443, 8.8.8.8:53, 140.82.112.3:443) ve HTTPS isteği (https://pypi.org).
Her deneme kısa zaman aşımıyla yapılır; biri başarılı olursa ağ açıktır.

Kullanım (konteynerde): python scripts/ag_kapali_mi.py
"""

from __future__ import annotations

import socket
import sys
import urllib.request

ALAN_ADLARI = ["pypi.org", "github.com"]
ADRESLER = [("1.1.1.1", 443), ("8.8.8.8", 53), ("140.82.112.3", 443)]
URL = "https://pypi.org/simple/"


def denemeler(zaman_asimi: float = 3.0) -> list[tuple[str, bool, str]]:
    """(deneme, başarılı mı, ayrıntı) listesi."""
    sonuc = []
    for ad in ALAN_ADLARI:
        try:
            adres = socket.gethostbyname(ad)
            sonuc.append((f"DNS {ad}", True, adres))
        except OSError as hata:
            sonuc.append((f"DNS {ad}", False, type(hata).__name__))
    for host, port in ADRESLER:
        try:
            with socket.create_connection((host, port), timeout=zaman_asimi):
                sonuc.append((f"TCP {host}:{port}", True, "bağlandı"))
        except OSError as hata:
            sonuc.append((f"TCP {host}:{port}", False, type(hata).__name__))
    try:
        acici = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with acici.open(URL, timeout=zaman_asimi) as cevap:
            sonuc.append((f"HTTPS {URL}", True, str(cevap.status)))
    except Exception as hata:  # noqa: BLE001 - her türlü hata "çıkış yok" demektir
        sonuc.append((f"HTTPS {URL}", False, type(hata).__name__))
    return sonuc


def main() -> int:
    sonuc = denemeler()
    for ad, basarili, ayrinti in sonuc:
        print(f"{'AÇIK  ' if basarili else 'kapalı'} {ad}: {ayrinti}")
    acik = [ad for ad, basarili, _ in sonuc if basarili]
    if acik:
        print(f"AĞ AÇIK: {len(acik)} deneme dışarı çıktı")
        return 1
    print("ağ kapalı: hiçbir deneme dışarı çıkamadı")
    return 0


if __name__ == "__main__":
    sys.exit(main())
