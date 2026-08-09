from watthog.winapi import peak_gpu_utilization


def instance(pid: int, luid: str, engine: str) -> str:
    return f"pid_{pid}_luid_0x00000000_{luid}_phys_0_eng_0_engtype_{engine}"


def test_no_counters_means_idle():
    assert peak_gpu_utilization({}) == 0.0


def test_processes_on_the_same_engine_are_summed():
    counters = {
        instance(100, "0x1111", "3D"): 40.0,
        instance(200, "0x1111", "3D"): 35.0,
    }
    assert peak_gpu_utilization(counters) == 0.75


def test_different_engine_types_are_not_summed():
    # 3D, копирование и видеодекодер работают параллельно: их сумма превысила бы
    # сто процентов при неполной загрузке чипа, поэтому берётся максимум.
    counters = {
        instance(100, "0x1111", "3D"): 60.0,
        instance(100, "0x1111", "Copy"): 50.0,
        instance(100, "0x1111", "VideoDecode"): 45.0,
    }
    assert peak_gpu_utilization(counters) == 0.60


def test_busiest_adapter_wins():
    counters = {
        instance(100, "0x1111", "3D"): 20.0,
        instance(100, "0x2222", "3D"): 85.0,
    }
    assert peak_gpu_utilization(counters) == 0.85


def test_result_is_capped_at_one():
    counters = {instance(100, "0x1111", "3D"): 140.0}
    assert peak_gpu_utilization(counters) == 1.0


def test_zero_values_are_skipped():
    counters = {instance(index, "0x1111", "3D"): 0.0 for index in range(50)}
    assert peak_gpu_utilization(counters) == 0.0


def test_unparsable_instance_names_do_not_crash():
    assert peak_gpu_utilization({"weird name": 30.0}) == 0.30
