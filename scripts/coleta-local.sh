#!/usr/bin/env bash
# Coleta diária na sua máquina (o runner do GitHub é bloqueado pelo Cloudflare da ANVISA).
# Roda feed + lista curada, commita o que mudou em data/ e faz push; o push dispara o deploy do site.
#
# Cron (06h, todo dia):  0 6 * * *  /home/uitor/code/bulario/scripts/coleta-local.sh >> ~/.local/state/buladiff-coleta.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"

git pull --ff-only --quiet
uv run bulario feed --baixar
uv run bulario fetch --curados

if git diff --quiet -- data && [ -z "$(git ls-files --others --exclude-standard data)" ]; then
  echo "$(date -Is) sem mudanças"
  exit 0
fi

git add data
git commit -q -m "Arquivo: $(date +%Y-%m-%d)"
git push --quiet
echo "$(date -Is) publicado: $(git rev-parse --short HEAD)"
