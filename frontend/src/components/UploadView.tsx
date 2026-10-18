import { useRef, useState, type DragEvent } from "react";

import { megabytes } from "../format";
import { Icon } from "./Icon";

const FILM_CELLS = 8;

interface UploadViewProps {
  maxUploadMb: number;
  uploading: { file: File; fraction: number } | null;
  error: string | null;
  onSelect: (file: File) => void;
  onCancel: () => void;
}

export function validateFile(file: File, maxUploadMb: number): string | null {
  if (!file.name.toLowerCase().endsWith(".mov")) return "Нужен файл в формате .mov.";
  if (file.size === 0) return "Файл пустой.";
  if (file.size > maxUploadMb * 1024 * 1024) return `Файл больше ${maxUploadMb} МБ.`;
  return null;
}

export function UploadView({ maxUploadMb, uploading, error, onSelect, onCancel }: UploadViewProps) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && !uploading) onSelect(file);
  };

  return (
    <section className="intake" aria-labelledby="intake-title">
      <div className="intake-copy">
        <h1 id="intake-title">Проверка видеозаписи кассы</h1>
        <p>
          Загрузите запись работы кассира. Сервис найдёт моменты, похожие на нарушение кассовой
          дисциплины, и покажет таймкод, кадры и правило. Видео анализируется локально и удаляется
          после проверки.
        </p>
      </div>

      <div
        className={`dropzone${dragging ? " is-dragging" : ""}${uploading ? " is-busy" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        {uploading ? (
          <div className="upload-progress" role="status" aria-live="polite">
            <p className="file-name">{uploading.file.name}</p>
            <div className="bar" aria-hidden="true">
              <span style={{ transform: `scaleX(${uploading.fraction})` }} />
            </div>
            <p className="muted">
              Передача файла: {Math.round(uploading.fraction * 100)}% из {megabytes(uploading.file.size)}
            </p>
            <button type="button" className="button-quiet" onClick={onCancel}>
              Отменить загрузку
            </button>
          </div>
        ) : (
          <>
            <ol className="drop-film" aria-hidden="true">
              {Array.from({ length: FILM_CELLS }, (_, i) => <li key={i} />)}
            </ol>
            <p className="drop-title">Перетащите файл .mov сюда</p>
            <button type="button" className="button-primary" onClick={() => input.current?.click()}>
              <Icon name="upload" />
              Выбрать видео
            </button>
            <p className="muted">Формат .mov, до {maxUploadMb} МБ. Звук не используется.</p>
          </>
        )}
        <input
          ref={input}
          type="file"
          accept=".mov,video/quicktime"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) onSelect(file);
          }}
        />
      </div>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
