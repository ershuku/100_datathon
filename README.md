# datathon — cashier video checker

Local AI service that flags possible cash-handling violations in cashier videos
(Datathon 26). This public copy contains the code, configuration and documentation; the
organisers' dataset, labels and case materials are not included.

## Документация

- [PRODUCT_FLOW.md](PRODUCT_FLOW.md) — полный путь через сайт и API.
- [DEPLOY.md](DEPLOY.md) — запуск в Docker, публичный HTTPS (GPU pod / Caddy / Cloudflare Tunnel), проверка перед сдачей.
- [training/README.md](training/README.md) — обучение детектора (RF-DETR) на Brev: кадры, предразметка, CVAT, обучение.
- [docs/JURY_API.md](docs/JURY_API.md) — запросы к API, ключ и формат ответа.
- [STATE_MACHINE.md](STATE_MACHINE.md) — правила нарушений (конечный автомат), [Aibar.md](Aibar.md) — исходная спецификация правил.

---

# Service: cashier video checker

Fully local service: upload a `.mov` of a cashier, get possible cash-handling violations with
timecodes, 1–3 evidence frames each and the legal reference. A web UI for people, a keyed API for
the jury, one container, one GPU, no internet needed after build.

```
browser ──/ui/*──┐                                   ┌─ normalize (ffmpeg: rotation, H.264 ≤1280 px)
                 ├─ FastAPI ─ SQLite jobs ─ worker ──┼─ analyzer child process (dummy | real ML)
jury ──/api/v1/*─┘   (X-API-Key)                     └─ evidence frames (exact timestamps, JPEG)
```

## Run locally (no Docker)

Needs Python 3.11 via [uv](https://docs.astral.sh/uv/), ffmpeg/ffprobe, Node 22 for the UI.

```bash
cp .env.example .env              # set API_KEY (>= 16 chars); FFMPEG_BIN/FFPROBE_BIN if not on PATH
uv sync
cd frontend && npm ci && npm run build && cd ..   # UI is then served by the backend at /
uv run uvicorn app.main:app --app-dir src --port 8000
```

Open http://127.0.0.1:8000. For UI development run `npm run dev` in `frontend/` (port 5173,
proxies `/ui` and `/health` to :8000).

A synthetic test video (never use dataset footage in examples or issues):

```bash
uv run python scripts/make_test_video.py data/sample.mov --duration 20 --hevc --rotate 90
```

## Jury API

All `/api/v1/*` routes need `X-API-Key` (one of the comma-separated keys in `API_KEY`); wrong or
missing key → `401 {"detail":"Unauthorized"}`.

```bash
curl -X POST https://<host>/api/v1/analyze -H "X-API-Key: <key>" -F "file=@video.mov"
# {"job_id":"5d1fb9a92299b56c"}

curl https://<host>/api/v1/jobs/<job_id> -H "X-API-Key: <key>"
# {"job_id":"5d1fb9a92299b56c","status":"processing"}
# {"job_id":"…","status":"done","verdict":"violation","violations":[{"type":"…","timecode_sec":44.2,
#   "description":"… Правило: <документ>, п. <пункт>.","evidence_frames":[{"timestamp_sec":44.2,"image_base64":"/9j/…"}]}]}
# {"job_id":"…","status":"failed","error":"timeout"}
```

- Exact shape: [`schemas/job_response.schema.json`](schemas/job_response.schema.json), enforced by
  `tests/test_contract.py`. No extra fields; `violations` is `[]` iff `verdict` is `no_violation`;
  timecodes have one decimal; base64 has no `data:` prefix.
- Upload errors are 4xx with `{"detail","code"}`: 400 (no file / not multipart / empty),
  413 (> 300 MB), 415 (not `.mov` / not QuickTime / resolution or fps out of range), 422
  (unreadable, duration), 503 (queue full or disk full, `Retry-After`). Unknown job → 404.
- `GET /health` (no key): `status`, `gpu`, `pipeline`, `queue_length`, `running`, `workers`.

The UI uses separate same-origin routes `/ui/analyze`, `/ui/jobs/{id}` (+ preview, frames,
`result.json` download) with no key and a per-IP rate limit. The jury key never reaches the browser.
Jury jobs always run before UI jobs; the UI may hold at most `UI_MAX_ACTIVE` jobs and never the
last `API_RESERVED_SLOTS` queue slots.

## Time budget

Each job has `JOB_TIMEOUT_SEC` (default 280 s) counted **from the start of the upload request**,
queue wait included. Jobs run one at a time per GPU slot. When the budget is gone the analyzer
process is killed and restarted, and `TIMEOUT_FALLBACK` decides the answer (`failed` by default;
`partial` returns events found so far, never an empty "no violation"). Measure with:

```bash
python scripts/load_test.py --url http://127.0.0.1:8000 --key <key> -n 5 a.mov b.mov
```

With 5 videos at once, the 5th waits for the first 4: keep per-video processing under ~50 s.

## Plugging in the ML analyzer (Aibar)

The interface is provisional and lives in one file: [`src/app/analysis/port.py`](src/app/analysis/port.py).

1. Implement `create_analyzer()` in [`src/pipeline/analyzer.py`](src/pipeline/analyzer.py). It runs
   **once** in a dedicated child process (load the model here, from `/models`), and returns an
   object with:
   ```python
   def analyze_video(self, video_path: str, ctx: JobContext, reporter: Reporter) -> AnalyzerOutput
   ```
   - `video_path`: normalized H.264 .mp4, rotation applied, long side ≤ 1280 px, starts at t=0.
     `ctx.source_path` is the untouched original if you need full resolution (same timeline,
     rotation not applied). Timecodes always refer to this timeline = seconds from video start.
   - `ctx.time_budget_sec`: you are killed after this; `ctx.work_dir`: scratch space.
   - `reporter.progress(percent, "текст этапа")` for the UI; `reporter.event(e)` optionally as soon
     as an event is found (used by `TIMEOUT_FALLBACK=partial`).
2. Return `AnalyzerOutput(events=(DetectedEvent(...), ...), debug={...})` where each event has
   `type_code` (key in `config/rules_legal.yaml`), `timecode_sec`, `description` (RU, what is
   visible and why it may be a violation, **no legal text**), 1–3 `EvidenceRef(timestamp_sec)` —
   or `EvidenceRef(timestamp_sec, image_path=...)` for a frame you already picked (inside
   `ctx.work_dir`) — optional `rule_id` and `needs_review`.
3. The backend does the rest: verdict (= any events), JPEG/base64, legal reference appended to the
   description, both JSON responses. Raising an exception → job `failed`, never `no_violation`.
4. Extra deps: add them pinned to the `ml` extra in `pyproject.toml` (`uv add --optional ml ...`),
   which locks them in `uv.lock` and installs them in the image. Weights: `models/`. Then `PIPELINE=real`.

Try it without the server: `DummyAnalyzer` in `src/app/analysis/dummy.py` is a complete example
(`DUMMY_SCENARIO=auto|none|violations|review|slow|crash`).

### Current real analyzer: detector + rule engine

`PIPELINE=real` runs [`src/pipeline/analyzer.py`](src/pipeline/analyzer.py): the RF-DETR detector
([`detector.py`](src/pipeline/detector.py), 5 frames/s, weights from `DETECTOR_WEIGHTS`, default
`/models/detector/checkpoint_best_total.pth`, i.e. `models/detector/` in the build context) and the
event-deadline state machine ([`rules.py`](src/pipeline/rules.py), design and limits in
[STATE_MACHINE.md](STATE_MACHINE.md)). Deps are pinned in the `ml` extra (torch/torchvision from the
CUDA 12.6 index). It loads fully offline. Tests: `tests/test_rules.py` (rules on synthetic scenes),
`tests/test_pipeline_analyzer.py` (analyzer → legal catalogue → public JSON, detector faked).
A separate hybrid analysis command (detector + tracker + local VLM, not included here)
can be added as a second factory and selected with `PIPELINE_FACTORY`; both use the same contract.

## Legal references

`config/rules_legal.yaml` contains the official Adilet sources checked on 18 October 2026,
clause references, and conditional mappings for the event codes. Rules are paraphrases, not
verbatim quotations. Each rule records `required_observations`, `limitations`, and the source
check date. Source checking does not establish that a rule applies to an individual video: Бага
must review applicability and Ершуак independently verify it. The analyzer must check the
required context before returning an event; catalogue lookup alone does not do this.
Ambiguous `ID`, `THIRD`, `SAFE`, and `DOOR` events require an explicit `rule_id`; a type code
alone attaches no citation. Unknown explicit rule IDs never fall back to a different rule.
Pending references are labelled as possible grounds requiring an applicability check.

The expanded catalogue covers 54 event codes and 49 rules: deposit/payout receipts, payout
counting exceptions, separate deposits, internal supervision, sorting and packaging, seals,
ATM cassettes, vault access, keys, collection handovers/crew/protection, cash-room equipment,
and information security. Every newly added code requires explicit rule selection.
`evidence_mode` distinguishes video with context from checks requiring additional records.
This is bounded coverage, not a complete code of Kazakhstan law and not a recognition model.

The UI shows the rule, applicability limits, and an official-source link next to the event's
timecode and evidence. The public API keeps the required schema and appends the clause,
limits, and URL to `description`. No video, frames, or observations are sent to Adilet.
The catalogue is local; inference never needs a live government API or website.

Cash operations/collection: https://adilet.zan.kz/rus/docs/V1900019680 (НБРК № 231).
Cash premises/security: https://adilet.zan.kz/rus/docs/V2000020075 (НБРК № 14).
Recheck the temporary wording of № 14, пункт 16, before 1 January 2027.
Information security: https://adilet.zan.kz/rus/docs/V2600038336 (АРРФР № 53), including
session timeout, account use, and paper/external-media protection. These categories need
context or records and are not provable from a short video alone.
Customer due diligence: https://adilet.zan.kz/rus/docs/Z090000191_ (статья 5 п. 1).
Bank secrecy: https://adilet.zan.kz/rus/docs/Z2600000258 (статья 69 пп. 1–4).
Both are contextual references: video alone cannot establish due-diligence failures, consent,
access rights, or unlawful disclosure. They require explicit selection and external records.
Fraud: https://adilet.zan.kz/rus/docs/K1400000226 (статья 190), context for human
review only; it is not automatically attached to video events.

`EXIT` (unlocked workstation) has no automatic default citation. Its explicit rule
`IS_SESSION_TIMEOUT` references АРРФР № 53 пункт 71(9): more than 30 minutes of inactivity
without either session termination or locking, requiring system records/extended observation.
A short departure does not satisfy this condition. Check the paragraph 72 exceptions
for integrated authentication and compensating cross-system functions before applying paragraph 71. № 231 пункт 22 concerns leaving before
customer service ends, not computer locking. Other narrower rules
(such as `CASH_LEAVE`, `CASH_BAG`, `CASH_ID_OUT`) may be selected by `rule_id` only when
the event and context actually satisfy them. TODO fields remain hidden from results.

## Team V-class compatibility

`config/rules_legal.yaml` is the maintained source for V1–V14 and V1b, candidate rules,
conditions, and limitations. The backend accepts either a team V-class or a canonical
`type_code`. V-classes always need an explicit approved `rule_id`; neither a class nor a
known rule proves that the context requirements hold. Unknown/unrelated rule selections
receive no citation. V12 remains observation-only, with no confirmed rule. Returning V12 or CASH_RETURN as a
violation is rejected (the job fails instead of fabricating a violation or a clean result);
the analyzer must retain such candidates internally for review.

Regenerate the generic guidance in `pipeline_law_projection.md` after catalogue edits:

```bash
.venv/bin/python scripts/render_law_projection.py
.venv/bin/python scripts/render_law_projection.py --check
```

Sections 3–4 of that document are an archived worksheet projection, preserved unchanged.
They are not runtime predictions, validated legal conclusions, or a lookup table for new videos.
The generator never reads the workbook or videos. It preserves archived sections as opaque bytes.

## Data handling

- Uploaded and derived videos are deleted `FILE_TTL_SEC` (default 1 h) after the job ends; only the
  JSON result (with evidence frames) stays in SQLite.
- Logs carry job ids, stages and durations, never frames or video content.
- No face recognition, no audio (audio streams are dropped at normalization).

## Tests

```bash
uv run pytest            # needs ffmpeg/ffprobe (FFMPEG_BIN/FFPROBE_BIN); all test videos are synthetic
```

Auth (401), upload validation, job lifecycle, schema contract, JPEG/base64 validity, TTL cleanup,
timeout and fallback, rate limiting, proxy-header trust, rotation/HEVC handling. On a small machine
run files one at a time (`uv run pytest tests/test_auth.py`).

## Decisions left to the team (`TODO(team)`)

| Setting | Options | Default |
|---|---|---|
| `TIMEOUT_FALLBACK` | `failed` / `partial` | `failed` |
| `REVIEW_POLICY` (events marked `needs_review`) | `report` as violation / `drop` | `report` |
| `config/rules_legal.yaml` | team review of applicability, especially context-dependent EXIT | official sources checked; team review pending |
