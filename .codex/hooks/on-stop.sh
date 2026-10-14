#!/usr/bin/env bash
# Stop hook: bir iş bittiğinde, projede KAYDEDİLMEMİŞ KOD değişikliği varsa
#   1) bağımsız Codex incelemesi ve
#   2) memory/ güncellemesi
# hatırlatır. Her değişiklik-seti için yalnızca BİR kez tetiklenir (state-hash),
# sohbet/boş turlarda ve değişiklik yoksa sessiz kalır.
set -uo pipefail

PROJ="/Users/abdurrahmankuli/Documents/Webs/yeni"
STATE="$HOME/.claude/projects/-Users-abdurrahmankuli-Documents-Webs-yeni/.last-stop-hash"

INPUT="$(cat)"

# Sonsuz döngü koruması: bu Stop bir önceki block sonucu tetiklendiyse çık.
case "$INPUT" in
  *'"stop_hook_active":true'* | *'"stop_hook_active": true'*) exit 0 ;;
esac

# Yalnızca gerçek kod değişikliklerini izle (.claude/ altını yok say).
STATUS="$(git -C "$PROJ" status --porcelain 2>/dev/null | grep -v '\.claude/' || true)"
[ -z "$STATUS" ] && exit 0   # kaydedilmemiş kod değişikliği yok → sessiz

HASH="$(printf '%s' "$STATUS" | shasum 2>/dev/null | awk '{print $1}')"
LAST="$(cat "$STATE" 2>/dev/null || true)"
[ "$HASH" = "$LAST" ] && exit 0   # bu değişiklik seti için zaten hatırlatıldı

printf '%s' "$HASH" > "$STATE" 2>/dev/null || true

cat <<'EOF'
{"decision":"block","reason":"Kod değişikliği algılandı — bitirmeden önce (gereksizse atla):\n1) Bağımsız çapraz-model incelemesi için `/codex:review` çalıştır (Codex plugin kurulu değilse bu adımı atla).\n2) Bu oturumda NEYİ NEDEN değiştirdiğini `memory/` klasörüne kısa bir proje notu olarak kaydet (yalnızca yeni/kalıcı bir bilgi varsa; yoksa atla). MEMORY.md indeksine de bir satır ekle.\nİkisini yaptıysan ya da bu değişiklikler önemsizse, normal şekilde bitir."}
EOF
exit 0
