// One stroke family (1.75px, round joins) for every icon in the app.
const PATHS = {
  prev: "M14.5 6 8.5 12l6 6",
  next: "M9.5 6l6 6-6 6",
  play: "M8 5.5v13l10.5-6.5z",
  pause: "M8.5 5.5v13M15.5 5.5v13",
  frameBack: "M17 6.5 10 12l7 5.5M7 6v12",
  frameFwd: "M7 6.5l7 5.5-7 5.5M17 6v12",
  target: "M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z",
  fullscreen: "M4.5 9V4.5H9M15 4.5h4.5V9M19.5 15v4.5H15M9 19.5H4.5V15",
  download: "M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19.5h14",
  expand: "M14 5h5v5M10 19H5v-5M19 5l-6 6M5 19l6-6",
  upload: "M12 19V8m0 0-4.5 4.5M12 8l4.5 4.5M5 4.5h14",
  external: "M14 5h5v5M19 5l-8 8M17 14v5H5V7h5",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} />
    </svg>
  );
}
