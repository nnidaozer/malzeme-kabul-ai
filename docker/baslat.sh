#!/bin/sh
# Konteyner girişi: katalog yoksa örnek veriyle kurar, ilk kullanıcıları ortamdan
# açar (scripts/ilk_kurulum.py), sonra Streamlit'i başlatır.
#
# Varsayılan parola yoktur. Veritabanında kullanıcı yoksa MALZEME_KABUL_MP_PAROLASI
# ve MALZEME_KABUL_GK_PAROLASI (ya da *_PAROLASI_DOSYASI) zorunludur; eksik ya da
# zayıfsa ilk kurulum hata verir ve Streamlit başlamaz (set -e).
set -eu
KOK="${MALZEME_KABUL_KOK:-/uygulama}"
if [ ! -f "$MALZEME_KABUL_DB" ]; then
  python "$KOK/scripts/katalog_kur.py" --db "$MALZEME_KABUL_DB" --ornek
fi
python "$KOK/scripts/ilk_kurulum.py" --db "$MALZEME_KABUL_DB"
exec streamlit run "$KOK/src/malzeme_kabul/arayuz/uygulama.py"
