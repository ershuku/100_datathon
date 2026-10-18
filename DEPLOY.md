# Deployment

One container serves the UI, the jury API and the analyzer. It needs one NVIDIA GPU and has no
runtime internet dependency: model weights are copied into the image at build time and
`HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` are set, so a model that loads in the container has
provably loaded without any hub access.

| | **A. GPU pod (RunPod)** (recommended) | B. GPU VM + Caddy | C. Own machine + Cloudflare Tunnel |
|---|---|---|---|
| Use when | the model needs more GPU than a laptop has | you want a "bank-like" server | the model fits the local GPU |
| Runs | the image directly (no compose) | `docker compose --profile caddy` | `docker compose --profile tunnel` |
| HTTPS | built-in proxy URL | Let's Encrypt via Caddy | Cloudflare edge |
| Upload limit | Cloudflare-fronted proxy, ~100 MB | 310 MB | 100 MB (Free/Pro) |
| `TRUST_PROXY` | `none` | `xff` | `cloudflare` |
| Cost | ≈ $0.34–0.69/h (RTX 4090 24 GB), ≈ $0.44/h (A40 48 GB), Oct 2026 | VM price | free |

Jury files are ~29 MB, so every option's upload limit is fine.

## 0. Build the image (all options)

Prerequisites on the build machine: Docker (Desktop on Windows/macOS). A GPU is not needed to build.

1. Model weights in `models/` (not in Git). The analyzer reads them from `/models`
   (`HF_HOME=/models/hf`, `TORCH_HOME=/models/torch`).
2. Analyzer Python deps pinned in `pyproject.toml` under the `ml` extra, then `uv lock`. Example
   for CUDA torch: `uv add --optional ml "torch==<ver>" --index pytorch-cu126=https://download.pytorch.org/whl/cu126`.
3. Build and check the plumbing offline:
   ```bash
   docker build -f docker/Dockerfile -t cashier-checker:0.1.0 .
   PIPELINE=dummy GPU=0 scripts/offline_check.sh     # runs with --network none, prints OFFLINE CHECK PASSED
   ```
   On a machine with a big enough GPU, also run `scripts/offline_check.sh` (PIPELINE=real, GPU on):
   it asserts `/health` shows `"pipeline":"real"`, `"gpu":true` and that no result is a dummy one.

App settings come from environment variables (see `.env.example`). Mandatory:
```
API_KEY=<python -c "import secrets;print(secrets.token_urlsafe(32))">   # the service refuses weak keys
PIPELINE=real
```

## A. GPU pod (RunPod)

Pods run one container image and give it a public HTTPS URL; Docker and compose are not
available inside, which is fine because the image is self-contained.

1. Push the image to a registry (private is fine):
   ```bash
   docker tag cashier-checker:0.1.0 ghcr.io/<org>/cashier-checker:0.1.0
   docker push ghcr.io/<org>/cashier-checker:0.1.0
   ```
   For a private image add the registry credentials in RunPod → Settings → Container Registry Auth.
2. Create a template / pod:
   - **Image**: `ghcr.io/<org>/cashier-checker:0.1.0`; leave the start command empty (the image's
     entrypoint runs uvicorn).
   - **GPU**: by the model's VRAM need (24 GB RTX 4090 / L4-class covers most 7B vision models in
     fp16; 48 GB A40/L40S for larger). Use **on-demand, Secure Cloud**, not spot/interruptible.
   - **Container disk**: image size + 10 GB. **Volume**: 10 GB at `/workspace`.
   - **Expose HTTP ports**: `8000`.
   - **Environment**: `API_KEY=…`, `PIPELINE=real`, `DATA_DIR=/workspace/data`, `TRUST_PROXY=none`.
3. The pod starts as root; the entrypoint prepares `DATA_DIR` and drops to the unprivileged `app`
   user. Public URL: `https://<POD_ID>-8000.proxy.runpod.net`.
   ```bash
   curl -s https://<POD_ID>-8000.proxy.runpod.net/health
   # {"status":"ok","gpu":true,"pipeline":"real",...}
   ```
4. Run the jury rehearsal from your laptop (section "Before handing over").
5. Keep the pod **running** for the whole jury window. Stopping keeps the volume; terminating
   deletes it (job results). The URL stays the same while the pod exists.

Notes:
- The proxy closes requests that are silent for ~100 s. The API is asynchronous (POST returns
  right after the upload, then short polls), so this does not affect the jury flow.
- Behind the proxy all UI visitors share one rate-limit bucket (`TRUST_PROXY=none`). The jury
  API is not rate-limited and runs before UI jobs.
- Vast.ai works the same way with the image; it exposes `IP:port` without TLS, so add a TLS
  front (e.g. option C's tunnel) there.

## B. GPU VM + Caddy

1. Rent a VM with an NVIDIA GPU (Ubuntu 22.04/24.04). Install the driver, Docker and the NVIDIA
   Container Toolkit; check `docker run --rm --gpus all nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04 nvidia-smi`.
2. DNS A record (e.g. `check.example.kz`) → VM IP. Open ports 80/443 only (uvicorn binds to
   `127.0.0.1:8000`).
3. Copy the repo with `models/` to the VM. `.env` with `TRUST_PROXY=xff`; `deploy.env` (from
   `deploy.env.example`) with `DOMAIN=check.example.kz`.
4. `docker compose --profile caddy up -d --build`, wait for "certificate obtained" in
   `docker compose logs -f caddy`, then `curl -s https://check.example.kz/health`.

`docker/Caddyfile`: HSTS, 310 MB body limit, long body-read timeout, and `X-Api-Key` removed from
the access log so the jury key is never written to disk.

## C. Own machine + Cloudflare Tunnel

Only if the model fits the local GPU (a 4 GB laptop GPU is not enough for vision-language models).

1. Cloudflare → Zero Trust → Networks → Tunnels → create; copy the token; public hostname
   `check.example.kz` → service `http://app:8000`.
2. `.env` with `TRUST_PROXY=cloudflare`; `deploy.env` with `TUNNEL_TOKEN=…` (the app container
   never sees the token).
3. `docker compose --profile tunnel up -d --build`.
4. Add a Cloudflare Cache Rule "bypass cache" for the hostname (frames and previews are
   confidential; the app already sends `Cache-Control: no-store`).
5. Keep the machine awake, on power and online for the whole jury window.

## Before handing over to the jury

- [ ] `/health` on the public URL shows `"gpu": true` and `"pipeline": "real"`
- [ ] Offline check passed on the final image (step 0)
- [ ] Rehearsal against the **public URL** with videos like the jury's:
      `python scripts/load_test.py --url https://<public-host> --key $KEY -n 5 a.mov b.mov`
      All 5 must finish well under 300 s. One GPU slot runs jobs one after another, so with 5 at
      once the per-video time must stay under ~50 s (server logs: `queue_wait_sec`, `processing_sec`).
- [ ] The jury key goes through a separate channel, not in the repo, chat or slides
- [ ] `TIMEOUT_FALLBACK` and `REVIEW_POLICY` decided by the team (`TODO(team)`)
- [ ] `config/rules_legal.yaml` filled in and checked by people
- [ ] After the event: delete test videos and results (pod: terminate; compose: `docker compose down -v`)

## Operations

- Logs (JSON lines with `job_id`, `stage`, durations; never video content): RunPod → pod logs;
  compose → `docker compose logs -f app` (rotated, 5 × 20 MB).
- Jury (API) jobs always run before UI jobs; the UI may hold at most `UI_MAX_ACTIVE` jobs.
- Queued jobs whose budget is gone are answered `failed / timeout` within ~5 s instead of waiting.
- Video files are deleted `FILE_TTL_SEC` (default 1 h) after a job ends; JSON results stay in the
  SQLite DB under `DATA_DIR`.
- A restart marks running/queued jobs `failed` ("interrupted by service restart").
- `WORKER_CONCURRENCY` > 1 loads one model copy per slot; raise only if VRAM allows.
- `VIDEO_ENCODER=h264_nvenc` moves preview encoding to the GPU if the ffmpeg build supports it
  (`ffmpeg -hide_banner -encoders | grep nvenc` inside the container).

## Licenses

- Base image `nvidia/cuda` (with cuDNN): NVIDIA Deep Learning Container License / CUDA EULA,
  which allow redistribution of the runtime libraries inside containers.
- ffmpeg from Ubuntu includes GPL components (libx264/libx265). GPL permits commercial use; for a
  non-GPL build swap to `libopenh264` (BSD).
- Python and JS dependencies are pinned in `uv.lock` / `frontend/package-lock.json`, all permissive
  (MIT/BSD/Apache/HPND; fonts OFL). The ML team checks model weights' licenses separately.

## Planned: split deployment (Oracle Free + GPU pod) — TODO

Website and API on a free Oracle Cloud ARM VM, the model on a GPU pod that the ML team starts.
The single-container options above stay as the fallback.

```
jury / browser ──HTTPS──> Oracle VM (Caddy + backend + UI, CPU only)
                              │  normalized video + shared secret
                              ▼
                     GPU pod (model server, HTTPS)
```

- [ ] **CPU-only arm64 backend image** for Oracle Ampere A1 (no CUDA, never loads the model):
      `python:3.11-slim` + ffmpeg, multi-arch build (`docker buildx --platform linux/arm64`).
- [ ] **Model server for the pod**: a small HTTP service wrapping `analyze_video` from
      `src/pipeline/analyzer.py`; one endpoint that takes the normalized video and returns events
      (type_code, timecode, description, evidence timestamps, rule_id, needs_review) plus progress;
      protected by a shared secret header; same offline env (`HF_HUB_OFFLINE=1`).
- [ ] **Remote adapter in the backend**: `PIPELINE=remote` with `MODEL_URL` and `MODEL_TOKEN`; sends
      the normalized video, maps the reply to `AnalyzerOutput`. The 280 s deadline still applies;
      pod down / slow / error → job `failed`, never `no_violation`. `/health` reports whether the
      model server is reachable.
- [ ] **Oracle VM setup** in this file: create an Always Free A1 instance (retry another region on
      "out of capacity"); open 80/443 in **both** the VCN security list and the instance's
      `iptables`; Docker + compose; Caddy with a free hostname (`<ip>.sslip.io` or DuckDNS) for
      Let's Encrypt; `TRUST_PROXY=xff`. Keep it busy before judging — idle Always Free instances
      can be reclaimed.
- [ ] **Pod runbook** for the ML team: start the model server image, expose its port, set the
      secret, give the URL to the backend; do not train on the same GPU during judging.
- [ ] **Reachability check** from Oracle to the pod (script) and a load test of the whole chain
      against the public URL (`scripts/load_test.py -n 5`).
- [ ] **Team decisions**: who owns the pod and its uptime window (ask the organizers when the jury
      sends test videos), GPU size by the model's VRAM, budget.

Other hosts considered: Vercel (serverless, ~4.5 MB request bodies — cannot take the videos),
Railway / Render paid / Fly.io (fine for the CPU backend, a few $ per month), Hugging Face Spaces
(free CPU, but sleeps and loses its disk on restart), Cloudflare Workers (no ffmpeg, no long-running
process). Oracle Always Free is the chosen free option; Railway is the paid fallback.
