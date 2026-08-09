"""Снимки интерфейса в SVG для документации.

Скрипт проводит настоящий короткий замер на текущей машине и выгружает три
экрана: живую панель, итоговый отчёт и список найденного железа.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from watthog.config import Settings  # noqa: E402
from watthog.meter import PowerMeter  # noqa: E402
from watthog.session import MeasurementSession  # noqa: E402
from watthog.telemetry import TelemetryReader  # noqa: E402
from watthog.ui.dashboard import LiveDashboard  # noqa: E402
from watthog.ui.report import hardware_panel, render_result  # noqa: E402
from watthog.ui.theme import build_console  # noqa: E402

CONSOLE_WIDTH = 104
DASHBOARD_HEIGHT = 32
CAPTURE_DURATION_SECONDS = 30.0


def main() -> int:
    output = Path(__file__).resolve().parents[1] / "docs"
    output.mkdir(parents=True, exist_ok=True)
    settings = Settings(duration_seconds=int(CAPTURE_DURATION_SECONDS), tariff_per_kwh=6.5, save_reports=False)

    with TelemetryReader(settings) as reader:
        meter = PowerMeter(reader.profile, settings)
        session = MeasurementSession(reader, meter, settings)

        dashboard_console = build_console(
            force_terminal=True, record=True, width=CONSOLE_WIDTH, height=DASHBOARD_HEIGHT
        )
        dashboard = LiveDashboard(dashboard_console, reader.profile, settings, CAPTURE_DURATION_SECONDS)
        print(f"замер {CAPTURE_DURATION_SECONDS:.0f} с...")
        result = session.run(CAPTURE_DURATION_SECONDS, dashboard.update)

        dashboard_console.print(dashboard.renderable())
        _export(dashboard_console, output / "dashboard.svg", "WattHog - живая панель")

        report_console = build_console(force_terminal=True, record=True, width=CONSOLE_WIDTH)
        render_result(report_console, result)
        _export(report_console, output / "report.svg", "WattHog - итоговый отчёт")

        info_console = build_console(force_terminal=True, record=True, width=CONSOLE_WIDTH)
        info_console.print(hardware_panel(reader.profile, reader.sources))
        _export(info_console, output / "hardware.svg", "WattHog - железо и источники")
    return 0


def _export(console, path: Path, title: str) -> None:
    path.write_text(console.export_svg(title=title), encoding="utf-8")
    print(f"{path.name}: {path.stat().st_size} байт")


if __name__ == "__main__":
    sys.exit(main())
