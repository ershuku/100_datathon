import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getConfig, uploadVideo } from "./api";
import { ResultView } from "./components/ResultView";
import { StatusView } from "./components/StatusView";
import { UploadView, validateFile } from "./components/UploadView";
import { useJobPolling } from "./hooks/useJobPolling";
import { errorText } from "./text";
import type { UiConfig } from "./types";

const DEFAULT_CONFIG: UiConfig = { pipeline: "real", max_upload_mb: 300, poll_interval_ms: 2000 };

function jobFromUrl(): string | null {
  const id = new URLSearchParams(window.location.search).get("job");
  return id && /^[0-9a-f]{16}$/.test(id) ? id : null;
}

function setJobInUrl(jobId: string | null) {
  const url = new URL(window.location.href);
  if (jobId) url.searchParams.set("job", jobId);
  else url.searchParams.delete("job");
  window.history.replaceState(null, "", url);
}

function JobScreen(props: { jobId: string; fileName: string | null; pollMs: number;
  onRetry: (() => void) | null; onReset: () => void }) {
  const { job, error } = useJobPolling(props.jobId, props.pollMs);
  if (job?.status === "done") return <ResultView job={job} fileName={props.fileName} onReset={props.onReset} />;
  return (
    <StatusView job={job} fileName={props.fileName} connectionError={error ? errorText(error.code) : null}
      onRetry={props.onRetry} onReset={props.onReset} />
  );
}

export function App() {
  const [config, setConfig] = useState<UiConfig>(DEFAULT_CONFIG);
  const [jobId, setJobId] = useState<string | null>(jobFromUrl);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState<{ file: File; fraction: number } | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getConfig(controller.signal).then(setConfig).catch(() => undefined);
    return () => controller.abort();
  }, []);

  const start = useCallback(async (selected: File) => {
    const problem = validateFile(selected, config.max_upload_mb);
    setUploadError(problem);
    if (problem) return;
    abort.current = new AbortController();
    setFile(selected);
    setUploading({ file: selected, fraction: 0 });
    try {
      const { job_id } = await uploadVideo(selected, (fraction) => setUploading({ file: selected, fraction }),
        abort.current.signal);
      setJobInUrl(job_id);
      setJobId(job_id);
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setUploadError(err instanceof ApiError ? errorText(err.code) : errorText(null));
      }
    } finally {
      setUploading(null);
    }
  }, [config.max_upload_mb]);

  const reset = useCallback(() => {
    setJobInUrl(null);
    setJobId(null);
    setUploadError(null);
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="/" onClick={(e) => { e.preventDefault(); reset(); }}>
          <img src="/favicon.svg" alt="" width={24} height={24} />
          Проверка кассовых операций
        </a>        {config.pipeline === "dummy" && (
          <span className="mode-badge" title="PIPELINE=dummy">Тестовый режим: результаты не настоящие</span>
        )}
      </header>
      <main>
        {jobId ? (
          <JobScreen key={jobId} jobId={jobId} fileName={file?.name ?? null} pollMs={config.poll_interval_ms}
            onRetry={file ? () => { reset(); void start(file); } : null} onReset={reset} />
        ) : (
          <UploadView maxUploadMb={config.max_upload_mb} uploading={uploading} error={uploadError}
            onSelect={start} onCancel={() => abort.current?.abort()} />
        )}
      </main>
    </div>
  );
}
