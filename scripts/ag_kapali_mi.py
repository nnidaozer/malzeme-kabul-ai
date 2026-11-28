#!/usr/bin/env python3
"""Bu makineden (konteynerden) dış ağa çıkılamadığını gösterir. Ağ kapalıysa 0, bir çıkış bulunursa 1 döner.

Denenenler: DNS çözümleme (pypi.org, github.com), adresle TCP bağlantısı
(1.1.1.1:443, 8.8.8.8:53, 140.82.112.3:443) ve HTTPS isteği (https://pypi.org).
Her deneme kısa zaman aşımıyla yapılır; biri başarılı olursa ağ açıktır.

HTTPS denemesinde sunucudan gelen HTTP hatası (ör. 403, 407) ve TLS/SSL hatası
da dışarıdaki bir uca ulaşıldığını gösterir; bunlar başarılı (ağ açık) sayılır.
`vekil_dahil=True` verilir ve sistemde vekil ayarı varsa aynı istek sistem
vekili üzerinden de denenir ("HTTPS vekil üzerinden ..."). Varsayılan
`vekil_dahil=False`: konteyner denetimi (scripts/ag_testi.sh) yalnız doğrudan
çıkışa bakar.

Kullanım (konteynerde): python scripts/ag_kapali_mi.py
"""

from __future__ import annotations

import socket
import ssl
import sys
import urllib.error
import urllib.request

ALAN_ADLARI = ["pypi.org", "github.com"]
ADRESLER = [("1.1.1.1", 443), ("8.8.8.8", 53), ("140.82.112.3", 443)]
URL = "https://pypi.org/simple/"


def _https_dene(acici, zaman_asimi: float) -> tuple[bool, str]:
    """(dışarı çıkıldı mı, ayrıntı). HTTP ve SSL hataları uca ulaşıldığını gösterir (temkinli taraf)."""
    try:
        with acici.open(URL, timeout=zaman_asimi) as cevap:
            return True, str(cevap.status)
    except urllib.error.HTTPError as hata:  # URLError'dan önce: sunucu yanıt verdi
        return True, f"HTTPError {hata.code}"
    except ssl.SSLError as hata:
        return True, type(hata).__name__
    except urllib.error.URLError as hata:
        if isinstance(hata.reason, ssl.SSLError):  # urllib SSL hatasını URLError içine sarar
            return True, f"URLError({type(hata.reason).__name__})"
        return False, type(hata).__name__
    except Exception as hata:  # noqa: BLE001 - diğer her hata "çıkış yok" demektir
        return False, type(hata).__name__


def denemeler(zaman_asimi: float = 3.0, vekil_dahil: bool = False) -> list[tuple[str, bool, str]]:
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
    basarili, ayrinti = _https_dene(urllib.request.build_opener(urllib.request.ProxyHandler({})), zaman_asimi)
    sonuc.append((f"HTTPS {URL}", basarili, ayrinti))
    if vekil_dahil:
        vekil = urllib.request.getproxies()
        if vekil:
            acici = urllib.request.build_opener(urllib.request.ProxyHandler(vekil))
            basarili, ayrinti = _https_dene(acici, zaman_asimi)
            sonuc.append((f"HTTPS vekil üzerinden {URL}", basarili, ayrinti))
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
