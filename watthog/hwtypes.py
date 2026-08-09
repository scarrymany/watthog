"""Типы данных, общие для платформенных источников телеметрии."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BatteryState:
    """Состояние батареи.

    ``discharge_watts`` заполняется только при разряде и только если контроллер
    батареи сообщает мгновенную мощность. Это прямое измерение потребления всей
    системы, самый точный источник из доступных без прав администратора.
    """

    present: bool
    on_ac_power: bool
    discharging: bool
    charge_percent: float | None
    discharge_watts: float | None


@dataclass(frozen=True)
class SensorReading:
    """Показание аппаратного датчика мощности с пометкой источника."""

    watts: float
    source: str
