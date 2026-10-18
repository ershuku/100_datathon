"""Submit N videos concurrently through the PUBLIC API and report time-to-done per job.

Simulates the jury: everything goes through /api/v1 with X-API-Key, and the clock starts before
the upload. Standard library only, so it also runs inside the offline container.

    python scripts/load_test.py --url https://host --key KEY -n 5 video1.mov [video2.mov ...]
    API_KEY=... python scripts/load_test.py -n 5 data/sample.mov

Exit code 1 if any job failed, never finished, or took longer than --limit seconds.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

JURY_LIMIT_SEC = 300.0


@dataclass
class Outcome:
    index: int
    file: str
    job_id: str | None = None
    upload_sec: float = 0.0
    total_sec: float = 0.0
    status: str = "not_submitted"
    verdict: str | None = None
    violations: int = 0
    error: str | None = None
    body: dict | None = None


def _multipart(path: Path) -> tuple[bytes, str]:
    boundary = f"----loadtest{uuid.uuid4().hex}"
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            "Content-Type: video/quicktime\r\n\r\n").encode()  # fmt: skip
    return head + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode(), boundary


def _request(url: str, key: str, data: bytes | None = None, content_type: str | None = None,
             timeout: float = 120.0) -> dict:  # fmt: skip
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    req.add_header("X-API-Key", key)
    if content_type:
        req.add_header("Content-Type", content_type)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL is the operator's
        return json.loads(resp.read())


def run_one(index: int, path: Path, base: str, key: str, poll: float, limit: float) -> Outcome:
    out = Outcome(index=index, file=path.name)
    body, boundary = _multipart(path)
    t0 = time.monotonic()
    try:
        out.job_id = _request(f"{base}/api/v1/analyze", key, body, f"multipart/form-data; boundary={boundary}")["job_id"]
        out.upload_sec = time.monotonic() - t0
        out.status = "processing"
        while time.monotonic() - t0 < limit + 60:  # keep polling a bit past the limit to measure overrun
            job = _request(f"{base}/api/v1/jobs/{out.job_id}", key, timeout=30)
            if job["status"] in ("done", "failed"):
                out.body = job
                out.status = job["status"]
                out.verdict = job.get("verdict")
                out.violations = len(job.get("violations", []))
                out.error = job.get("error")
                break
            time.sleep(poll)
        else:
            out.status = "no_result"
    except urllib.error.HTTPError as exc:
        out.status, out.error = "http_error", f"{exc.code} {exc.read()[:200].decode(errors='replace')}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        out.status, out.error = "network_error", str(exc)[:200]
    out.total_sec = time.monotonic() - t0
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("videos", nargs="+", type=Path, help="files are reused round-robin when n > count")
    parser.add_argument("--url", default=os.environ.get("BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--key", default=os.environ.get("API_KEY"))
    parser.add_argument("-n", type=int, default=5, help="number of concurrent submissions")
    parser.add_argument("--poll", type=float, default=2.0)
    parser.add_argument("--limit", type=float, default=JURY_LIMIT_SEC)
    parser.add_argument("--save-json", type=Path, help="write the final job responses to this file")
    args = parser.parse_args()
    if not args.key:
        parser.error("pass --key or set API_KEY")
    missing = [str(p) for p in args.videos if not p.is_file()]
    if missing:
        parser.error(f"not found: {', '.join(missing)}")

    base = args.url.rstrip("/")
    files = [args.videos[i % len(args.videos)] for i in range(args.n)]
    print(f"Submitting {args.n} job(s) concurrently to {base} (limit {args.limit:.0f} s)\n")
    with ThreadPoolExecutor(max_workers=args.n) as pool:
        outcomes = list(pool.map(lambda a: run_one(*a, base, args.key, args.poll, args.limit), enumerate(files)))

    print(f"{'#':>2}  {'file':<24} {'job_id':<17} {'upload':>7} {'total':>7}  {'status':<13} result")
    for o in outcomes:
        over = " OVER LIMIT" if o.total_sec > args.limit else ""
        result = f"{o.verdict} ({o.violations})" if o.verdict else (o.error or "")
        print(f"{o.index:>2}  {o.file[:24]:<24} {o.job_id or '-':<17} {o.upload_sec:>6.1f}s {o.total_sec:>6.1f}s"
              f"  {o.status:<13} {result}{over}")  # fmt: skip
    if args.save_json:
        args.save_json.write_text(json.dumps([o.body for o in outcomes], ensure_ascii=False), encoding="utf-8")
    totals = [o.total_sec for o in outcomes]
    bad = [o for o in outcomes if o.status != "done" or o.total_sec > args.limit]
    print(f"\nmax {max(totals):.1f} s, median {statistics.median(totals):.1f} s; "
          f"{len(outcomes) - len(bad)}/{len(outcomes)} done within {args.limit:.0f} s")  # fmt: skip
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
