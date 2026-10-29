#!/usr/bin/env bash
# HomeDock OS installer for a fresh Ubuntu/Debian server.
#   curl -fsSL https://raw.githubusercontent.com/c-orter/HomeDockOS/main/install.sh | sudo bash
set -Eeuo pipefail

REPO="${HOMEDOCK_REPO:-c-orter/HomeDockOS}"
REF="${HOMEDOCK_REF:-v2.7.0.1}"
DIR="${HOMEDOCK_DIR:-/opt/homedock}"
TZ_NAME="${TZ:-$(cat /etc/timezone 2>/dev/null || echo UTC)}"

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run as root: curl -fsSL <url> | sudo bash"
command -v apt-get >/dev/null || die "this installer supports Ubuntu and Debian"

say "Installing prerequisites"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ca-certificates tar >/dev/null

if ! command -v docker >/dev/null; then
  say "Installing Docker"
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || apt-get install -y -qq docker-compose-plugin >/dev/null
systemctl enable --now docker >/dev/null 2>&1 || true

for port in 80 443; do
  if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
    die "port $port is already in use; stop whatever listens on it and run this again"
  fi
done

say "Downloading HomeDock OS $REF"
mkdir -p "$DIR"
rm -rf "$DIR/src.new" && mkdir "$DIR/src.new"
curl -fsSL "https://github.com/$REPO/archive/refs/tags/$REF.tar.gz" | tar -xz --strip-components=1 -C "$DIR/src.new"
rm -rf "$DIR/src" && mv "$DIR/src.new" "$DIR/src"

cat > "$DIR/docker-compose.yml" <<YAML
services:
  homedock:
    build: ./src
    image: homedock-os:local
    container_name: homedock-os
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - $DIR/homedock-data/DATA:/DATA
      - $DIR/homedock-data/config:/homedock/config
      - $DIR/homedock-data/compose:/homedock/compose-link
      - $DIR/homedock-data/packages:/homedock/_user_packages
      - $DIR/homedock-data/dropzone:/homedock/dropzone
      - $DIR/homedock-data/logs:/homedock/logs
      - /var/run/docker.sock:/var/run/docker.sock
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - default
      - homedock_network
    labels:
      - "HDDockerInDocker=true"
    environment:
      - TZ=$TZ_NAME
      - PYTHONUNBUFFERED=1

networks:
  homedock_network:
    name: homedock_network
YAML

say "Building and starting HomeDock OS (a few minutes the first time)"
docker compose -f "$DIR/docker-compose.yml" up -d --build

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  say "Opening ports 80 and 443 in ufw"
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
fi

IP="$(curl -fsS https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
say "Done. Open http://$IP/ to finish setup."
echo "Update later: re-run this installer with HOMEDOCK_REF=<newer tag>. Your data stays in $DIR/homedock-data."
