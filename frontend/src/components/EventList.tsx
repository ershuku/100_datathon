import { bindSlash, timecode } from "../format";
import type { UiViolation } from "../types";

interface EventListProps {
  violations: UiViolation[];
  selected: number;
  onSelect: (index: number) => void;
}

/** Every flagged moment at a glance, in time order. */
export function EventList({ violations, selected, onSelect }: EventListProps) {
  return (
    <nav className="event-list" aria-label="Все нарушения">
      <ol>
        {violations.map((v, i) => (
          <li key={`${v.timecode_sec}-${i}`}>
            <button type="button" className="event-row" aria-current={i === selected ? "true" : undefined}
              onClick={() => onSelect(i)}>
              <span className="event-row-num">{i + 1}</span>
              <span className="event-row-time">{timecode(v.timecode_sec)}</span>
              <span className="event-row-type">{bindSlash(v.type)}</span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
