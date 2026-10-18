import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

const DEFAULT_FPS = 30;
const VISIBLE_RATIO = 0.25; // below this much of the player on screen, playback stops

export interface Player {
  ref: RefObject<HTMLVideoElement | null>;
  time: number;
  playing: boolean;
  frameSec: number;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  /** Moves to sec and stays paused there. */
  seek: (sec: number) => void;
  step: (frames: number) => void;
}

/**
 * One owner for the review video. The playhead is driven by requestAnimationFrame while playing, so the
 * strip line moves smoothly, and playback never continues out of sight: it pauses when the player
 * scrolls away or the tab is hidden.
 */
export function usePlayer(duration: number, fps: number | null): Player {
  const ref = useRef<HTMLVideoElement | null>(null);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const frameSec = 1 / (fps && fps > 0 ? fps : DEFAULT_FPS);

  const clamp = useCallback((sec: number) => Math.min(Math.max(0, sec), Math.max(0, duration - frameSec / 2)),
    [duration, frameSec]);

  const pause = useCallback(() => ref.current?.pause(), []);
  const play = useCallback(() => {
    void ref.current?.play().catch(() => undefined);
  }, []);
  const toggle = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    if (el.paused) play();
    else pause();
  }, [play, pause]);
  const seek = useCallback((sec: number) => {
    const el = ref.current;
    if (!el) return;
    el.pause();
    el.currentTime = clamp(sec);
    setTime(el.currentTime);
  }, [clamp]);
  const step = useCallback((frames: number) => {
    const el = ref.current;
    if (!el) return;
    seek(el.currentTime + frames * frameSec);
  }, [seek, frameSec]);

  // Mirror the element's state; rAF only while playing.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const tick = () => {
      setTime(el.currentTime);
      raf = requestAnimationFrame(tick);
    };
    const onPlay = () => {
      setPlaying(true);
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(tick);
    };
    const onPause = () => {
      setPlaying(false);
      cancelAnimationFrame(raf);
      setTime(el.currentTime);
    };
    const onSeeked = () => setTime(el.currentTime);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onPause);
    el.addEventListener("seeked", onSeeked);
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onPause);
      el.removeEventListener("seeked", onSeeked);
    };
  }, []);

  // Never play where nobody is looking.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => {
      if (entry.intersectionRatio < VISIBLE_RATIO) el.pause();
    }, { threshold: [0, VISIBLE_RATIO] });
    io.observe(el);
    const onHidden = () => document.hidden && el.pause();
    document.addEventListener("visibilitychange", onHidden);
    return () => {
      io.disconnect();
      document.removeEventListener("visibilitychange", onHidden);
    };
  }, []);

  return { ref, time, playing, frameSec, play, pause, toggle, seek, step };
}
