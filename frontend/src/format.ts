/** 44.2 -> "0:44.2", 125 -> "2:05.0" */
export function timecode(sec: number): string {
  const safe = Math.max(0, sec);
  const minutes = Math.floor(safe / 60);
  const rest = safe - minutes * 60;
  return `${minutes}:${rest.toFixed(1).padStart(4, "0")}`;
}

/** 44.233 -> "0:44.23" (hundredths, for frame-by-frame stepping) */
export function preciseTime(sec: number): string {
  const safe = Math.max(0, sec);
  const minutes = Math.floor(safe / 60);
  const rest = safe - minutes * 60;
  return `${minutes}:${rest.toFixed(2).padStart(5, "0")}`;
}

/** 42 -> "0:42" (clock without tenths) */
export function clock(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** "A / B" -> "A / B": a line never starts with the slash. */
export function bindSlash(text: string): string {
  return text.replace(/ \//g, " /");
}

export function megabytes(bytes: number): string {
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} МБ`;
}
