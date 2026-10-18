"""RF-DETR detector over a video -> tracker-format frames (same format as training/infer_video.py,
which ships standalone to the tracker team; keep the two in sync).

Frames are decoded with PyAV at native resolution; frame_index is the source index and pts_sec
the decoder timestamp. Boxes come back from rfdetr already in source-frame pixels.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import av
import numpy as np

FAMILY = {"safe_open": "safe", "safe_closed": "safe", "laptop_open": "laptop", "laptop_closed": "laptop",
          "door_open": "door", "door_closed": "door", "counter_machine": "counter", "uv_detector": "uv"}


def one_per_family(dets: list[dict]) -> list[dict]:
    """Fixed furniture exists once per room: keep the best box per family per frame."""
    best: dict[str, dict] = {}
    out = []
    for d in dets:
        fam = FAMILY.get(d["label"])
        if fam is None:
            out.append(d)
        elif fam not in best or d["score"] > best[fam]["score"]:
            best[fam] = d
    return out + list(best.values())


class Detector:
    def __init__(self, weights: str, threshold: float = 0.35, fps: float = 5.0) -> None:
        from rfdetr import RFDETR  # heavy import, only in the analyzer process

        self.model = RFDETR.from_checkpoint(weights)
        self.threshold = threshold
        self.fps = fps
        self.model.predict(np.zeros((848, 464, 3), np.uint8), threshold=threshold)  # warm-up

    def run(self, path: str | Path, on_progress: Callable[[float], None] | None = None) -> dict:
        frames, infer_s = [], 0.0
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            duration = float(stream.duration * stream.time_base) if stream.duration else None
            tb = float(stream.time_base)
            next_t, last_end = 0.0, 0.0
            for index, frame in enumerate(container.decode(stream)):
                pts = float(frame.pts * tb)
                dur = float(frame.duration * tb) if frame.duration else 1.0 / float(stream.average_rate or 30)
                last_end = pts + dur
                if pts + 1e-6 < next_t:
                    continue
                next_t = (np.floor(pts * self.fps + 1e-6) + 1) / self.fps
                rgb = frame.to_ndarray(format="rgb24")
                t0 = time.perf_counter()
                det = self.model.predict(rgb, threshold=self.threshold)
                infer_s += time.perf_counter() - t0
                names = det.data.get("class_name", [str(c) for c in det.class_id])
                dets = one_per_family([
                    {"label": str(c), "score": round(float(s), 4), "box_xyxy": [round(float(v), 1) for v in b]}
                    for c, s, b in zip(names, det.confidence, det.xyxy)])
                frames.append({"frame_index": index, "pts_sec": round(pts, 4),
                               "width": rgb.shape[1], "height": rgb.shape[0], "detections": dets})
                if on_progress and duration:
                    on_progress(min(1.0, pts / duration))
        return {"source_end_pts": round(last_end, 4), "sampling": {"target_fps": self.fps},
                "frames": frames, "timing": {"model_sec": round(infer_s, 2)}}
