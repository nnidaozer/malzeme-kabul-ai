#!/bin/sh
# Oturum kurulumu: depodaki Claude ayarlarını kullanıcı düzeyine (~/.claude/) kurar.
#
# Bulut oturumları depo klasöründe değil, bir üst klasörde başlayabiliyor. O
# zaman depodaki .claude/settings.json (data/gold deny kuralı, hook'lar) ve
# .claude/agents/ yüklenmiyor. Bu betik:
#   1. scripts/hooks/ altındaki hook dosyalarını ~/.claude/hooks/malzeme-kabul-ai/
#      altına kopyalar,
#   2. .claude/agents/*.md dosyalarını ~/.claude/agents/ altına kopyalar,
#   3. .claude/settings.json içindeki deny kurallarını ve hook'ları, yolları
#      mutlak yola çevirerek ~/.claude/settings.json ile birleştirir.
#
# Betik tekrar tekrar çalıştırılabilir: kendi eklediği hook'ları ve deny
# kurallarını her seferinde yenisiyle değiştirir, ~/.claude/settings.json
# içindeki başka ayarlara dokunmaz.
#
# Kullanım: sh scripts/oturum_kurulum.sh

set -eu

DEPO="$(cd "$(dirname "$0")/.." && pwd -P)"
CLAUDE_EV="${HOME}/.claude"
HOOK_HEDEF="${CLAUDE_EV}/hooks/malzeme-kabul-ai"
AJAN_HEDEF="${CLAUDE_EV}/agents"

PY=""
for p in python3 python py; do
  if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    PY="$p"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "oturum_kurulum: Python 3.9+ bulunamadı, kurulum yapılmadı." >&2
  exit 1
fi

mkdir -p "$HOOK_HEDEF" "$AJAN_HEDEF"
cp "$DEPO"/scripts/hooks/*.py "$DEPO"/scripts/hooks/calistir.sh "$HOOK_HEDEF"/
cp "$DEPO"/.claude/agents/*.md "$AJAN_HEDEF"/

"$PY" - "$DEPO" "$CLAUDE_EV/settings.json" "$HOOK_HEDEF" <<'PYEOF'
import json
import os
import re
import shlex
import sys

depo, hedef_ayar, hook_dizini = sys.argv[1:4]
ISARET = hook_dizini.rstrip("/") + "/"

with open(os.path.join(depo, ".claude", "settings.json"), encoding="utf-8") as f:
    kaynak = json.load(f)

if os.path.exists(hedef_ayar):
    with open(hedef_ayar, encoding="utf-8") as f:
        ayar = json.load(f)
else:
    ayar = {}

HOOK_KALIBI = re.compile(r'^sh "\$\{CLAUDE_PROJECT_DIR\}/scripts/hooks/calistir\.sh" (\S+)$')


def komutu_cevir(komut):
    m = HOOK_KALIBI.match(komut)
    if not m:
        sys.exit(f"oturum_kurulum: tanınmayan hook komutu, kurulum yarıda bırakıldı: {komut}")
    return "CLAUDE_PROJECT_DIR={} sh {} {}".format(
        shlex.quote(depo), shlex.quote(ISARET + "calistir.sh"), shlex.quote(m.group(1))
    )


def kurali_cevir(kural):
    # "Edit(/data/gold/**)" -> "Edit(//<depo>/data/gold/**)"
    m = re.match(r"^(\w+)\((/[^/].*)\)$", kural)
    if not m:
        return kural
    return f"{m.group(1)}(/{depo.rstrip('/')}{m.group(2)})"


def bizim_mi(grup):
    return any(ISARET in h.get("command", "") for h in grup.get("hooks", []))


# Deny kuralları: eski kopyalarımızı at, yenilerini ekle.
izinler = ayar.setdefault("permissions", {})
yeni_kurallar = [kurali_cevir(k) for k in kaynak.get("permissions", {}).get("deny", [])]
depo_oneki = "(/" + depo.rstrip("/") + "/"
deny = [k for k in izinler.get("deny", []) if depo_oneki not in k]
for k in yeni_kurallar:
    if k not in deny:
        deny.append(k)
izinler["deny"] = deny

# Hook'lar: her olayda eski gruplarımızı at, yenilerini ekle.
hooklar = ayar.setdefault("hooks", {})
for olay in list(hooklar):
    hooklar[olay] = [g for g in hooklar[olay] if not bizim_mi(g)]
    if not hooklar[olay]:
        del hooklar[olay]
for olay, gruplar in kaynak.get("hooks", {}).items():
    for grup in gruplar:
        yeni = dict(grup)
        yeni["hooks"] = [dict(h, command=komutu_cevir(h["command"])) for h in grup["hooks"]]
        hooklar.setdefault(olay, []).append(yeni)

gecici = hedef_ayar + ".tmp"
with open(gecici, "w", encoding="utf-8") as f:
    json.dump(ayar, f, ensure_ascii=False, indent=2)
    f.write("\n")
os.replace(gecici, hedef_ayar)
PYEOF

echo "oturum_kurulum: ayarlar $CLAUDE_EV/settings.json dosyasına, hook'lar $HOOK_HEDEF klasörüne, ajanlar $AJAN_HEDEF klasörüne kuruldu."
