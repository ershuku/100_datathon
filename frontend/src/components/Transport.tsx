import { preciseTime, timecode } from "../format";
import type { Player } from "../hooks/usePlayer";
import { Icon } from "./Icon";

interface TransportProps {
  player: Player;
  duration: number;
  /** The selected violation's moment, when there is one. */
  moment: number | null;
  onFullscreen: () => void;
}

/** Frame-accurate review controls under the video. The native controls are off so there is one scrubber. */
export function Transport({ player, duration, moment, onFullscreen }: TransportProps) {
  const frame = Math.round(player.time / player.frameSec) + 1;
  return (
    <div className="transport">
      <div className="transport-buttons" role="group" aria-label="Управление видео">
        <button type="button" className="tool" onClick={() => player.step(-1)} aria-label="Кадр назад"
          title="Кадр назад (←)">
          <Icon name="frameBack" />
        </button>
        <button type="button" className="tool tool-play" onClick={player.toggle}
          aria-label={player.playing ? "Пауза" : "Воспроизвести"} title="Пуск / пауза (пробел)">
          <Icon name={player.playing ? "pause" : "play"} />
        </button>
        <button type="button" className="tool" onClick={() => player.step(1)} aria-label="Кадр вперёд"
          title="Кадр вперёд (→)">
          <Icon name="frameFwd" />
        </button>
      </div>

      <p className="transport-time" aria-live="off">
        <span className="transport-now">{preciseTime(player.time)}</span>
        <span className="transport-total"> / {timecode(duration)}</span>
        <span className="transport-frame">кадр {frame}</span>
      </p>

      <div className="transport-end">
        {moment !== null && (
          <button type="button" className="button-quiet" onClick={() => player.seek(moment)}>
            <Icon name="target" />
            К моменту {timecode(moment)}
          </button>
        )}
        <button type="button" className="tool" onClick={onFullscreen} aria-label="На весь экран">
          <Icon name="fullscreen" />
        </button>
      </div>
    </div>
  );
}
