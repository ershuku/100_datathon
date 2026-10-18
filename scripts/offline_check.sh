#!/usr/bin/env bash
# Proves the built image processes a video end to end with NO network at all (--network none).
#
#   scripts/offline_check.sh                    # synthetic test video generated inside the container
#   scripts/offline_check.sh path/to/video.mov  # or a local file of your own (copied in, not uploaded)
#
# Env: IMAGE (default cashier-checker:0.1.0), PIPELINE (default real), GPU=0 to run without --gpus.
# With PIPELINE=real it also asserts /health reports pipeline "real" and a visible GPU, and that no
# result carries the dummy marker.
set -euo pipefail

IMAGE="${IMAGE:-cashier-checker:0.1.0}"
PIPELINE="${PIPELINE:-real}"
NAME="cashier-offline-check-$$"
KEY="offline-$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
GPU_ARGS=()
[ "${GPU:-1}" = "1" ] && GPU_ARGS=(--gpus all)

fail() { echo "FAIL: $*"; docker logs --tail 50 "$NAME" 2>&1 | sed 's/^/   | /' || true; exit 1; }
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "== starting $IMAGE with --network none (PIPELINE=$PIPELINE)"
docker run -d --name "$NAME" --network none ${GPU_ARGS[@]+"${GPU_ARGS[@]}"} \
  -e API_KEY="$KEY" -e PIPELINE="$PIPELINE" "$IMAGE" >/dev/null

echo "== confirming the container really has no network"
if docker exec "$NAME" python -c "import socket; socket.create_connection(('1.1.1.1', 443), 3)" 2>/dev/null; then
  fail "container reached the internet"
fi
echo "   ok: outbound connections fail"

echo "== waiting for /health (model loading can take a while)"
health=""
for _ in $(seq 1 90); do
  if health=$(docker exec "$NAME" python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read().decode())" 2>/dev/null); then
    break
  fi
  health=""
  sleep 2
done
[ -n "$health" ] || fail "service never became healthy"
echo "   $health"

if [ "$PIPELINE" = "real" ]; then
  echo "$health" | grep -q '"pipeline":"real"' || fail "/health does not report pipeline real"
  if [ "${GPU:-1}" = "1" ]; then
    echo "$health" | grep -q '"gpu":true' || fail "/health reports no GPU"
  fi
fi

if [ $# -ge 1 ]; then
  echo "== copying $1 into the container"
  docker cp "$1" "$NAME:/tmp/sample.mov"
else
  echo "== generating a synthetic 30 s HEVC .mov inside the container"
  docker exec "$NAME" ffmpeg -v error -y -f lavfi -i testsrc2=size=1920x1080:rate=30:duration=30 \
    -c:v libx265 -tag:v hvc1 -x265-params log-level=error -f mov /tmp/sample.mov
fi

echo "== submitting through the public API inside the container"
docker exec -e API_KEY="$KEY" "$NAME" python scripts/load_test.py -n 1 --save-json /tmp/result.json /tmp/sample.mov \
  || fail "job did not finish successfully within the limit"

if [ "$PIPELINE" = "real" ] && docker exec "$NAME" grep -q "ТЕСТОВЫЙ РЕЖИМ" /tmp/result.json; then
  fail "result contains the dummy marker although PIPELINE=real"
fi
echo "OFFLINE CHECK PASSED"
