import { useEffect, useRef } from "react";

import { timecode } from "../format";
import type { UiViolation } from "../types";
import { Icon } from "./Icon";

interface LightboxProps {
  violation: UiViolation;
  frameIndex: number;
  onChange: (frameIndex: number) => void;
  onClose: () => void;
}

export function Lightbox({ violation, frameIndex, onChange, onClose }: LightboxProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const frames = violation.evidence_frames;
  const frame = frames[frameIndex];

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" && frameIndex < frames.length - 1) onChange(frameIndex + 1);
      if (e.key === "ArrowLeft" && frameIndex > 0) onChange(frameIndex - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [frameIndex, frames.length, onChange]);

  return (
    <dialog
      ref={dialog}
      className="lightbox"
      aria-label={`Кадр ${timecode(frame.timestamp_sec)}`}
      onClose={onClose}
      onClick={(e) => e.target === dialog.current && dialog.current.close()}
    >
      <figure>
        <img src={frame.url} alt={`Кадр-доказательство на ${timecode(frame.timestamp_sec)}`} />
        <figcaption>
          <span className="lightbox-time">{timecode(frame.timestamp_sec)}</span>
          <span>{violation.type}</span>
          <span className="muted">
            Кадр {frameIndex + 1} из {frames.length}
          </span>
        </figcaption>
      </figure>
      <div className="lightbox-nav">
        <button type="button" className="button-quiet" disabled={frameIndex === 0}
          onClick={() => onChange(frameIndex - 1)}>
          <Icon name="prev" />
          Предыдущий
        </button>
        <button type="button" className="button-quiet" disabled={frameIndex === frames.length - 1}
          onClick={() => onChange(frameIndex + 1)}>
          Следующий
          <Icon name="next" />
        </button>
        <button type="button" className="button-primary" onClick={() => dialog.current?.close()}>
          Закрыть
        </button>
      </div>
    </dialog>
  );
}
