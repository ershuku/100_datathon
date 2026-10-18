"""On-disk layout of a job. Everything under data/jobs/<id>/ is deleted after FILE_TTL_SEC."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JobFiles:
    root: Path

    @property
    def upload(self) -> Path:
        return self.root / "upload.mov"

    @property
    def normalized(self) -> Path:
        return self.root / "normalized.mp4"

    @property
    def frames_dir(self) -> Path:
        return self.root / "frames"

    @property
    def work_dir(self) -> Path:
        return self.root / "work"

    def remove_upload(self) -> None:
        self.upload.unlink(missing_ok=True)

    def remove_all(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def job_files(jobs_dir: Path, job_id: str) -> JobFiles:
    return JobFiles(jobs_dir / job_id)
