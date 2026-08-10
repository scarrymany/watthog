"""Фоновые задачи оконного интерфейса.

Замер блокирует поток на всё своё время, поэтому выполняется отдельно от
цикла событий tkinter. Обмен идёт через очередь: рабочий поток только кладёт
события, а окно забирает их по таймеру и рисует. Виджеты из рабочего потока
не трогаются - tkinter этого не допускает.

Источники телеметрии открываются и закрываются внутри того же потока, где
читаются: дескрипторы NVML и PDH привязаны к потоку, который их создал.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

from watthog.config import Settings
from watthog.inventory import HardwareProfile
from watthog.meter import PowerMeter
from watthog.session import MeasurementSession, Sample, SessionResult
from watthog.telemetry import SourceStatus, TelemetryReader


@dataclass(frozen=True)
class HardwareFound:
    profile: HardwareProfile
    sources: tuple[SourceStatus, ...]


@dataclass(frozen=True)
class SampleTaken:
    sample: Sample
    duration_seconds: float


@dataclass(frozen=True)
class MeasurementFinished:
    result: SessionResult


@dataclass(frozen=True)
class TaskFailed:
    message: str


Event = HardwareFound | SampleTaken | MeasurementFinished | TaskFailed


class _BackgroundTask:
    """Общая обвязка: поток, очередь событий и безопасное чтение результатов."""

    def __init__(self) -> None:
        self._events: queue.Queue[Event] = queue.Queue()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def drain(self) -> list[Event]:
        """Забирает все накопившиеся события, не блокируя цикл событий окна."""
        collected: list[Event] = []
        while True:
            try:
                collected.append(self._events.get_nowait())
            except queue.Empty:
                return collected

    def _spawn(self, target, name: str) -> None:
        self._thread = threading.Thread(target=target, name=name, daemon=True)
        self._thread.start()

    def _publish(self, event: Event) -> None:
        self._events.put(event)


class HardwareProbe(_BackgroundTask):
    """Однократное определение железа и доступных источников телеметрии."""

    def start(self, settings: Settings) -> None:
        if self.running:
            return
        self._spawn(lambda: self._probe(settings), "watthog-probe")

    def _probe(self, settings: Settings) -> None:
        try:
            with TelemetryReader(settings) as reader:
                self._publish(HardwareFound(reader.profile, reader.sources))
        except Exception as error:  # noqa: BLE001 - источники телеметрии разнородны
            self._publish(TaskFailed(f"Не удалось определить железо: {error}"))


class MeasurementWorker(_BackgroundTask):
    """Проведение замера в фоне с возможностью досрочной остановки."""

    def __init__(self) -> None:
        super().__init__()
        self._stop = threading.Event()

    def start(self, settings: Settings, duration_seconds: float) -> None:
        if self.running:
            return
        self._stop.clear()
        self._spawn(lambda: self._measure(settings, duration_seconds), "watthog-measure")

    def request_stop(self) -> None:
        self._stop.set()

    @property
    def stop_requested(self) -> bool:
        return self._stop.is_set()

    def _measure(self, settings: Settings, duration_seconds: float) -> None:
        reader = TelemetryReader(settings)
        try:
            reader.open()
        except Exception as error:  # noqa: BLE001 - источники телеметрии разнородны
            self._publish(TaskFailed(f"Не удалось открыть источники телеметрии: {error}"))
            return

        try:
            self._publish(HardwareFound(reader.profile, reader.sources))
            session = MeasurementSession(reader, PowerMeter(reader.profile, settings), settings)
            result = session.run(
                duration_seconds,
                on_sample=lambda sample, duration: self._publish(SampleTaken(sample, duration)),
                stop_requested=self._stop.is_set,
            )
            self._publish(MeasurementFinished(result))
        except Exception as error:  # noqa: BLE001 - падение замера не должно ронять окно
            self._publish(TaskFailed(f"Замер прерван ошибкой: {error}"))
        finally:
            reader.close()
