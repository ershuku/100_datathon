from __future__ import annotations

import shutil
import subprocess
import time
from functools import lru_cache

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])

GPU_CHECK_TTL_SEC = 60


@lru_cache(maxsize=1)
def _gpu_visible_cached(_bucket: int) -> bool:
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return False
    try:
        proc = subprocess.run([exe, "-L"], capture_output=True, timeout=5, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0 and b"GPU" in proc.stdout


def gpu_visible() -> bool:
    return _gpu_visible_cached(int(time.time() // GPU_CHECK_TTL_SEC))


@router.get("/health")
async def health(request: Request) -> dict:
    state = request.app.state
    return {
        "status": "ok",
        "gpu": gpu_visible(),
        "pipeline": state.settings.pipeline.value,
        "queue_length": state.worker.queue_length,
        "running": state.worker.running,
        "workers": state.settings.worker_concurrency,
    }
