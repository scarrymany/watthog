import pytest

from watthog import constants as const
from watthog.config import Settings
from watthog.hwtypes import BatteryState
from watthog.inventory import CpuInfo, FormFactor, GpuInfo, GpuKind, HardwareProfile
from watthog.meter import Accuracy, PowerBreakdown, PowerMeter, _interpolate, average_breakdown
from watthog.tdp_tables import CpuClass
from watthog.telemetry import GpuTelemetry, Telemetry

CPU_PEAK = 100.0
CPU_IDLE = 20.0
GPU_PEAK = 250.0
GPU_IDLE = 16.0


def make_profile(form_factor=FormFactor.DESKTOP, with_gpu=True, gpu_telemetry=True):
    gpus = ()
    if with_gpu:
        gpus = (
            GpuInfo(
                name="Test GPU",
                kind=GpuKind.DISCRETE,
                peak_watts=GPU_PEAK,
                idle_watts=GPU_IDLE,
                power_source="справочник",
                nvml_index=0 if gpu_telemetry else None,
            ),
        )
    return HardwareProfile(
        form_factor=form_factor,
        cpu=CpuInfo("Test CPU", 8, 16, CpuClass.DESKTOP_UNLOCKED, CPU_PEAK, CPU_IDLE, "справочник"),
        gpus=gpus,
        ram_gib=32.0,
        disk_count=2,
        has_battery=form_factor is FormFactor.LAPTOP,
        os_description="Test OS",
    )


def make_telemetry(**overrides):
    defaults = {
        "cpu_load": 0.0,
        "cpu_freq_ratio": const.CPU_REFERENCE_FREQ_RATIO,
        "cpu_power_watts": None,
        "platform_power_watts": None,
        "gpus": (),
        "disk_bytes_per_second": 0.0,
        "battery": None,
    }
    return Telemetry(**{**defaults, **overrides})


def test_breakdown_totals_include_conversion_loss():
    breakdown = PowerBreakdown(cpu=50.0, gpu=100.0, ram=8.0, storage=2.0, platform=25.0, conversion_loss=20.0)
    assert breakdown.total_dc == 185.0
    assert breakdown.total_ac == 205.0


def test_breakdown_addition_and_scaling():
    one = PowerBreakdown(cpu=10.0, gpu=20.0)
    two = PowerBreakdown(cpu=30.0, gpu=40.0)
    assert (one + two).cpu == 40.0
    assert (one + two).gpu == 60.0
    assert two.scaled(0.5).gpu == 20.0


def test_average_breakdown_of_empty_list_is_zero():
    assert average_breakdown([]).total_ac == 0.0


def test_average_breakdown_averages_each_component():
    average = average_breakdown([PowerBreakdown(cpu=10.0), PowerBreakdown(cpu=30.0)])
    assert average.cpu == 20.0


def test_idle_cpu_model_lands_near_idle_power():
    meter = PowerMeter(make_profile(with_gpu=False), Settings())
    breakdown = meter.measure(make_telemetry(cpu_load=0.0))
    assert breakdown.cpu == pytest.approx(CPU_IDLE / const.VRM_EFFICIENCY)


def test_full_load_cpu_model_lands_near_peak_power():
    meter = PowerMeter(make_profile(with_gpu=False), Settings())
    breakdown = meter.measure(make_telemetry(cpu_load=1.0))
    assert breakdown.cpu == pytest.approx(CPU_PEAK / const.VRM_EFFICIENCY)


def test_cpu_model_is_monotonic_in_load():
    meter = PowerMeter(make_profile(with_gpu=False), Settings())
    values = [meter.measure(make_telemetry(cpu_load=load / 10)).cpu for load in range(11)]
    assert values == sorted(values)


def test_higher_clock_raises_modelled_cpu_power():
    meter = PowerMeter(make_profile(with_gpu=False), Settings())
    low = meter.measure(make_telemetry(cpu_load=0.5, cpu_freq_ratio=0.6)).cpu
    high = meter.measure(make_telemetry(cpu_load=0.5, cpu_freq_ratio=1.3)).cpu
    assert high > low


def test_real_cpu_sensor_overrides_the_model():
    meter = PowerMeter(make_profile(with_gpu=False), Settings())
    breakdown = meter.measure(make_telemetry(cpu_load=1.0, cpu_power_watts=42.0))
    assert breakdown.cpu == pytest.approx(42.0 / const.VRM_EFFICIENCY)


def test_gpu_sensor_value_is_used_as_is():
    meter = PowerMeter(make_profile(), Settings())
    breakdown = meter.measure(make_telemetry(gpus=(GpuTelemetry(0, 123.4, 0.7),)))
    assert breakdown.gpu == pytest.approx(123.4)


def test_gpu_without_sensor_is_modelled_from_utilization():
    meter = PowerMeter(make_profile(gpu_telemetry=False), Settings())
    idle = meter.measure(make_telemetry(gpus=(GpuTelemetry(0, None, 0.0),))).gpu
    busy = meter.measure(make_telemetry(gpus=(GpuTelemetry(0, None, 1.0),))).gpu
    assert idle == pytest.approx(GPU_IDLE)
    assert busy == pytest.approx(GPU_PEAK)


def test_gpu_without_any_reading_falls_back_to_idle():
    meter = PowerMeter(make_profile(gpu_telemetry=False), Settings())
    assert meter.measure(make_telemetry()).gpu == pytest.approx(GPU_IDLE)


def test_integrated_gpu_adds_no_power():
    profile = make_profile(with_gpu=False)
    integrated = GpuInfo("iGPU", GpuKind.INTEGRATED, 0.0, 0.0, "-")
    profile = HardwareProfile(
        form_factor=profile.form_factor,
        cpu=profile.cpu,
        gpus=(integrated,),
        ram_gib=profile.ram_gib,
        disk_count=profile.disk_count,
        has_battery=profile.has_battery,
        os_description=profile.os_description,
    )
    assert PowerMeter(profile, Settings()).measure(make_telemetry()).gpu == 0.0


def test_disk_power_grows_with_throughput():
    meter = PowerMeter(make_profile(with_gpu=False), Settings())
    quiet = meter.measure(make_telemetry()).storage
    busy = meter.measure(
        make_telemetry(disk_bytes_per_second=const.DISK_SATURATION_BYTES_PER_SECOND)
    ).storage
    assert busy == pytest.approx(quiet + const.DISK_ACTIVE_WATTS_DESKTOP)


def test_measured_battery_draw_calibrates_the_breakdown():
    meter = PowerMeter(make_profile(form_factor=FormFactor.LAPTOP, with_gpu=False), Settings())
    battery = BatteryState(
        present=True, on_ac_power=False, discharging=True, charge_percent=80.0, discharge_watts=25.0
    )
    breakdown = meter.measure(make_telemetry(cpu_load=0.5, battery=battery))
    assert breakdown.total_dc == pytest.approx(25.0)


def test_extra_devices_are_added_after_calibration():
    settings = Settings(extra_devices_watts=30.0)
    meter = PowerMeter(make_profile(form_factor=FormFactor.LAPTOP, with_gpu=False), settings)
    battery = BatteryState(
        present=True, on_ac_power=False, discharging=True, charge_percent=80.0, discharge_watts=25.0
    )
    breakdown = meter.measure(make_telemetry(battery=battery))
    assert breakdown.total_dc == pytest.approx(55.0)


def test_conversion_loss_matches_configured_efficiency():
    settings = Settings(psu_peak_efficiency=0.90, psu_rated_watts=650)
    meter = PowerMeter(make_profile(with_gpu=False), settings)
    breakdown = meter.measure(make_telemetry(cpu_load=0.5))
    efficiency = breakdown.total_dc / breakdown.total_ac
    assert 0.75 <= efficiency <= 0.90


def test_laptop_uses_flat_adapter_efficiency():
    meter = PowerMeter(make_profile(form_factor=FormFactor.LAPTOP, with_gpu=False), Settings())
    breakdown = meter.measure(make_telemetry(cpu_load=0.3))
    assert breakdown.total_dc / breakdown.total_ac == pytest.approx(const.LAPTOP_ADAPTER_EFFICIENCY)


def test_accuracy_reflects_available_sensors():
    meter = PowerMeter(make_profile(), Settings())
    assert meter.accuracy(make_telemetry(gpus=(GpuTelemetry(0, 100.0, 0.5),))) is Accuracy.MEDIUM
    assert (
        meter.accuracy(make_telemetry(cpu_power_watts=50.0, gpus=(GpuTelemetry(0, 100.0, 0.5),)))
        is Accuracy.HIGH
    )
    assert meter.accuracy(make_telemetry()) is Accuracy.MODELED

    battery = BatteryState(True, False, True, 50.0, 30.0)
    assert meter.accuracy(make_telemetry(battery=battery)) is Accuracy.MEASURED


def test_interpolate_handles_edges_and_midpoints():
    curve = ((0.0, 0.0), (1.0, 10.0), (2.0, 20.0))
    assert _interpolate(curve, -5.0) == 0.0
    assert _interpolate(curve, 0.5) == 5.0
    assert _interpolate(curve, 1.5) == 15.0
    assert _interpolate(curve, 99.0) == 20.0
