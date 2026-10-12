import asyncio
import json
from pathlib import Path

import pytest

from ai_runtime.app.capability.diagnostics import AlgorithmExecutionError
from ai_runtime.sdk import build_package, init_project, main, read_json, run_fixture


def project(tmp_path):
    directory = tmp_path / "hello"
    init_project(directory, "hello-person")
    return directory


def test_quickstart_uses_real_worker_and_deterministic_package(tmp_path, capsys):
    directory = project(tmp_path)
    assert build_package(directory) == build_package(directory)
    assert main(["check", str(directory)]) == 0
    assert (
        main(
            [
                "run",
                str(directory),
                "--fixture",
                str(directory / "fixtures/frame.json"),
                "--expect",
                str(directory / "fixtures/expected.json"),
            ]
        )
        == 0
    )
    assert '"source": "SDK_FIXTURE"' in capsys.readouterr().out
    assert main(["pack", str(directory), "--output", str(tmp_path / "hello.zip")]) == 0
    assert (tmp_path / "hello.zip").read_bytes() == build_package(directory)
    # Avoid silently replacing developer files or releases.
    assert main(["init", str(directory)]) == 2
    assert main(["pack", str(directory), "--output", str(tmp_path / "hello.zip")]) == 2


def test_worker_supports_default_relative_runtime_data_root(tmp_path, monkeypatch):
    from PIL import Image

    from ai_runtime.app.capability.package_runner import PackageRunner
    from ai_runtime.app.capability.packages import AlgorithmPackageStore
    from ai_runtime.app.task.contracts import TaskInferenceParameters
    from ai_runtime.sdk import FixturePool

    directory = project(tmp_path)
    fixture = read_json(directory / "fixtures/frame.json")
    monkeypatch.chdir(tmp_path)
    root = Path("var/runtime-data")
    descriptor = AlgorithmPackageStore(root).install(build_package(directory))
    bindings = {"person": 1}

    async def scenario():
        runner = PackageRunner(
            root, descriptor, {"confidence": 0.5}, bindings, FixturePool(fixture, bindings)
        )
        try:
            await runner.start()
            result = await runner.run(
                [], Image.new("RGB", (640, 360)), 1000, TaskInferenceParameters(schemaVersion="1.0")
            )
            assert len(result) == 1
            assert result[0].class_name == "person"
        finally:
            await runner.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "source,stage,line",
    [
        ("raise RuntimeError('rtsp://admin:secret@camera/stream')", "IMPORT", 1),
        (
            "class Algorithm:\n def __init__(self):\n  raise ValueError('token=secret')\n",
            "INITIALIZE",
            3,
        ),
        (
            "class Algorithm:\n def process(self, f, sdk):\n  raise KeyError('/private/token')\n",
            "PROCESS",
            3,
        ),
        ("class Algorithm:\n invalid syntax !!\n", "IMPORT", 2),
    ],
)
def test_error_stage_location_and_redaction(tmp_path, source, stage, line):
    directory = project(tmp_path)
    (directory / "processor.py").write_text(source)
    with pytest.raises(AlgorithmExecutionError) as failure:
        asyncio.run(
            run_fixture(build_package(directory), read_json(directory / "fixtures/frame.json"))
        )
    diagnostic = failure.value.diagnostic
    assert diagnostic["stage"] == stage
    assert diagnostic["frames"][-1]["file"] == "processor.py"
    assert diagnostic["frames"][-1]["line"] == line
    assert len(diagnostic["packageSha256"]) == 64
    assert diagnostic["diagnosticId"]
    encoded = json.dumps(diagnostic)
    assert "secret" not in encoded
    assert str(tmp_path) not in encoded
    assert "rtsp://" not in encoded


@pytest.mark.parametrize(
    "body,code",
    [
        ("while True: pass", "ALGORITHM_TIMEOUT"),
        ("sdk.infer('foreign')", "ALGORITHM_SDK_FAILED"),
        ("return {'objects': [42]}", "ALGORITHM_OUTPUT_FAILED"),
        ("return {'objects': [float('nan')]}", "ALGORITHM_OUTPUT_FAILED"),
    ],
)
def test_host_errors_and_cli_exit_code(tmp_path, capsys, body, code):
    directory = project(tmp_path)
    manifest = read_json(directory / "algorithm.json")
    manifest["timeoutMillis"] = 100
    (directory / "algorithm.json").write_text(json.dumps(manifest))
    (directory / "processor.py").write_text(
        f"class Algorithm:\n def process(self, f, sdk):\n  {body}\n"
    )
    report = tmp_path / "result.json"
    assert (
        main(
            [
                "run",
                str(directory),
                "--fixture",
                str(directory / "fixtures/frame.json"),
                "--output",
                str(report),
            ]
        )
        == 1
    )
    assert read_json(report)["error"]["code"] == code
    assert read_json(report)["error"]["timestampMillis"] == 1000
    assert code in capsys.readouterr().err


def test_golden_mismatch_and_symlink_rejected(tmp_path):
    directory = project(tmp_path)
    expected = directory / "fixtures/expected.json"
    expected.write_text('{"objects": []}')
    assert (
        main(
            [
                "run",
                str(directory),
                "--fixture",
                str(directory / "fixtures/frame.json"),
                "--expect",
                str(expected),
            ]
        )
        == 1
    )
    (directory / "linked.py").symlink_to(tmp_path / "outside.py")
    with pytest.raises(ValueError, match="符号链接"):
        build_package(directory)


def test_runtime_task_reports_same_diagnostic_and_releases_worker(tmp_path):
    from uuid import uuid4

    from test_task_manager import FakeModelPool, FakeSharedStream, request

    from ai_runtime.app.capability.packages import AlgorithmPackageStore
    from ai_runtime.app.core.config import RuntimeSettings
    from ai_runtime.app.task.manager import TaskManager

    directory = project(tmp_path)
    (directory / "processor.py").write_text("raise RuntimeError('private token')")
    descriptor = AlgorithmPackageStore(tmp_path).install(build_package(directory))

    async def scenario():
        settings = RuntimeSettings(
            api_key="a-secure-runtime-key-for-tests", runtime_data_root=tmp_path
        )
        manager = TaskManager(settings, FakeModelPool(), FakeSharedStream)
        config = request(501, str(uuid4()))
        config.pipeline = {"schemaVersion": "1.0", "nodes": [], "algorithmPackage": descriptor}
        config.model_bindings = {"person": config.model_version_id}
        config.parameters.algorithm = {"confidence": 0.5}
        try:
            await manager.start_task(config)
            runner = manager._tasks[501]
            await asyncio.wait_for(runner._task, 5)
            status = runner.snapshot()
            assert status.status == "FAILED"
            assert status.error_code == "ALGORITHM_IMPORT_FAILED"
            diagnostic = status.metrics["algorithmError"]
            assert diagnostic["diagnosticId"] == status.diagnostic_id
            assert diagnostic["taskId"] == 501
            assert diagnostic["runId"] == config.run_id
            assert diagnostic["configVersion"] == config.config_version
            assert runner._package.process is None
            assert "private token" not in json.dumps(status.model_dump())
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_process_launch_failure_is_sanitized(tmp_path, monkeypatch):
    directory = project(tmp_path)

    async def fail_launch(*_args, **_kwargs):
        raise OSError("/private/host-secret")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fail_launch)
    with pytest.raises(AlgorithmExecutionError) as failure:
        asyncio.run(
            run_fixture(build_package(directory), read_json(directory / "fixtures/frame.json"))
        )
    assert failure.value.diagnostic["code"] == "ALGORITHM_IMPORT_FAILED"
    assert "host-secret" not in json.dumps(failure.value.diagnostic)


def test_legacy_worker_error_remains_supported(tmp_path):
    directory = project(tmp_path)
    (directory / "processor.py").write_text(
        "import os\nclass Algorithm:\n def process(self, f, sdk):\n"
        '  os.write(1, b\'{"error":"LegacyFailure"}\\n\')\n'
        '  return {"objects": []}\n'
    )
    with pytest.raises(AlgorithmExecutionError) as failure:
        asyncio.run(
            run_fixture(build_package(directory), read_json(directory / "fixtures/frame.json"))
        )
    assert failure.value.diagnostic["code"] == "ALGORITHM_PROCESS_FAILED"
    assert failure.value.diagnostic["exceptionType"] == "LegacyFailure"
