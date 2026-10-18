// Hand-drawn china-marker loops, two passes each: a heavy stroke that overshoots and crosses its own start,
// and a lighter second pass slightly off the first, the way a wax marker skips and doubles on a print.
const LOOPS = [
  {
    tilt: -4,
    main: "M80 9 C104 7 131 15 137 37 C143 60 127 84 96 91 C70 97 35 93 17 76 C3 62 6 37 24 22 C38 11 58 8 74 10 C96 12 114 6 130 1",
    echo: "M70 14 C98 11 128 22 131 44 C134 66 112 85 82 88 C52 91 21 82 13 61 C8 43 22 23 47 15",
  },
  {
    tilt: 3,
    main: "M64 7 C95 3 128 12 138 33 C147 55 134 80 104 90 C78 98 40 96 20 80 C4 67 4 40 21 24 C35 11 55 6 76 8 C98 10 118 18 134 30",
    echo: "M58 13 C88 9 124 18 132 40 C139 62 120 84 92 89 C62 93 26 85 15 64 C7 46 18 26 40 16",
  },
  {
    tilt: -2,
    main: "M74 6 C102 4 133 14 139 38 C144 61 125 85 92 92 C64 97 30 92 14 73 C1 57 7 32 27 18 C42 8 62 5 80 8 C100 11 120 4 136 -2",
    echo: "M66 12 C94 9 127 20 132 42 C136 64 114 86 86 89 C56 92 22 82 12 62 C5 44 20 24 43 15",
  },
];

interface MarkerLoopProps {
  variant: number;
  selected: boolean;
  delayMs?: number;
}

/** Sits over its positioned parent; both passes draw themselves on mount and again when selected. */
export function MarkerLoop({ variant, selected, delayMs = 0 }: MarkerLoopProps) {
  const loop = LOOPS[variant % LOOPS.length];
  const pass = selected ? "on" : "off";
  return (
    <svg className={`marker-loop${selected ? " is-selected" : ""}`} viewBox="0 0 144 100" aria-hidden="true"
      focusable="false">
      <g transform={`rotate(${loop.tilt} 72 50)`}>
        <path key={`main-${pass}`} className="marker-main" d={loop.main} pathLength={1}
          style={{ animationDelay: `${delayMs}ms` }} />
        <path key={`echo-${pass}`} className="marker-echo" d={loop.echo} pathLength={1}
          style={{ animationDelay: `${delayMs + 240}ms` }} />
      </g>
    </svg>
  );
}
