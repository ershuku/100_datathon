"""DummyAnalyzer: realistic fake results so the API and UI work before the ML pipeline exists.

Every description is prefixed with a test-mode marker so a dummy result can never pass for a
real one (PRODUCT_FLOW §10: mock mode must be off for the real submission).
"""

from __future__ import annotations

import time

from app.analysis.port import AnalyzerOutput, DetectedEvent, EvidenceRef, JobContext, Reporter

MARK = "[ТЕСТОВЫЙ РЕЖИМ] "
STEP_SEC = 0.2

_FAKE_EVENTS = (
    ("TABLE", "На столе остаются наличные предыдущего клиента, когда к кассе подходит следующий клиент."),
    ("SAFE", "Сейф остаётся открытым, кассир продолжает другую работу."),
    ("PERSONAL", "Личные вещи кассира находятся на рабочей поверхности рядом с наличными."),
)

_STAGES = ("Поиск людей и предметов", "Анализ действий кассира", "Проверка правил")


class DummyAnalyzer:
    def __init__(self, delay_sec: float = 8.0, scenario: str = "auto") -> None:
        self.delay_sec = delay_sec
        self.scenario = scenario

    def _event_count(self, ctx: JobContext) -> int:
        if self.scenario == "none":
            return 0
        if self.scenario in ("violations", "slow"):
            return 2
        if self.scenario == "review":
            return 1
        return int(ctx.duration_sec * 10) % 3  # auto: deterministic per video, 0-2 events

    def _make_event(self, index: int, count: int, ctx: JobContext) -> DetectedEvent:
        code, text = _FAKE_EVENTS[index % len(_FAKE_EVENTS)]
        t = round(ctx.duration_sec * (index + 1) / (count + 1), 1)
        moments = sorted({max(0.0, round(t - 1.0, 1)), t, min(round(ctx.duration_sec - 0.1, 1), round(t + 1.0, 1))})
        return DetectedEvent(
            type_code=code,
            timecode_sec=t,
            description=MARK + text,
            evidence=tuple(EvidenceRef(timestamp_sec=m) for m in moments[:3]),
            needs_review=self.scenario == "review",
        )

    def analyze_video(self, video_path: str, ctx: JobContext, reporter: Reporter) -> AnalyzerOutput:
        if self.scenario == "crash":
            raise RuntimeError("dummy analyzer crash (DUMMY_SCENARIO=crash)")
        delay = 10_000.0 if self.scenario == "slow" else self.delay_sec
        count = self._event_count(ctx)
        events = [self._make_event(i, count, ctx) for i in range(count)]

        started = time.monotonic()
        reported = 0
        if self.scenario == "slow":  # report early so TIMEOUT_FALLBACK=partial has something to return
            for event in events:
                reporter.event(event)
            reported = len(events)
        while (elapsed := time.monotonic() - started) < delay:
            fraction = elapsed / delay if delay else 1.0
            reporter.progress(int(fraction * 100), _STAGES[min(len(_STAGES) - 1, int(fraction * len(_STAGES)))])
            while reported < len(events) and fraction >= (reported + 1) / (len(events) + 1):
                reporter.event(events[reported])
                reported += 1
            time.sleep(STEP_SEC)
        reporter.progress(100, _STAGES[-1])
        return AnalyzerOutput(events=tuple(events), debug={"analyzer": "dummy", "scenario": self.scenario})
