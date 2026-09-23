#!/usr/bin/env bash
# Link agent-kit into omp. Links, never copies: `git pull` in this repo updates every
# install, and there is no second copy to drift.
#
#   ./install.sh            link everything
#   ./install.sh --status   show what is linked
#
# Existing real files at a target are left alone and reported; move them away and re-run.
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OMP="${OMP_HOME:-$HOME/.omp}"
SKILLS="$OMP/.agents/skills"
EXTENSIONS="$OMP/agent/extensions"

link() { # link <source> <target>
  local src="$1" dst="$2"
  if [[ "${STATUS:-}" == 1 ]]; then
    if [[ -L "$dst" && "$(readlink "$dst")" == "$src" ]]; then echo "linked    $dst"
    elif [[ -e "$dst" ]]; then echo "conflict  $dst"
    else echo "missing   $dst"; fi
    return
  fi
  mkdir -p "$(dirname "$dst")"
  if [[ -L "$dst" ]]; then ln -sfn "$src" "$dst"; echo "linked    $dst"
  elif [[ -e "$dst" ]]; then echo "conflict  $dst (real file, left untouched)"; CONFLICT=1
  else ln -s "$src" "$dst"; echo "linked    $dst"; fi
}

[[ "${1:-}" == "--status" ]] && STATUS=1
CONFLICT=0
for dir in "$KIT"/.agents/skills/*/; do
  name="$(basename "$dir")"
  link "$KIT/.agents/skills/$name" "$SKILLS/$name"
done
for file in "$KIT"/agent/extensions/*.ts; do
  link "$file" "$EXTENSIONS/$(basename "$file")"
done
exit "$CONFLICT"
