import { bindSlash, timecode } from "../format";
import type { UiViolation } from "../types";
import { Icon } from "./Icon";

interface ViolationPanelProps {
  index: number;
  total: number;
  violation: UiViolation;
  onPrev: () => void;
  onNext: () => void;
  onPlayFrom: (sec: number) => void;
  onShowFrame: (sec: number) => void;
  onZoomFrame: (frameIndex: number) => void;
}

const PUNKT_PREFIX = /^(п\.|пп\.|раздел|глава|ст\.)/i;

/** The selected violation, read first: what it is, when, why, on what basis, and its evidence frames. */
export function ViolationPanel(props: ViolationPanelProps) {
  const { index, total, violation: v, onPrev, onNext, onPlayFrom, onShowFrame, onZoomFrame } = props;
  return (
    <article className="violation" aria-labelledby="violation-title">
      <div className="violation-nav">
        <button type="button" className="tool" onClick={onPrev} disabled={index === 0}
          aria-label="Предыдущее нарушение" title="Предыдущее (↑)">
          <Icon name="prev" />
        </button>
        <p className="violation-count" aria-live="polite">
          Нарушение <span className="num">{index + 1}</span> из <span className="num">{total}</span>
        </p>
        <button type="button" className="tool" onClick={onNext} disabled={index === total - 1}
          aria-label="Следующее нарушение" title="Следующее (↓)">
          <Icon name="next" />
        </button>
      </div>

      <h2 id="violation-title" className="violation-type">{bindSlash(v.type)}</h2>

      <button type="button" className="violation-play" onClick={() => onPlayFrom(v.timecode_sec)}>
        <Icon name="play" size={20} />
        <span>Смотреть с <span className="mono">{timecode(v.timecode_sec)}</span></span>
      </button>

      {v.needs_review && <p className="violation-flag">Требует дополнительной проверки человеком</p>}
      <p className="violation-text">{v.description}</p>

      <dl className="violation-basis">
        <dt>Основание</dt>
        {v.legal_ref ? (
          <dd>
            <p>
              {v.legal_ref.document}, {PUNKT_PREFIX.test(v.legal_ref.punkt) ? "" : "п. "}
              {v.legal_ref.punkt}
            </p>
            {v.legal_ref.rule_text && <p className="violation-rule">{v.legal_ref.rule_text}</p>}
            {v.legal_ref.url && (
              <a className="link" href={v.legal_ref.url} target="_blank" rel="noopener noreferrer">
                Открыть источник
                <Icon name="external" size={15} />
              </a>
            )}
          </dd>
        ) : (
          <dd className="violation-missing">Нормативное основание для этого типа ещё не указано командой.</dd>
        )}
      </dl>

      {v.evidence_frames.length > 0 && (
        <div className="evidence">
          <p className="evidence-label">Кадры-доказательства</p>
          <ul className="evidence-frames">
            {v.evidence_frames.map((f, fi) => (
              <li key={f.url}>
                <button type="button" className="evidence-frame" onClick={() => onShowFrame(f.timestamp_sec)}
                  aria-label={`Показать в видео кадр ${timecode(f.timestamp_sec)}`}>
                  <img src={f.url} alt="" />
                  <span className="evidence-time">{timecode(f.timestamp_sec)}</span>
                </button>
                <button type="button" className="evidence-zoom" onClick={() => onZoomFrame(fi)}
                  aria-label={`Открыть исходный кадр ${timecode(f.timestamp_sec)} крупно`}>
                  <Icon name="expand" size={15} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
