#!/usr/bin/env python3
"""İlk kurulum denetimi: veritabanında kullanıcı yoksa M&P ve giriş kalite hesaplarını ortamdan açar.

Parolalar ortam değişkenlerinden (`MALZEME_KABUL_MP_PAROLASI`,
`MALZEME_KABUL_GK_PAROLASI`) ya da Docker secrets için dosyadan
(`MALZEME_KABUL_MP_PAROLASI_DOSYASI`, `MALZEME_KABUL_GK_PAROLASI_DOSYASI`)
okunur; kullanıcı adları `MALZEME_KABUL_MP_KULLANICI` / `MALZEME_KABUL_GK_KULLANICI`
(varsayılan "mp" / "gk"). Varsayılan parola yoktur: parola eksik ya da zayıfsa
sıfırdan farklı çıkış koduyla biter ve `docker/baslat.sh` Streamlit'i başlatmaz.
Kullanıcı zaten varsa ortam değişkeni gerekmez; ancak bir hesap bilinen bir deneme
parolasıyla kurulmuşsa (eski `--ornek-kullanicilar` birimi) her açılışta hata verir.
Parolalar hiçbir çıktıya yazılmaz.

Kullanım:
  python scripts/ilk_kurulum.py --db /veri/katalog.sqlite
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from malzeme_kabul.arayuz.kimlik import KimlikHatasi, kullanicilar, ortamdan_kullanicilar

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_DB = KOK / "data" / "calisma" / "katalog.sqlite"


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("--db", default=str(VARSAYILAN_DB))
    args = ayr.parse_args(argv)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    baglanti = sqlite3.connect(args.db)
    try:
        olusan = ortamdan_kullanicilar(os.environ, baglanti)
        if olusan:
            for k in olusan:
                print(f"ilk kullanıcı oluşturuldu: {k.ad} ({k.rol_adi})")
        else:
            print(f"kullanıcılar zaten kurulu ({len(kullanicilar(baglanti))}); ortamdaki parolalar kullanılmadı")
    except KimlikHatasi as hata:
        print(f"HATA: ilk kurulum yapılamadı: {hata}", file=sys.stderr)
        print("Uygulama başlatılmadı. Parola belirleme ve değiştirme: README, \"Ağsız Docker\" bölümü.",
              file=sys.stderr)
        return 2
    finally:
        baglanti.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
