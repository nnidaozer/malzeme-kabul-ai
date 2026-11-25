#!/usr/bin/env python3
"""Yerel kapı: host'tan gelen bağlantıyı dışa kapalı ağdaki uygulamaya aktaran TCP aktarıcısı.

Docker, yalnız `internal` ağdaki bir konteynerin portunu host'a açmaz. Bu kapı
iki ağdadır: host'a yalnız 127.0.0.1:8501'den açılır ve gelen her bağlantıyı
yalnız `HEDEF` (uygulama:8501) adresine aktarır. Başka hiçbir yere bağlanmaz;
uygulamanın kendisinin dış ağa çıkışı yoktur.
"""

from __future__ import annotations

import os
import socket
import threading

DINLE = ("0.0.0.0", int(os.environ.get("KAPI_PORTU", "8501")))
HEDEF = (os.environ.get("KAPI_HEDEFI", "uygulama"), int(os.environ.get("KAPI_HEDEF_PORTU", "8501")))


def _aktar(kaynak: socket.socket, hedef: socket.socket) -> None:
    try:
        while veri := kaynak.recv(65536):
            hedef.sendall(veri)
    except OSError:
        pass
    finally:
        for s in (kaynak, hedef):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _baglanti(istemci: socket.socket) -> None:
    try:
        uygulama = socket.create_connection(HEDEF, timeout=10)
    except OSError:
        istemci.close()
        return
    uygulama.settimeout(None)
    threading.Thread(target=_aktar, args=(istemci, uygulama), daemon=True).start()
    threading.Thread(target=_aktar, args=(uygulama, istemci), daemon=True).start()


def main() -> None:
    sunucu = socket.create_server(DINLE, reuse_port=False)
    print(f"yerel kapı: {DINLE[0]}:{DINLE[1]} -> {HEDEF[0]}:{HEDEF[1]}", flush=True)
    while True:
        istemci, _ = sunucu.accept()
        _baglanti(istemci)


if __name__ == "__main__":
    main()
