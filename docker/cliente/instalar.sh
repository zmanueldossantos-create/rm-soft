#!/usr/bin/env bash
# RM SOFT - instala o RM SOFT no servidor do cliente (Ubuntu Server 22.04 / 24.04).
# Feito pelo técnico da RM SOFT, uma vez:   sudo ./instalar.sh
# Pode ser repetido sem perigo: nunca muda as palavras-passe já criadas nem apaga dados.
set -euo pipefail
cd "$(dirname "$0")"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.linux.yml --env-file .env)

say()  { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31mERRO: %s\033[0m\n' "$1"; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "execute com sudo: sudo ./instalar.sh"
grep -qi ubuntu /etc/os-release || echo "Aviso: testado em Ubuntu Server; noutro Linux pode precisar de ajustes."

say "1/7 Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh || fail "não foi possível instalar o Docker (sem internet?)"
fi
systemctl enable --now docker >/dev/null
docker compose version >/dev/null || fail "o Docker Compose não está disponível"

say "2/7 Nome do servidor na rede (rmsoft.local)"
apt-get install -y -qq avahi-daemon >/dev/null 2>&1 || echo "Aviso: avahi não instalado - use o endereço IP."
if [ "$(hostname)" != "rmsoft" ]; then
  read -r -p "Chamar este servidor 'rmsoft' (os postos abrem http://rmsoft.local)? [S/n] " ans
  if [ "${ans:-S}" != "n" ] && [ "${ans:-S}" != "N" ]; then hostnamectl set-hostname rmsoft; fi
fi

say "3/7 Configuração (.env)"
if [ ! -f .env ]; then
  cp .env.example .env
  read -r -p "Nome do cliente (ex.: Padaria Kilamba): " client
  read -r -p "Pasta das cópias de segurança [/srv/rmsoft-copias]: " backups
  read -r -p "Porta para os postos [80]: " port
  secret() { head -c 48 /dev/urandom | base64 | tr -d '/+=\n' | cut -c1-48; }
  sed -i "s|^CLIENT_NAME=.*|CLIENT_NAME=${client}|" .env
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(secret)|" .env
  sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$(secret)|" .env
  sed -i "s|^BACKUP_DIR=.*|BACKUP_DIR=${backups:-/srv/rmsoft-copias}|" .env
  sed -i "s|^HTTP_PORT=.*|HTTP_PORT=${port:-80}|" .env
  chmod 600 .env
  echo ".env criado (palavras-passe geradas - não o envie a ninguém)."
else
  echo ".env já existe: mantido (as palavras-passe nunca mudam)."
fi
set -a; . ./.env; set +a
[ -n "${JWT_SECRET_KEY}" ] && [ -n "${POSTGRES_PASSWORD}" ] || fail ".env incompleto (JWT_SECRET_KEY / POSTGRES_PASSWORD)"
[ -s /etc/machine-id ] || fail "/etc/machine-id em falta: necessário para a licença"

say "4/7 Pastas das cópias"
mkdir -p "${BACKUP_DIR}/empresas" "${BACKUP_DIR}/base"
chown -R 1000:1000 "${BACKUP_DIR}/empresas"   # the application's user in the container

say "5/7 Construir e arrancar (alguns minutos na primeira vez)"
"${COMPOSE[@]}" up -d --build
echo -n "A aguardar o arranque"
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" >/dev/null 2>&1; then
    echo " - pronto."; break
  fi
  echo -n "."; sleep 5
done

say "6/7 Conta SUPER_ADMIN da RM SOFT"
"${COMPOSE[@]}" exec backend python -m app.cli create-superadmin --if-none

say "7/7 Pronto"
code=$("${COMPOSE[@]}" exec -T backend python -m app.cli installation-code | tr -d '\r')
port_suffix=""; [ "${HTTP_PORT:-80}" != "80" ] && port_suffix=":${HTTP_PORT}"
echo "Cliente:                 ${CLIENT_NAME:-?}"
echo "Abrir nos postos:        http://$(hostname).local${port_suffix}"
for ip in $(hostname -I); do echo "                         http://${ip}${port_suffix}"; done
echo "Código de instalação:    ${code}"
echo
echo "Próximo passo: gerar a licença deste código na plataforma RM SOFT (Empresas > Contrato > Gerar licença)"
echo "e importá-la em Definições da Empresa > Licença (ou Empresas > Licença, como SUPER_ADMIN)."
