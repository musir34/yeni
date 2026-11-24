#!/usr/bin/env bash
# SessionStart hook: oturum başında proje hafızasının (memory/) yerini hatırlatır.
# "Her işe başladığında Obsidian/memory'yi kontrol et" protokolünün garantili (harness tarafından çalıştırılan) hali.
# Notlar tam metin YÜKLENMEZ (120+ not ≈ 100k token); MEMORY.md indeksi harness tarafından zaten yükleniyor,
# ilgili not konuya göre açılır. Mac + Windows uyumlu: yol $CLAUDE_PROJECT_DIR'dan türetilir.
set -euo pipefail

PROJ="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && (pwd -W 2>/dev/null || pwd))}"
SLUG="$(printf '%s' "$PROJ" | sed 's/[^A-Za-z0-9]/-/g')"
MEM_DIR="$HOME/.claude/projects/$SLUG/memory"

[ -d "$MEM_DIR" ] || exit 0

shopt -s nullglob
NOTES=("$MEM_DIR"/*.md)

echo "## 📌 Proje Hafızası (memory/)"
echo "Klasör: $MEM_DIR (${#NOTES[@]} dosya)."
echo "İşe başlamadan önce MEMORY.md indeksine bak; konuyla ilgili notları tam metin aç ve dikkate al."

exit 0
