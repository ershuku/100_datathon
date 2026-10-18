// All user-facing Russian copy lives here.

const ERRORS: Record<string, string> = {
  unsupported_extension: "Нужен файл в формате .mov. Выберите исходную видеозапись.",
  unsupported_container: "Файл назван .mov, но внутри другой формат. Загрузите исходную запись .mov.",
  unreadable_video: "Файл не читается как видео. Возможно, он повреждён — загрузите его ещё раз.",
  no_video_stream: "В файле нет видеодорожки.",
  file_too_large: "Файл слишком большой.",
  empty_file: "Файл пустой.",
  duration_out_of_range: "Длительность видео вне допустимого диапазона.",
  missing_file: "Файл не был передан. Выберите видео ещё раз.",
  queue_full: "Сервис сейчас загружен другими проверками. Повторите через минуту.",
  rate_limited: "Слишком много запросов подряд. Подождите минуту и повторите.",
  timeout: "Анализ не уложился в 5 минут. Повторите попытку; если ошибка повторится, сообщите команде.",
  analysis_failed: "Модуль анализа завершился с ошибкой. Повторите попытку.",
  transcode_failed: "Видео не удалось декодировать. Проверьте, что файл открывается в плеере.",
  probe_timeout: "Видео не удалось прочитать вовремя. Повторите попытку.",
  no_evidence: "Не удалось извлечь кадры-доказательства из видео.",
  interrupted: "Сервис перезапускался во время обработки. Загрузите видео ещё раз.",
  internal_error: "Внутренняя ошибка сервиса. Повторите попытку.",
  network: "Нет связи с сервером. Проверьте подключение и повторите.",
  job_not_found: "Проверка не найдена. Возможно, ссылка устарела или сервис был переустановлен.",
};

export function errorText(code: string | null | undefined): string {
  return (code && ERRORS[code]) || "Не удалось обработать видео. Повторите попытку.";
}

export const STAGES = [
  { key: "queued", label: "Ожидание в очереди" },
  { key: "normalize", label: "Подготовка видео" },
  { key: "analyze", label: "Анализ действий" },
  { key: "evidence", label: "Кадры-доказательства" },
] as const;

export const HUMAN_REVIEW_NOTE =
  "Результат является подсказкой для проверки человеком, а не окончательным заключением.";

export function pluralEvents(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} событие`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} события`;
  return `${n} событий`;
}
