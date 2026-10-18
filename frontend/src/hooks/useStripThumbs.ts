import { useEffect, useRef, useState } from "react";

const THUMB_WIDTH = 240;
const SEEK_TIMEOUT_MS = 4000;

type Thumbs = (string | null)[];

function seekTo(video: HTMLVideoElement, sec: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("seek timeout")), SEEK_TIMEOUT_MS);
    video.addEventListener("seeked", () => {
      window.clearTimeout(timer);
      resolve();
    }, { once: true });
    video.currentTime = sec;
  });
}

function toBlobUrl(canvas: HTMLCanvasElement): Promise<string | null> {
  return new Promise((resolve) =>
    canvas.toBlob((blob) => resolve(blob ? URL.createObjectURL(blob) : null), "image/jpeg", 0.72));
}

/**
 * Samples one still per strip cell from the same-origin preview video, entirely in the browser.
 * Cells stay null (drawn as empty film) when there is no preview or a seek fails.
 * Finished sets are cached per cell count, so crossing a layout breakpoint and back reuses them.
 */
export function useStripThumbs(previewUrl: string | null, duration: number, count: number): Thumbs {
  const cache = useRef(new Map<string, Thumbs>());
  const key = `${previewUrl}|${duration}|${count}`;
  const [thumbs, setThumbs] = useState<Thumbs>(() => Array(count).fill(null));

  useEffect(() => {
    const store = cache.current;
    return () => {
      store.forEach((set) => set.forEach((url) => url && URL.revokeObjectURL(url)));
      store.clear();
    };
  }, []);

  useEffect(() => {
    const cached = cache.current.get(key);
    if (cached) {
      setThumbs(cached);
      return;
    }
    setThumbs(Array(count).fill(null));
    if (!previewUrl || duration <= 0 || count <= 0) return;

    let cancelled = false;
    const created: Thumbs = Array(count).fill(null);
    const video = document.createElement("video");
    video.muted = true;
    video.preload = "auto";
    video.playsInline = true;
    video.src = previewUrl;

    const run = async () => {
      await new Promise<void>((resolve, reject) => {
        video.addEventListener("loadeddata", () => resolve(), { once: true });
        video.addEventListener("error", () => reject(new Error("preview load failed")), { once: true });
      });
      const canvas = document.createElement("canvas");
      canvas.width = THUMB_WIDTH;
      canvas.height = Math.round(THUMB_WIDTH * (video.videoHeight / video.videoWidth || 9 / 16));
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      for (let i = 0; i < count && !cancelled; i++) {
        const mid = ((i + 0.5) / count) * duration;
        try {
          await seekTo(video, Math.min(mid, Math.max(0, duration - 0.05)));
        } catch {
          continue;
        }
        if (cancelled) return;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const url = await toBlobUrl(canvas);
        if (!url) continue;
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        created[i] = url;
        setThumbs([...created]);
      }
      if (!cancelled) cache.current.set(key, [...created]);
    };

    run().catch(() => undefined); // strip falls back to empty film cells
    return () => {
      cancelled = true;
      video.removeAttribute("src");
      video.load();
      if (!cache.current.has(key)) created.forEach((url) => url && URL.revokeObjectURL(url));
    };
  }, [key, previewUrl, duration, count]);

  return thumbs;
}
