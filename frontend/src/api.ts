import type { UiConfig, UiJob } from "./types";

export class ApiError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
    message: string,
    readonly retryAfterSec: number | null = null,
  ) {
    super(message);
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let code = `http_${res.status}`;
  let message = res.statusText;
  try {
    const body = await res.json();
    code = body.code ?? code;
    message = body.detail ?? message;
  } catch {
    /* non-JSON error body */
  }
  const retry = Number(res.headers.get("Retry-After"));
  return new ApiError(code, res.status, message, Number.isFinite(retry) && retry > 0 ? retry : null);
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, { signal, headers: { Accept: "application/json" } });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("network", 0, "network error");
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export const getConfig = (signal?: AbortSignal) => getJson<UiConfig>("/ui/config", signal);

export const getJob = (jobId: string, signal?: AbortSignal) =>
  getJson<UiJob>(`/ui/jobs/${encodeURIComponent(jobId)}`, signal);

/** XHR instead of fetch: fetch has no upload progress events. */
export function uploadVideo(
  file: File,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<{ job_id: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/ui/analyze");
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onerror = () => reject(new ApiError("network", 0, "network error"));
    xhr.onabort = () => reject(new DOMException("aborted", "AbortError"));
    xhr.onload = () => {
      const body = xhr.response ?? {};
      if (xhr.status >= 200 && xhr.status < 300 && body.job_id) return resolve(body);
      const retry = Number(xhr.getResponseHeader("Retry-After"));
      reject(new ApiError(body.code ?? `http_${xhr.status}`, xhr.status, body.detail ?? "upload failed",
        Number.isFinite(retry) && retry > 0 ? retry : null));
    };
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    const form = new FormData();
    form.append("file", file, file.name);
    xhr.send(form);
  });
}
