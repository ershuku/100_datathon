#!/usr/bin/env bash
# Self-hosted CVAT on the training box (data never leaves it). Reach it through an SSH tunnel:
#   ssh -i ~/.brev/brev.pem -p 22 -L 8080:localhost:8080 ubuntu@<instance IP>  ->  http://localhost:8080
# Creates the admin user from CVAT_ADMIN_PASSWORD (generated into ~/.cvat_admin if unset).
set -euo pipefail
CVAT_VERSION="${CVAT_VERSION:-v2.77.0}"
cd "$HOME"
[ -d cvat ] || git clone -q --depth 1 --branch "$CVAT_VERSION" https://github.com/cvat-ai/cvat.git
cd cvat
export CVAT_VERSION CVAT_HOST=localhost
docker compose up -d --quiet-pull

# The server applies migrations on first start; createsuperuser fails until they are done.
for _ in $(seq 1 120); do
  pending=$(docker exec cvat_server bash -c 'python3 ~/manage.py showmigrations 2>/dev/null | grep -c "\[ \]"' || true)
  [ "$pending" = "0" ] && break
  sleep 5
done

if [ ! -f "$HOME/.cvat_admin" ]; then
  umask 077
  echo "${CVAT_ADMIN_PASSWORD:-$(openssl rand -base64 18 | tr -d '/+=')}" > "$HOME/.cvat_admin"
fi
out=$(docker exec -e DJANGO_SUPERUSER_PASSWORD="$(cat "$HOME/.cvat_admin")" cvat_server \
  bash -c 'python3 ~/manage.py createsuperuser --noinput --username admin --email admin@localhost' 2>&1) \
  || { echo "$out" | grep -q "already taken" || { echo "$out" | tail -3; exit 1; }; }
curl -s -o /dev/null -w "CVAT $CVAT_VERSION http %{http_code}; admin password in ~/.cvat_admin\n" \
  http://localhost:8080/api/server/about
