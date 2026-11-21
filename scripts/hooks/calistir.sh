#!/bin/sh
# Bir Python hook betiğini, sistemde bulunan Python 3 ile çalıştırır.
#
# Kullanım: sh scripts/hooks/calistir.sh <betik.py>
#
# Windows'ta `python3` çoğu zaman Microsoft Store yer tutucusudur ve çalışmaz;
# bu yüzden python3, python ve py sırayla denenir. Hiçbiri yoksa hook
# güvenli tarafta kalır ve araç çağrısını engeller (çıkış kodu 2).

betik="$(dirname "$0")/$1"

for p in python3 python py; do
  if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    exec "$p" "$betik"
  fi
done

echo "Hook çalıştırılamadı: Python 3.9+ bulunamadı ($1). Güvenlik için araç çağrısı engellendi." >&2
exit 2
