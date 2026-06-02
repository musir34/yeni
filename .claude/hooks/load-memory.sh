#!/usr/bin/env bash
# SessionStart hook: proje hafızasını (memory/*.md) oturum başında context'e yükler.
# "Her işe başladığında Obsidian/memory'yi kontrol et" protokolünün garantili (harness tarafından çalıştırılan) hali.
set -euo pipefail

MEM_DIR="$HOME/.claude/projects/-Users-abdurrahmankuli-Documents-Webs-yeni/memory"

[ -d "$MEM_DIR" ] || exit 0

echo "## 📌 Proje Hafızası (memory/) — oturum başında otomatik yüklendi"
echo "Aşağıdaki kalıcı notlar bu projeye özeldir. İşe başlamadan önce dikkate al."
echo

shopt -s nullglob
for f in "$MEM_DIR"/*.md; do
  base="$(basename "$f")"
  # MEMORY.md indeksi harness tarafından zaten yükleniyor; tam dosyaları ekle.
  [ "$base" = "MEMORY.md" ] && continue
  echo "### ${base}"
  cat "$f"
  echo
done

exit 0
