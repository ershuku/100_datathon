import { useRef, type CSSProperties, type PointerEvent } from "react";

import { clock, timecode } from "../format";
import { useStripThumbs } from "../hooks/useStripThumbs";
import type { UiViolation } from "../types";
import { MarkerLoop } from "./MarkerLoop";

interface ContactStripProps {
  duration: number;
  previewUrl: string | null;
  violations: UiViolation[];
  selected: number | null;
  time: number;
  cells: number;
  onSelect: (index: number) => void;
  /** Called continuously while the reviewer drags the playhead; the video stays paused. */
  onScrub: (sec: number) => void;
}

const LOOP_STAGGER_MS = 160;

/**
 * The whole recording as one strip of stills, doubling as the scrubber: press anywhere and drag to move
 * the video. Flagged moments are circled on the cell they fall in.
 */
export function ContactStrip(props: ContactStripProps) {
  const { duration, previewUrl, violations, selected, time, cells, onSelect, onScrub } = props;
  const thumbs = useStripThumbs(previewUrl, duration, cells);
  const track = useRef<HTMLDivElement>(null);
  const pending = useRef<number | null>(null);
  const frame = useRef(0);
  const slice = duration / cells;
  const pct = (sec: number) => `${Math.min(1, Math.max(0, sec / duration)) * 100}%`;
  // A loop circles the whole cell its moment falls in, so it never straddles two stills.
  const cellCenter = (sec: number) => {
    const cell = Math.min(cells - 1, Math.max(0, Math.floor(sec / slice)));
    return `${((cell + 0.5) / cells) * 100}%`;
  };

  // One seek per animation frame however fast the pointer moves.
  const scrubTo = (clientX: number) => {
    const rect = track.current?.getBoundingClientRect();
    if (!rect) return;
    pending.current = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width)) * duration;
    if (frame.current) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = 0;
      if (pending.current !== null) onScrub(pending.current);
    });
  };
  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (!previewUrl || e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    e.currentTarget.dataset.scrubbing = "true";
    scrubTo(e.clientX);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (e.currentTarget.dataset.scrubbing === "true") scrubTo(e.clientX);
  };
  const endScrub = (e: PointerEvent<HTMLDivElement>) => {
    delete e.currentTarget.dataset.scrubbing;
  };

  return (
    <div className={`strip${previewUrl ? " is-scrubbable" : ""}`} style={{ "--cells": cells } as CSSProperties}>
      <div ref={track} className="strip-track" role="slider" tabIndex={previewUrl ? 0 : -1}
        aria-label="Позиция в видео: перетащите или используйте стрелки"
        aria-valuemin={0} aria-valuemax={Math.round(duration)} aria-valuenow={Math.round(time)}
        aria-valuetext={timecode(time)} aria-disabled={!previewUrl}
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={endScrub} onPointerCancel={endScrub}>
        <ol className="strip-cells" aria-hidden="true">
          {thumbs.map((src, i) => (
            <li key={i} className="strip-cell">
              {src ? <img src={src} alt="" draggable={false} /> : <span className="strip-blank" />}
              <span className="strip-time">{clock(i * slice)}</span>
            </li>
          ))}
        </ol>
        {previewUrl && (
          <span className="strip-head" style={{ left: pct(time) }} aria-hidden="true">
            <span className="strip-grip" />
          </span>
        )}
      </div>
      <div className="strip-marks">
        {violations.map((v, i) => (
          <button key={`${v.timecode_sec}-${i}`} type="button"
            className={`strip-mark${selected === i ? " is-selected" : ""}`}
            style={{ left: cellCenter(v.timecode_sec) }}
            onClick={() => onSelect(i)}
            aria-label={`Нарушение ${i + 1}: ${v.type}, ${timecode(v.timecode_sec)}`}
            aria-pressed={selected === i}>
            <MarkerLoop variant={i} selected={selected === i} delayMs={i * LOOP_STAGGER_MS} />
            <span className="strip-mark-num">{i + 1}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
