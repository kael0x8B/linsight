import asyncio
import io
import json
import zipfile

import pytest
from PIL import Image

from ai_runtime.app.capability.package_runner import PackageRunner
from ai_runtime.app.capability.packages import AlgorithmPackageStore, inspect_package
from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.task.contracts import TaskInferenceParameters


def package(
    code=(
        "class Algorithm:\n def process(self, frame, sdk):\n"
        "  return {'objects': frame['objects']}\n"
    ),
    **changes,
):
    manifest = {
        "schemaVersion": "1.0",
        "sdkVersion": "1.0",
        "code": "external-zone",
        "name": "外部区域算法",
        "version": "1.0.0",
        "entrypoint": "processor.py",
        "models": [{"slot": "person", "labels": ["person"]}],
        "parameterSchema": {
            "type": "object",
            "properties": {"limit": {"type": "number", "minimum": 0, "maximum": 1}},
            "required": ["limit"],
            "additionalProperties": False,
        },
        "defaultParameters": {"limit": 0.4},
        **changes,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("algorithm.json", json.dumps(manifest))
        archive.writestr("processor.py", code)
    return output.getvalue()


def test_install_is_immutable_and_survives_store_restart(tmp_path):
    content = package("raise RuntimeError('must not execute during install')")
    installed = AlgorithmPackageStore(tmp_path).install(content)
    assert AlgorithmPackageStore(tmp_path).install(content) == installed
    assert AlgorithmPackageStore(tmp_path).list() == [installed]
    assert len(list((tmp_path / "algorithms").iterdir())) == 1


def test_reject_hash_sdk_traversal_and_modified_code(tmp_path):
    with pytest.raises(ValueError, match="SHA256"):
        AlgorithmPackageStore(tmp_path).install(package(), "0" * 64)
    with pytest.raises(ValueError, match="SDK"):
        inspect_package(package(sdkVersion="99.0"))
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("../outside.py", "pass")
    with pytest.raises(ValueError, match="路径"):
        inspect_package(data.getvalue())
    store = AlgorithmPackageStore(tmp_path)
    installed = store.install(package())
    path, _ = store.resolve(installed["sha256"])
    (path / "processor.py").write_text("pass")
    with pytest.raises(ValueError, match="变化"):
        store.resolve(installed["sha256"])


def test_schema_parameters_not_silently_discarded(tmp_path):
    installed = AlgorithmPackageStore(tmp_path).install(package())
    parameters = TaskInferenceParameters(schemaVersion="1.0", algorithm={"limit": 0.75})
    assert parameters.model_dump()["algorithm"] == {"limit": 0.75}
    for values in ({}, {"limit": 4}, {"limit": 0.4, "secret": "unexpected"}):
        with pytest.raises(ValueError):
            PackageRunner(tmp_path, installed, values, {"person": 1}, None)


def test_new_supplier_logic_runs_without_registry_changes(tmp_path):
    content = package("""class Algorithm:
 def process(self, frame, sdk):
  objects = []
  for obj in frame['objects']:
   if obj['bbox']['x'] >= frame['parameters']['limit']:
    objects.append({**obj, 'attributes': {'eventCandidate': True, 'label': '外部新规则命中'}})
  return {'objects': objects}
""")
    descriptor = AlgorithmPackageStore(tmp_path).install(content)

    async def run():
        runner = PackageRunner(tmp_path, descriptor, {"limit": 0.4}, {"person": 1}, None)
        await runner.start()
        try:
            objects = [
                DetectionObject(
                    **{
                        "class": "person",
                        "confidence": 0.9,
                        "bbox": {"x": x, "y": 0.1, "width": 0.1, "height": 0.2},
                    }
                )
                for x in [0.1, 0.5]
            ]
            result = await runner.run(
                objects,
                Image.new("RGB", (64, 64)),
                1000,
                TaskInferenceParameters(schemaVersion="1.0"),
            )
            assert len(result) == 1
            assert result[0].attributes["eventCandidate"] is True
            assert result[0].bbox.x == 0.5
        finally:
            process = runner.process
            await runner.close()
            assert process.returncode is not None

    asyncio.run(run())


@pytest.mark.parametrize(
    "code,pattern",
    [
        ("class Algorithm:\n def process(self, f, sdk):\n  while True: pass\n", "timeout"),
        ("class Algorithm:\n def process(self, f, sdk):\n  sdk.infer('foreign')\n", "未授权"),
        (
            "class Algorithm:\n def process(self, f, sdk):\n  return {'objects': [42]}\n",
            "validation",
        ),
    ],
)
def test_bad_supplier_does_not_keep_worker_alive(tmp_path, code, pattern):
    descriptor = AlgorithmPackageStore(tmp_path).install(package(code, timeoutMillis=100))

    async def run():
        runner = PackageRunner(tmp_path, descriptor, {"limit": 0.4}, {"person": 1}, None)
        await runner.start()
        process = runner.process
        with pytest.raises((ValueError, TimeoutError)):
            await runner.run(
                [], Image.new("RGB", (64, 64)), 1000, TaskInferenceParameters(schemaVersion="1.0")
            )
        assert runner.process is None
        assert process.returncode is not None

    asyncio.run(run())


def test_package_task_survives_local_edit_and_offline_restart(tmp_path):
    from unittest.mock import patch
    from uuid import uuid4

    from test_task_manager import FakeModelPool, FakeSharedStream, request

    from ai_runtime.app.core.config import RuntimeSettings
    from ai_runtime.app.gateway.service import GatewayChange, GatewayService
    from ai_runtime.app.task.manager import TaskManager

    async def scenario():
        installed = AlgorithmPackageStore(tmp_path).install(package())
        settings = RuntimeSettings(api_key="package-test-runtime-key", runtime_data_root=tmp_path)
        pool = FakeModelPool()
        config = request(501, str(uuid4()))
        config.pipeline = {
            "schemaVersion": "1.0",
            "nodes": [{"id": "person", "type": "DETECTOR", "capabilityKey": "model.person"}],
            "edges": [],
            "algorithmPackage": installed,
        }
        config.parameters.algorithm = {"limit": 0.4}
        config.model_bindings = {"person": config.model_version_id}
        manager = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, manager)
        models = [
            {
                "modelVersionId": config.model_version_id,
                "artifactFormat": "ONNX",
                "runtimeManifest": {"decoder": {"labels": ["person"]}},
            }
        ]
        with patch.object(gateway.models, "summaries", return_value=models):
            await gateway.platform_start(config, 0)
            change = GatewayChange(
                taskId=501,
                expectedRevision=1,
                requestId=str(uuid4()),
                configuration={
                    "parameters": {"schemaVersion": "1.0", "algorithm": {"limit": 0.75}}
                },
            )
            result = await gateway.change(change)
            assert result["config"]["parameters"]["algorithm"] == {"limit": 0.75}
            assert (await gateway.change(change))["revision"] == 2
            assert "algorithmResources" not in result["config"]
        await gateway.close()
        await manager.close()
        manager = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, manager)
        with patch.object(gateway.models, "summaries", return_value=models):
            await gateway.reconcile()
            assert gateway.status(501).status == "RUNNING"
            assert manager._tasks[501].request.parameters.algorithm == {"limit": 0.75}
        await gateway.close()
        await manager.close()

    asyncio.run(scenario())


def test_sdk_cropped_inference_and_person_resource_redaction(tmp_path):
    from unittest.mock import AsyncMock

    from ai_runtime.app.gateway.service import _public_config
    from ai_runtime.app.model.contracts import ModelTestResult

    code = """class Algorithm:
 def process(self, frame, sdk):
  assert all('path' not in p and 'url' not in p for p in frame['resources'].get('people', []))
  result = sdk.infer('person', {'x': 0, 'y': 0, 'width': .5, 'height': .5})
  return {'objects': result['objects']}
"""

    async def scenario():
        installed = AlgorithmPackageStore(tmp_path).install(package(code))
        pool = AsyncMock()
        pool.test.return_value = ModelTestResult(
            sourceWidth=32,
            sourceHeight=32,
            objects=[],
            backend="test",
            device="CPU",
            preprocessMillis=0,
            inferenceMillis=1,
            postprocessMillis=0,
        )
        runner = PackageRunner(tmp_path, installed, {"limit": 0.4}, {"person": 1}, pool)
        await runner.start()
        try:
            await runner.run(
                [],
                Image.new("RGB", (64, 64)),
                1000,
                TaskInferenceParameters(schemaVersion="1.0"),
                {"people": [{"id": 1, "name": "A", "path": "/private", "url": "secret"}]},
            )
            assert pool.test.await_args.kwargs["image"].size == (32, 32)
        finally:
            await runner.close()

    asyncio.run(scenario())
    assert _public_config(
        {"sourceUrl": "secret", "algorithmResources": {"secret": 1}, "taskId": 1}
    ) == {"taskId": 1}


def test_observation_validity_is_explicit_and_backward_compatible(tmp_path):
    async def run(validity):
        code = (
            "class Algorithm:\n def process(self, frame, sdk):\n"
            "  assert 'observation-validity-v1' in frame['runtimeCapabilities']\n"
            f"  return {{'objects': [], 'observationValid': {validity!r}}}\n"
        )
        descriptor = AlgorithmPackageStore(tmp_path).install(package(code))
        runner = PackageRunner(tmp_path, descriptor, {"limit": 0.4}, {"person": 1}, None)
        await runner.start()
        try:
            await runner.run(
                [], Image.new("RGB", (64, 64)), 1000, TaskInferenceParameters(schemaVersion="1.0")
            )
            assert runner.observation_valid is validity
        finally:
            await runner.close()

    asyncio.run(run(False))
    asyncio.run(run(True))
    with pytest.raises(ValueError, match="observationValid"):
        asyncio.run(run("false"))
