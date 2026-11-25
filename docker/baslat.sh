#!/bin/sh
# Konteyner girişi: katalog yoksa örnek veriyle kurar, sonra Streamlit'i başlatır.
# MALZEME_KABUL_ORNEK_KULLANICILAR=1 ise deneme kullanıcıları (mp, gk) da açılır.
set -eu
if [ ! -f "$MALZEME_KABUL_DB" ]; then
  if [ "${MALZEME_KABUL_ORNEK_KULLANICILAR:-0}" = "1" ]; then
    python /uygulama/scripts/katalog_kur.py --db "$MALZEME_KABUL_DB" --ornek --ornek-kullanicilar
  else
    python /uygulama/scripts/katalog_kur.py --db "$MALZEME_KABUL_DB" --ornek
  fi
fi
exec streamlit run /uygulama/src/malzeme_kabul/arayuz/uygulama.py
