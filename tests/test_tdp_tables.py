from watthog.tdp_tables import (
    MATCH_SOURCE_ESTIMATE,
    MATCH_SOURCE_TABLE,
    MOBILE_GPU_POWER_FACTOR,
    CpuClass,
    classify_cpu,
    is_integrated_gpu,
    is_mobile_cpu,
    is_virtual_gpu,
    lookup_cpu_power,
    lookup_gpu_power,
    normalize_name,
)


def test_normalize_name_strips_vendor_noise():
    assert normalize_name("Intel(R) Core(TM) i9-14900K CPU @ 3.20GHz") == "intel core i9-14900k"
    assert normalize_name("AMD Ryzen 7 7800X3D 8-Core Processor") == "amd ryzen 7 7800x3d"


def test_lookup_cpu_power_finds_exact_model():
    peak, idle, source = lookup_cpu_power("AMD Ryzen 7 7800X3D 8-Core Processor", 8)
    assert (peak, idle, source) == (88.0, 24.0, MATCH_SOURCE_TABLE)


def test_lookup_cpu_power_prefers_longest_matching_pattern():
    # "ryzen 9 7950x" - префикс "ryzen 9 7950x3d", более точный образец должен выиграть.
    assert lookup_cpu_power("AMD Ryzen 9 7950X3D 16-Core Processor", 16)[0] == 145.0
    assert lookup_cpu_power("AMD Ryzen 9 7950X 16-Core Processor", 16)[0] == 200.0
    assert lookup_cpu_power("Intel(R) Core(TM) i9-14900KS", 24)[0] == 253.0


def test_lookup_cpu_power_falls_back_to_class_estimate():
    peak, idle, source = lookup_cpu_power("Totally Unknown CPU 9999X", 12)
    assert source == MATCH_SOURCE_ESTIMATE
    assert 65.0 <= peak <= 260.0
    assert 0.0 < idle < peak


def test_lookup_cpu_power_estimate_scales_with_core_count():
    small = lookup_cpu_power("Unknown Chip 1234K", 4)[0]
    large = lookup_cpu_power("Unknown Chip 1234K", 16)[0]
    assert large > small


def test_classify_cpu_recognizes_segments():
    assert classify_cpu("Intel(R) Core(TM) i7-13700H") is CpuClass.MOBILE_H
    assert classify_cpu("Intel(R) Core(TM) i9-13980HX") is CpuClass.MOBILE_HX
    assert classify_cpu("Intel(R) Core(TM) i7-1165G7") is CpuClass.MOBILE_U
    assert classify_cpu("AMD Ryzen 5 5500U") is CpuClass.MOBILE_U
    assert classify_cpu("AMD Ryzen 7 7800X3D") is CpuClass.DESKTOP_UNLOCKED
    assert classify_cpu("Intel(R) Core(TM) i5-12400F") is CpuClass.DESKTOP_STANDARD
    assert classify_cpu("Intel(R) Core(TM) i7-12700T") is CpuClass.DESKTOP_LOW_POWER


def test_is_mobile_cpu_matches_mobile_classes():
    assert is_mobile_cpu(CpuClass.MOBILE_U)
    assert not is_mobile_cpu(CpuClass.DESKTOP_STANDARD)


def test_lookup_gpu_power_finds_exact_model_and_longest_match():
    assert lookup_gpu_power("NVIDIA GeForce RTX 5070")[0] == 250.0
    assert lookup_gpu_power("NVIDIA GeForce RTX 5070 Ti")[0] == 300.0
    assert lookup_gpu_power("NVIDIA GeForce RTX 4070 Ti SUPER")[0] == 285.0
    assert lookup_gpu_power("AMD Radeon RX 7900 XTX")[0] == 355.0


def test_lookup_gpu_power_derates_mobile_variants():
    desktop = lookup_gpu_power("NVIDIA GeForce RTX 4060")[0]
    mobile = lookup_gpu_power("NVIDIA GeForce RTX 4060 Laptop GPU")[0]
    assert mobile == desktop * MOBILE_GPU_POWER_FACTOR


def test_integrated_and_virtual_adapters_are_recognized():
    assert is_integrated_gpu("AMD Radeon(TM) Graphics")
    assert is_integrated_gpu("Intel(R) UHD Graphics 770")
    assert is_integrated_gpu("AMD Radeon 780M Graphics")
    assert not is_integrated_gpu("NVIDIA GeForce RTX 5070")

    assert is_virtual_gpu("Microsoft Basic Display Adapter")
    assert is_virtual_gpu("Parsec Virtual Display Adapter")
    assert not is_virtual_gpu("Intel(R) Arc(TM) A770 Graphics")


def test_discrete_arc_is_not_treated_as_integrated():
    assert not is_integrated_gpu("Intel(R) Arc(TM) A770 Graphics")
    assert is_integrated_gpu("Intel(R) Arc(TM) Graphics")
