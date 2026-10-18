# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: the Datathon 26 jury and case evaluators (ForteBank case). They open the site, upload a test `.mov` of a bank cashier at work, wait for the analysis, and check the verdict and every reported event against its evidence frames. They are judging whether the service detects, locates, classifies and justifies events correctly on footage it has never seen. For them the demo is the product.

Secondary, non-human: the jury's automated checker, which calls the API (`POST /api/v1/analyze`, `GET /api/v1/jobs/{id}` with `X-API-Key`). The site and the API run the same pipeline and return the same result contract.

## Product Purpose

A fully local AI service that analyzes cashier video and flags possible procedural violations. For each video it returns one of two verdicts, `no_violation` or `violation`, and lists every detected event. Each event carries a type, a timecode, a description of the observed action and why it may be a violation, 1–3 original JPEG evidence frames, and its normative basis (a Kazakhstan document, plus the clause or section when one is available).

Success: on a new, permitted video, both the site and the API return a correct, schema-valid result with verifiable frames within the 5-minute end-to-end budget, and technical failures are reported as failures, never as `no_violation`.

## Positioning

All inference runs inside the team's own deployed service. No video, frame, or description of video content goes to a cloud AI, and processing needs no internet once the weights are installed. Each flag is tied to visible evidence and a checked normative source rather than to an opaque score. The output supports a human review. It does not establish guilt, intent, or a final legal fact.

## Operating Context

- Input: `.mov` cashier recordings, about 29 MB expected per the ТЗ. The server validates the container, the video stream, size, and duration; checking the extension alone is not enough. A corrupted file is a technical error.
- Flow: choose or drop the file → upload (transfer progress) → real job stages (queue → preparing video → action analysis → evidence frames) → verdict and events. No invented percentage progress.
- No accounts, history, export, or batch upload (not required per the FAQ). The UI uses a server-side access scheme. The jury API key never reaches the frontend.
- Deployed at a public URL for the jury. FastAPI serves the built React/Vite frontend from the same origin. In dev, Vite runs on :5173 and proxies to uvicorn on :8000.
- Source of requirements: the organisers' case document (not included). Target behaviour: `PRODUCT_FLOW.md`.

## Capabilities and Constraints

- Exactly two verdicts. No third "insufficient data" verdict unless the organizers clarify. When visibility is limited, avoid categorical legal conclusions.
- Required result content for each event: type, timecode, 1–3 frames, observed action + reasoning, normative basis with a link. Jumping to the moment in a video player is an optional convenience.
- Result copy: "Нарушение не обнаружено" (not a guarantee about unseen operations) / "Обнаружены признаки возможных нарушений". Standing note: the result is a hint for human review, not a final conclusion.
- Errors: a clear, specific message for each failure code (see `frontend/src/text.ts`). The user can retry; there are no endless automatic retries.
- No audio, no face recognition or identification.
- Temporary videos, frames, and results have a retention period and are deleted. Jury test videos are never used for training, published, or shared.
- A test mode (`PIPELINE=dummy`) exists and is shown in the UI as "Тестовый режим: результаты не настоящие". It must be off for the real submission.
- Event types and normative rules come from the verified catalogue (`config/rules_legal.yaml`, owned by Baga). The UI never invents types, sources, or clauses.

## Brand Commitments

- Own, neutral tool identity. Current working name: "Проверка кассовых операций". No ForteBank logo, colors, or other brand assets. ForteBank may be named only as the case context ("кейс ForteBank").
- Interface language: Russian only. All user-facing copy lives in `frontend/src/text.ts`.
- Voice: factual and careful. Describe only what is observed, use "possible"/"signs of" language for violations, and never assert guilt.

## Evidence on Hand

- `data/sample.mov` and `scripts/make_test_video.py`: local test footage only. Its content must not be sent to cloud agents.
- `open/open_labels.xlsx`: the team's labels. Local only.
- `config/rules_legal.yaml`: catalogue of normative rules.
- `schemas/job_response.schema.json`: the result contract.
- None of the following exist: testimonials, accuracy figures, or benchmark claims. Do not fabricate them. Quality metrics come only from Yershuak's local evaluation.

## Product Principles

1. Evidence before assertion: every flag is shown with its frames, timecode, and source, so an evaluator can verify it in seconds.
2. Honest state: real stages, real errors, and explicit test mode. A failure is never shown as a clean result.
3. Assist, don't adjudicate: the wording keeps the human reviewer as the decision-maker.
4. Local and private by construction: nothing about the video leaves the service.
5. One analyzer, one truth: the site and the API always agree.
