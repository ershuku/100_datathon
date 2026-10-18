// Mirrors src/app/schemas/ui.py (UI API, not the public jury contract).

export type JobStatus = "queued" | "processing" | "done" | "failed";
export type Verdict = "violation" | "no_violation";

export interface LegalRef {
  document: string;
  punkt: string;
  rule_text: string | null;
  url: string | null;
}

export interface UiFrame {
  timestamp_sec: number;
  url: string;
}

export interface UiViolation {
  type: string;
  type_code: string;
  timecode_sec: number;
  description: string;
  legal_ref: LegalRef | null;
  needs_review: boolean;
  evidence_frames: UiFrame[];
}

export interface UiJob {
  job_id: string;
  status: JobStatus;
  stage: string;
  stage_text: string;
  progress: number;
  queue_position: number | null;
  error: string | null;
  error_code: string | null;
  timings: { queue_wait_sec: number | null; processing_sec: number | null; total_sec: number | null };
  video: {
    duration_sec: number | null;
    fps: number | null;
    width: number | null;
    height: number | null;
    preview_url: string | null;
  };
  verdict: Verdict | null;
  partial: boolean;
  violations: UiViolation[];
  result_url: string | null;
}

export interface UiConfig {
  pipeline: string;
  max_upload_mb: number;
  poll_interval_ms: number;
}
