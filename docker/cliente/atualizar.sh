#!/usr/bin/env bash
# RM SOFT - atualiza o servidor do cliente para a versão nova (os dados ficam; a base é atualizada sozinha).
# Copie primeiro os ficheiros do pacote novo (rmsoft-docker-<versão>) por cima desta pasta - o .env fica - e depois:
#   sudo ./atualizar.sh
set -euo pipefail
cd "$(dirname "$0")"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.linux.yml --env-file .env)
[ "$(id -u)" -eq 0 ] || { echo "execute com sudo: sudo ./atualizar.sh"; exit 1; }
[ -f .env ] || { echo "Falta o .env: esta pasta não é uma instalação (use ./instalar.sh)."; exit 1; }
[ -f VERSAO ] || { echo "Falta o ficheiro VERSAO: copie o pacote novo inteiro para esta pasta."; exit 1; }
VERSAO=$(head -n 1 VERSAO | tr -d '\r[:space:]')
set -a; . ./.env; set +a

stamp=$(date +%Y-%m-%d_%H%M)
echo "== 1/4 Cópia da base antes de atualizar"
mkdir -p "${BACKUP_DIR}/base"
"${COMPOSE[@]}" exec -T postgres pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc > "${BACKUP_DIR}/base/antes_atualizacao_${stamp}.dump"
echo "   ${BACKUP_DIR}/base/antes_atualizacao_${stamp}.dump"

echo "== 2/4 Imagens da versão ${VERSAO}"
if docker image inspect "rmsoft-backend:${VERSAO}" >/dev/null 2>&1; then
  echo "   já carregadas"
else
  images="rmsoft-imagens-${VERSAO}.tar.gz"
  [ -f "$images" ] || { echo "ERRO: $images não está nesta pasta (copie o pacote novo inteiro)"; exit 1; }
  docker load -i "$images"
fi
if grep -q '^APP_VERSION=' .env; then sed -i "s|^APP_VERSION=.*|APP_VERSION=${VERSAO}|" .env; else echo "APP_VERSION=${VERSAO}" >> .env; fi

echo "== 3/4 Reiniciar com a versão nova"
"${COMPOSE[@]}" up -d

echo "== 4/4 Limpar as versões antigas"
for repo in rmsoft-backend rmsoft-web; do
  docker images "$repo" --format '{{.Tag}}' | grep -vx "${VERSAO}" | while read -r tag; do
    docker image rm "${repo}:${tag}" >/dev/null 2>&1 || true
  done
done
for f in rmsoft-imagens-*.tar.gz; do [ "$f" = "rmsoft-imagens-${VERSAO}.tar.gz" ] || rm -f "$f"; done
echo "Atualizado para a versão ${VERSAO}. Os postos: Ctrl+F5 no navegador."
