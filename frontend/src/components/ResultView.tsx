import { useCallback, useEffect, useMemo, useState } from "react";

import { clock } from "../format";
import { usePlayer } from "../hooks/usePlayer";
import { HUMAN_REVIEW_NOTE, pluralEvents } from "../text";
import type { UiJob } from "../types";
import { ContactStrip } from "./ContactStrip";
import { EventList } from "./EventList";
import { Icon } from "./Icon";
import { Lightbox } from "./Lightbox";
import { MarkerLoop } from "./MarkerLoop";
import { Transport } from "./Transport";
import { ViolationPanel } from "./ViolationPanel";

interface ResultViewProps {
  job: UiJob;
  fileName: string | null;
  onReset: () => void;
}

const NARROW_QUERY = "(max-width: 720px)";
const CELLS_WIDE = 12;
const CELLS_NARROW = 6;
const SECOND_STEP = 1;

function useStripCells(): number {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW_QUERY).matches);
  useEffect(() => {
    const mq = window.matchMedia(NARROW_QUERY);
    const onChange = () => setNarrow(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return narrow ? CELLS_NARROW : CELLS_WIDE;
}

/** Keys type into nothing here, so only real text fields and focused buttons keep their own keys. */
function ownsKey(target: EventTarget | null, key: string): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return true;
  return (key === " " || key === "Enter") && ["BUTTON", "A"].includes(target.tagName);
}

export function ResultView({ job, fileName, onReset }: ResultViewProps) {
  const violations = useMemo(
    () => [...job.violations].sort((a, b) => a.timecode_sec - b.timecode_sec),
    [job.violations],
  );
  const found = job.verdict === "violation" && violations.length > 0;
  const duration = job.video.duration_sec ?? 0;
  const preview = job.video.preview_url;
  const player = usePlayer(duration, job.video.fps);
  const cells = useStripCells();
  const [selected, setSelected] = useState(0);
  const [lightbox, setLightbox] = useState<number | null>(null);
  const current = found ? violations[selected] : null;
  const { seek } = player;

  // Choosing a violation shows its moment, paused: the large frame is the first evidence the reviewer sees.
  const select = useCallback((i: number) => {
    if (i < 0 || i >= violations.length) return;
    setSelected(i);
    setLightbox(null);
    seek(violations[i].timecode_sec);
  }, [violations, seek]);

  const playFrom = (sec: number) => {
    seek(sec);
    player.play();
  };
  const fullscreen = () => void player.ref.current?.requestFullscreen?.().catch(() => undefined);
  const zoom = (fi: number) => {
    player.pause();
    setLightbox(fi);
  };

  useEffect(() => {
    if (lightbox !== null) return; // the dialog owns the arrows while open
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey || ownsKey(e.target, e.key)) return;
      const stepSize = e.shiftKey ? SECOND_STEP / player.frameSec : 1;
      const actions: Record<string, () => void> = {
        ArrowLeft: () => player.step(-stepSize),
        ArrowRight: () => player.step(stepSize),
        " ": player.toggle,
        ArrowUp: () => select(selected - 1),
        ArrowDown: () => select(selected + 1),
      };
      const action = actions[e.key];
      if (!action || (!preview && e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
      e.preventDefault();
      action();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox, player, preview, select, selected]);

  return (
    <section className="result" aria-labelledby="verdict">
      <header className={`verdict${found ? " verdict-found" : " verdict-clear"}`}>
        <div className="verdict-text">
          {found && (
            <span className="verdict-mark" aria-hidden="true">
              <MarkerLoop variant={1} selected />
              <span className="verdict-mark-num">{violations.length}</span>
            </span>
          )}
          <div>
            <h1 id="verdict">{found ? "Обнаружены признаки возможных нарушений" : "Нарушение не обнаружено"}</h1>
            <p className="verdict-meta">
              {found && <span className="verdict-count">{pluralEvents(violations.length)}</span>}
              {fileName && <span>{fileName}</span>}
              <span className="num">{clock(duration)}</span>
              {job.timings.total_sec != null && (
                <span>проверка заняла <span className="num">{Math.round(job.timings.total_sec)} с</span></span>
              )}
            </p>
          </div>
        </div>
        <div className="verdict-actions">
          {job.result_url && (
            <a className="button-quiet" href={job.result_url} download>
              <Icon name="download" />
              Скачать JSON
            </a>
          )}
          <button type="button" className="button-primary" onClick={onReset}>
            Проверить другое видео
          </button>
        </div>
      </header>

      {job.partial && (
        <p className="alert" role="status">
          Анализ остановлен по лимиту времени. Показаны события, найденные до остановки; остальная часть
          видео не проверена.
        </p>
      )}

      <div className={`desk${found ? "" : " desk-clear"}`}>
        <div className="desk-case">
          {current ? (
            <>
              <ViolationPanel index={selected} total={violations.length} violation={current}
                onPrev={() => select(selected - 1)} onNext={() => select(selected + 1)}
                onPlayFrom={playFrom} onShowFrame={seek} onZoomFrame={zoom} />
              {violations.length > 1 && <EventList violations={violations} selected={selected} onSelect={select} />}
            </>
          ) : (
            <p className="clear-note">
              В видео не найдено моментов, похожих на нарушение. Это не подтверждает корректность операций,
              которые не видны в кадре (например, проводки в системе).
            </p>
          )}
        </div>

        <div className="desk-viewer">
          {duration > 0 && (
            <ContactStrip duration={duration} previewUrl={preview} violations={violations}
              selected={found ? selected : null} time={player.time} cells={cells}
              onSelect={select} onScrub={seek} />
          )}
          {preview ? (
            <>
              <video ref={player.ref} className="player" src={preview} preload="auto" playsInline
                onClick={player.toggle}
                onLoadedMetadata={() => current && seek(current.timecode_sec)} />
              <Transport player={player} duration={duration} moment={current?.timecode_sec ?? null}
                onFullscreen={fullscreen} />
              <p className="shortcuts">
                <kbd>←</kbd> <kbd>→</kbd> по кадру · <kbd>Shift</kbd> + стрелка — по секунде · <kbd>Пробел</kbd> пуск
                {found && <> · <kbd>↑</kbd> <kbd>↓</kbd> другое нарушение</>}
              </p>
            </>
          ) : (
            <p className="player-gone">Видео удалено после окончания срока хранения. Результат сохранён.</p>
          )}
        </div>
      </div>

      <p className="note">{HUMAN_REVIEW_NOTE}</p>

      {current && lightbox !== null && (
        <Lightbox violation={current} frameIndex={lightbox} onChange={setLightbox} onClose={() => setLightbox(null)} />
      )}
    </section>
  );
}
