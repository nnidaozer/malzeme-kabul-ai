#!/bin/sh
# Ağsız Docker testi: uygulamayı docker compose ile kaldırır ve
#   1. uygulama konteynerinden dış ağa çıkılamadığını (DNS, TCP, HTTPS),
#   2. uygulama konteynerinde varsayılan yol (default route) olmadığını,
#   3. uygulamanın yine de host'tan 127.0.0.1:8501 üzerinden çalıştığını
# gösterir. Hepsi geçerse 0 döner. İsteğe bağlı: AG_TESTI_KAPAT=1 bitince kapatır,
# AG_TESTI_INSA=0 imajı yeniden kurmaz (önceden kurulmuş malzeme-kabul:yerel kullanılır).
# AG_TESTI_KONTROL=1 ayrıca pozitif kontrol yapar: aynı denetim dış ağa açık "kapi"
# konteynerinde çalıştırılır ve ağı AÇIK bulmalıdır (denetimin gerçekten çıkışı
# yakalayabildiğini gösterir; internetsiz makinede bu adım çalıştırılmaz).
#
# Kullanım: sh scripts/ag_testi.sh
set -eu
cd "$(dirname "$0")/.."

if [ "${AG_TESTI_INSA:-1}" = "1" ]; then
  docker compose up -d --build
else
  docker compose up -d
fi
trap '[ "${AG_TESTI_KAPAT:-0}" = "1" ] && docker compose down -v' EXIT

echo "== 1. Uygulama konteynerinden dış ağ denemeleri"
docker compose exec -T uygulama python /uygulama/scripts/ag_kapali_mi.py

echo "== 2. Uygulama konteynerinin yönlendirme tablosu (varsayılan yol olmamalı)"
yollar="$(docker compose exec -T uygulama sh -c 'cat /proc/net/route')"
echo "$yollar"
if echo "$yollar" | awk 'NR > 1 && $2 == "00000000" { bulundu = 1 } END { exit !bulundu }'; then
  echo "HATA: uygulama konteynerinde varsayılan yol var" >&2
  exit 1
fi
echo "varsayılan yol yok"

echo "== 3. Uygulama host'tan erişilebilir mi (127.0.0.1:8501)"
i=0
until python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8501/_stcore/health', timeout=3).read().strip() == b'ok' else 1)" 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -ge 30 ]; then
    echo "HATA: uygulama 60 sn içinde yanıt vermedi" >&2
    docker compose logs --tail 50 uygulama >&2
    exit 1
  fi
  sleep 2
done
echo "uygulama çalışıyor: http://127.0.0.1:8501 (sağlık: ok)"
if [ "${AG_TESTI_KONTROL:-0}" = "1" ]; then
  echo "== 4. Pozitif kontrol: dış ağa açık kapı konteynerinde aynı denetim ağı açık bulmalı"
  if docker compose exec -T kapi python /uygulama/scripts/ag_kapali_mi.py; then
    echo "HATA: denetim açık ağı yakalayamadı" >&2
    exit 1
  fi
  echo "denetim açık ağı yakaladı"
fi
echo "AĞ TESTİ GEÇTİ: uygulama ağsız çalışıyor."
