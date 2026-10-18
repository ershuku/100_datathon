import { useEffect, useState } from "react";

import { clock } from "../format";
import { STAGES, errorText } from "../text";
import type { UiJob } from "../types";

const EXPOSURE_CELLS = 20; // the sheet fills one frame per 5% of real progress

interface StatusViewProps {
  job: UiJob | null;
  fileName: string | null;
  connectionError: string | null;
  onRetry: (() => void) | null;
  onReset: () => void;
}

function useElapsed(active: boolean): number {
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(start);
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return (now - start) / 1000;
}

function stageIndex(job: UiJob | null): number {
  if (!job || job.status === "queued") return 0;
  const i = STAGES.findIndex((s) => s.key === job.stage);
  return i < 0 ? 1 : i;
}

export function StatusView({ job, fileName, connectionError, onRetry, onReset }: StatusViewProps) {
  const failed = job?.status === "failed";
  const elapsed = useElapsed(!failed && !connectionError);
  const current = stageIndex(job);
  const progress = job?.progress ?? 0;
  const exposed = Math.round((progress / 100) * EXPOSURE_CELLS);

  if (failed || connectionError) {
    return (
      <section className="status status-failed" aria-labelledby="status-title">
        <h1 id="status-title">Проверка не выполнена</h1>
        <p className="alert" role="alert">
          {connectionError ?? errorText(job?.error_code)}
        </p>
        <div className="actions">
          {onRetry && (
            <button type="button" className="button-primary" onClick={onRetry}>
              Повторить проверку
            </button>
          )}
          <button type="button" className="button-quiet" onClick={onReset}>
            Загрузить другое видео
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="status" aria-labelledby="status-title" aria-busy="true">
      <h1 id="status-title">Идёт проверка</h1>
      {fileName && <p className="file-name">{fileName}</p>}
      <ol className="stages">
        {STAGES.map((stage, i) => (
          <li key={stage.key} className={i < current ? "is-done" : i === current ? "is-current" : ""}>
            <span className="stage-num" aria-hidden="true">{i + 1}</span>
            <span>
              {stage.label}
              {i === current && stage.key === "queued" && job?.queue_position != null && (
                <span className="muted"> — место в очереди: {job.queue_position}</span>
              )}
              {i === current && stage.key === "analyze" && job?.stage_text && !job.stage_text.startsWith(stage.label) && (
                <span className="muted"> — {job.stage_text}</span>
              )}
            </span>
          </li>
        ))}
      </ol>
      <ol className="exposure" role="progressbar" aria-label="Готовность" aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={progress}>
        {Array.from({ length: EXPOSURE_CELLS }, (_, i) => (
          <li key={i} className={i < exposed ? "is-exposed" : ""} />
        ))}
      </ol>
      <p className="status-meta" aria-live="polite">
        <span className="num">{progress}%</span> · прошло <span className="num">{clock(elapsed)}</span> · обычно
        проверка занимает до 5 минут
      </p>
    </section>
  );
}
