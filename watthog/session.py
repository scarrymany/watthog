"""Проведение замера: цикл выборок, интегрирование энергии и статистика."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from watthog import constants as const
from watthog.config import Settings
from watthog.inventory import HardwareProfile
from watthog.meter import Accuracy, PowerBreakdown, PowerMeter, average_breakdown
from watthog.telemetry import SourceStatus, Telemetry, TelemetryReader


@dataclass(frozen=True)
class Sample:
    """Одна выборка: момент времени, мощность и её разбивка."""

    elapsed: float
    watts: float
    breakdown: PowerBreakdown
    accuracy: Accuracy
    telemetry: Telemetry


@dataclass(frozen=True)
class SessionResult:
    started_at: datetime
    duration_seconds: float
    sample_count: int
    average_watts: float
    minimum_watts: float
    maximum_watts: float
    median_watts: float
    percentile95_watts: float
    energy_wh: float
    average_breakdown: PowerBreakdown
    accuracy: Accuracy
    profile: HardwareProfile
    sources: tuple[SourceStatus, ...]
    settings: Settings
    interrupted: bool

    @property
    def average_dc_watts(self) -> float:
        return self.average_breakdown.total_dc


SampleCallback = Callable[[Sample, float], None]


class MeasurementSession:
    """Цикл измерения с фиксированным шагом и накоплением статистики."""

    def __init__(self, reader: TelemetryReader, meter: PowerMeter, settings: Settings) -> None:
        self._reader = reader
        self._meter = meter
        self._settings = settings

    def run(self, duration_seconds: float, on_sample: SampleCallback | None = None) -> SessionResult:
        interval = self._settings.sample_interval
        total_ticks = max(1, round(duration_seconds / interval))
        started_at = datetime.now()
        start = time.monotonic()

        samples: list[Sample] = []
        interrupted = False
        try:
            for tick in range(1, total_ticks + 1):
                _sleep_until(start + tick * interval)
                telemetry = self._reader.read()
                breakdown = self._meter.measure(telemetry)
                sample = Sample(
                    elapsed=time.monotonic() - start,
                    watts=breakdown.total_ac,
                    breakdown=breakdown,
                    accuracy=self._meter.accuracy(telemetry),
                    telemetry=telemetry,
                )
                samples.append(sample)
                if on_sample is not None:
                    on_sample(sample, duration_seconds)
        except KeyboardInterrupt:
            interrupted = True

        return self._summarize(samples, started_at, interrupted)

    def _summarize(self, samples: list[Sample], started_at: datetime, interrupted: bool) -> SessionResult:
        profile = self._reader.profile
        sources = self._reader.sources
        if not samples:
            return SessionResult(
                started_at=started_at,
                duration_seconds=0.0,
                sample_count=0,
                average_watts=0.0,
                minimum_watts=0.0,
                maximum_watts=0.0,
                median_watts=0.0,
                percentile95_watts=0.0,
                energy_wh=0.0,
                average_breakdown=PowerBreakdown(),
                accuracy=Accuracy.MODELED,
                profile=profile,
                sources=sources,
                settings=self._settings,
                interrupted=interrupted,
            )

        watts = [sample.watts for sample in samples]
        elapsed = samples[-1].elapsed
        energy_wh = _integrate_energy_wh(samples)

        return SessionResult(
            started_at=started_at,
            duration_seconds=elapsed,
            sample_count=len(samples),
            average_watts=energy_wh * const.SECONDS_PER_HOUR / elapsed if elapsed > 0 else watts[-1],
            minimum_watts=min(watts),
            maximum_watts=max(watts),
            median_watts=percentile(watts, 50.0),
            percentile95_watts=percentile(watts, 95.0),
            energy_wh=energy_wh,
            average_breakdown=average_breakdown([sample.breakdown for sample in samples]),
            accuracy=_dominant_accuracy(samples),
            profile=profile,
            sources=sources,
            settings=self._settings,
            interrupted=interrupted,
        )


def _sleep_until(deadline: float) -> None:
    remaining = deadline - time.monotonic()
    if remaining > 0:
        time.sleep(remaining)


def _integrate_energy_wh(samples: list[Sample]) -> float:
    """Энергия за сессию методом трапеций по фактическим меткам времени."""
    previous_elapsed = 0.0
    previous_watts = samples[0].watts
    watt_seconds = 0.0
    for sample in samples:
        span = sample.elapsed - previous_elapsed
        if span > 0.0:
            watt_seconds += (previous_watts + sample.watts) / 2.0 * span
        previous_elapsed = sample.elapsed
        previous_watts = sample.watts
    return watt_seconds / const.SECONDS_PER_HOUR


def percentile(values: list[float], rank: float) -> float:
    """Перцентиль с линейной интерполяцией между соседними значениями."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * rank / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _dominant_accuracy(samples: list[Sample]) -> Accuracy:
    """Худшая из встретившихся оценок точности: результат не лучше слабого звена."""
    order = (Accuracy.MEASURED, Accuracy.HIGH, Accuracy.MEDIUM, Accuracy.MODELED)
    worst = Accuracy.MEASURED
    for sample in samples:
        if order.index(sample.accuracy) > order.index(worst):
            worst = sample.accuracy
    return worst
