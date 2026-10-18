#!/bin/sh
# Runs as root on GPU pod platforms (RunPod, Vast.ai) that mount a root-owned volume, or as the
# unprivileged "app" user under docker compose. As root it prepares DATA_DIR and drops privileges.
set -eu

DATA_DIR="${DATA_DIR:-/data}"
export TMPDIR="${TMPDIR:-$DATA_DIR/tmp}"  # upload spooling goes to disk, not the container layer

if [ "$(id -u)" = "0" ]; then
  mkdir -p "$DATA_DIR" "$TMPDIR"
  chown -R app:app "$DATA_DIR"
  exec setpriv --reuid=app --regid=app --init-groups "$@"
fi

mkdir -p "$TMPDIR"
exec "$@"
