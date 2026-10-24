#!/usr/bin/env bash
# RM SOFT - atualiza o servidor do cliente para a versão nova (os dados ficam; a base é atualizada sozinha).
#   sudo ./atualizar.sh
set -euo pipefail
cd "$(dirname "$0")"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.linux.yml --env-file .env)
[ "$(id -u)" -eq 0 ] || { echo "execute com sudo: sudo ./atualizar.sh"; exit 1; }
[ -f .env ] || { echo "Falta o .env: esta pasta não é uma instalação (use ./instalar.sh)."; exit 1; }
set -a; . ./.env; set +a

stamp=$(date +%Y-%m-%d_%H%M)
echo "== 1/3 Cópia da base antes de atualizar"
mkdir -p "${BACKUP_DIR}/base"
"${COMPOSE[@]}" exec -T postgres pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc > "${BACKUP_DIR}/base/antes_atualizacao_${stamp}.dump"
echo "   ${BACKUP_DIR}/base/antes_atualizacao_${stamp}.dump"

echo "== 2/3 Versão nova"
if [ -d ../../.git ]; then
  git -C ../.. pull --ff-only
else
  echo "   (sem git: copie primeiro a pasta nova do RM SOFT por cima desta, mantendo o .env)"
fi

echo "== 3/3 Reconstruir e reiniciar"
"${COMPOSE[@]}" up -d --build
docker image prune -f >/dev/null
echo "Atualizado. Os postos: Ctrl+F5 no navegador."
