# Jury API: how to call the service

Base URL: given to the jury together with the API key (not published here). Below it is written as
`$BASE`, e.g. `export BASE=https://<host>`.

All jury endpoints are under `/api/v1/` and need the header `X-API-Key: <key>`. The key is handed
over separately (never in Git, chat or slides). A missing or wrong key gives
`401 {"detail":"Unauthorized"}`.

## 1. Submit a video

`POST /api/v1/analyze`, `multipart/form-data`, field **`file`** = a `.mov` video.

```bash
curl -s -X POST $BASE/api/v1/analyze \
     -H "X-API-Key: $KEY" -F "file=@video_017.mov"
# {"job_id":"5d1fb9a92299b56c"}
```

## 2. Poll for the result

`GET /api/v1/jobs/{job_id}`, same header. Poll every few seconds until `status` is `done` or `failed`.

```bash
curl -s $BASE/api/v1/jobs/5d1fb9a92299b56c -H "X-API-Key: $KEY"
```

| `status` | Meaning |
|---|---|
| `processing` | queued or being analysed |
| `done` | finished; `verdict` and `violations` are present |
| `failed` | not processed (e.g. `"error":"timeout"`); never reported as "no violation" |

Finished result (exact shape: [`schemas/job_response.schema.json`](../schemas/job_response.schema.json)):

```json
{
  "job_id": "5d1fb9a92299b56c",
  "status": "done",
  "verdict": "violation",
  "violations": [
    {
      "type": "Ранее принятые наличные вне устройства хранения",
      "timecode_sec": 56.2,
      "description": "К кассе подходит следующий клиент, а на столе остаются наличные предыдущего клиента. Правило: <документ>, п. <пункт>.",
      "evidence_frames": [
        {"timestamp_sec": 55.6, "image_base64": "/9j/4AAQ..."},
        {"timestamp_sec": 56.2, "image_base64": "/9j/4AAQ..."},
        {"timestamp_sec": 56.8, "image_base64": "/9j/4AAQ..."}
      ]
    }
  ]
}
```

- `verdict`: `violation` or `no_violation`. `violations` is `[]` exactly when `no_violation`.
- `timecode_sec`: seconds from the start of the video, one decimal.
- `evidence_frames`: 1–3 JPEGs, base64 **without** a `data:` prefix.
- `description`: what is visible, then the legal reference from
  [`config/rules_legal.yaml`](../config/rules_legal.yaml) when the catalogue has one for that rule.

## 3. Errors on upload

| Code | Reason |
|---|---|
| 400 | no file, not multipart, empty file |
| 401 | missing or wrong `X-API-Key` |
| 413 | file larger than 300 MB |
| 415 | not `.mov` / not QuickTime / resolution or fps out of range |
| 422 | unreadable video or duration out of range |
| 503 | queue or disk full, with `Retry-After` (seconds) |
| 404 | unknown `job_id` (on polling) |

Bodies are `{"detail": "...", "code": "..."}`.

## 4. Health and timing

- `GET /health` (no key): `{"status":"ok","gpu":true,"pipeline":"real","queue_length":0,"running":0,"workers":1}`.
  `pipeline` must be `real` (`dummy` means the demo analyzer).
- Each job has a budget of 280 s **counted from the upload**, queue wait included. Jobs run one
  at a time on the GPU; jury (API) jobs always run before website jobs.
- Measured on the deployment GPU: a 30 s clip in about 12 s end to end.

## 5. Minimal Python client

```python
import os, time, requests

BASE = os.environ["BASE"]
H = {"X-API-Key": os.environ["KEY"]}

with open("video_017.mov", "rb") as f:
    job = requests.post(f"{BASE}/api/v1/analyze", headers=H, files={"file": f}, timeout=300).json()["job_id"]
while True:
    r = requests.get(f"{BASE}/api/v1/jobs/{job}", headers=H, timeout=30).json()
    if r["status"] in ("done", "failed"):
        break
    time.sleep(3)
print(r["status"], r.get("verdict"), [(v["type"], v["timecode_sec"]) for v in r.get("violations", [])])
```

Or the repo's tool, which also measures the time per video:
`python scripts/load_test.py --url $BASE --key "$KEY" -n 1 video_017.mov`.

## Deployment

Single container (`docker/Dockerfile`, `PIPELINE=real`) on a Brev GPU instance (RTX A4000), bound
to `127.0.0.1:8000` on that machine. Public HTTPS comes from **Tailscale Funnel**
(`tailscale funnel --bg 8000`): no inbound port is open, and TLS ends on the instance itself, so no
third party sees the videos in transit. The web UI is the same host at `/`.
