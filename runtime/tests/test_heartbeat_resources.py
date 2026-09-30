from pathlib import Path

from edge_agent.app.heartbeat.resources import (
    collect_accelerator_usage,
    collect_disk_cleanup_status,
)


def test_collects_single_core_rknpu_debugfs_load(tmp_path: Path) -> None:
    debugfs_root = tmp_path / "debug"
    load = debugfs_root / "rknpu" / "load"
    load.parent.mkdir(parents=True)
    load.write_text("NPU load: 37%\n", encoding="utf-8")

    gpu, npu = collect_accelerator_usage(tmp_path / "devfreq", debugfs_root)

    assert gpu is None
    assert npu == 37.0


def test_averages_multi_core_rknpu_load(tmp_path: Path) -> None:
    debugfs_root = tmp_path / "debug"
    load = debugfs_root / "rknpu" / "load"
    load.parent.mkdir(parents=True)
    load.write_text("Core0: 10%, Core1: 20%, Core2: 30%\n", encoding="utf-8")

    _, npu = collect_accelerator_usage(tmp_path / "devfreq", debugfs_root)

    assert npu == 20.0


def test_falls_back_to_rockchip_devfreq_load_files(tmp_path: Path) -> None:
    devfreq_root = tmp_path / "devfreq"
    gpu_load = devfreq_root / "fde60000.gpu" / "load"
    npu_load = devfreq_root / "fde40000.npu" / "load"
    gpu_load.parent.mkdir(parents=True)
    npu_load.parent.mkdir(parents=True)
    gpu_load.write_text("22@800000000Hz\n", encoding="utf-8")
    npu_load.write_text("46@600000000Hz\n", encoding="utf-8")

    gpu, npu = collect_accelerator_usage(devfreq_root, tmp_path / "missing-debug")

    assert gpu == 22.0
    assert npu == 46.0


def test_unavailable_or_malformed_metrics_remain_unreported(tmp_path: Path) -> None:
    devfreq_root = tmp_path / "devfreq"
    load = devfreq_root / "fde40000.npu" / "load"
    load.parent.mkdir(parents=True)
    load.write_text("not available\n", encoding="utf-8")

    gpu, npu = collect_accelerator_usage(devfreq_root, tmp_path / "missing-debug")

    assert gpu is None
    assert npu is None


def test_invalid_metrics_are_rejected_and_driver_spikes_are_bounded(tmp_path: Path) -> None:
    debugfs_root = tmp_path / "debug"
    load = debugfs_root / "rknpu" / "load"
    load.parent.mkdir(parents=True)
    load.write_text("NPU load: -5%\n", encoding="utf-8")
    assert collect_accelerator_usage(tmp_path / "devfreq", debugfs_root)[1] is None

    load.write_text("NPU load: 20000%\n", encoding="utf-8")
    assert collect_accelerator_usage(tmp_path / "devfreq", debugfs_root)[1] == 100.0


def test_reads_bounded_disk_cleanup_receipt(tmp_path: Path) -> None:
    receipt = tmp_path / "last-run.env"
    receipt.write_text(
        "STATUS=RECLAIMED\n"
        "LAST_RUN_EPOCH_SECONDS=1789084800\n"
        "BEFORE_PERCENT=86\n"
        "AFTER_PERCENT=72\n"
        "FREED_BYTES=2147483648\n"
        "ACTIONS=pip_cache,old_snapshot,journal\n",
        encoding="utf-8",
    )

    assert collect_disk_cleanup_status(receipt) == {
        "diskCleanupStatus": "RECLAIMED",
        "diskCleanupLastRunEpochSeconds": 1789084800,
        "diskCleanupBeforePercent": 86,
        "diskCleanupAfterPercent": 72,
        "diskCleanupFreedBytes": 2147483648,
        "diskCleanupActions": "pip_cache,old_snapshot,journal",
    }


def test_rejects_tampered_disk_cleanup_receipt(tmp_path: Path) -> None:
    receipt = tmp_path / "last-run.env"
    receipt.write_text(
        "STATUS=RECLAIMED\nLAST_RUN_EPOCH_SECONDS=1\nBEFORE_PERCENT=101\n"
        "AFTER_PERCENT=72\nFREED_BYTES=1\nACTIONS=../../events\n",
        encoding="utf-8",
    )

    assert set(collect_disk_cleanup_status(receipt).values()) == {None}
