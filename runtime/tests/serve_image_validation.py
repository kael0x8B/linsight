"""Isolated browser fixture. Run with PYTHONPATH=runtime:runtime/tests from repository root."""

import hashlib
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from test_image_validation import gateway
from test_model_pool import _write_contract_model

from ai_runtime.app.gateway.api import build_gateway_router
from ai_runtime.app.model.contracts import DeployModelRequest
from ai_runtime.app.model.pool import ModelPool

temporary = tempfile.TemporaryDirectory(prefix="linsight-validation-browser-")
root = Path(temporary.name)
pool = ModelPool(max_models=2)
host, model = gateway(root, pool)
model.update(displayName="人员检测", artifactFormat="ONNX", device="CPU")
path = root / "person.onnx"
_write_contract_model(path)
model["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
config = host.store.get(1)["config"]
task = {
    "config": config,
    "revision": 7,
    "appliedRevision": 7,
    "enabled": False,
    "name": "现场人员算法",
    "status": {"status": "STOPPED", "metrics": {}},
    "displayNames": {"task": "现场人员算法", "camera": "测试摄像头", "algorithm": "人员检测"},
}
host.snapshot = lambda: {
    "schemaVersion": "1.0",
    "capabilities": ["task.image-recognition.v1", "task.image-validation.v1"],
    "tasks": [task],
    "models": [model],
    "historyDays": 7,
}


@asynccontextmanager
async def lifespan(app):
    await pool.deploy(
        DeployModelRequest(
            modelVersionId=40,
            artifactPath=path,
            sha256=model["sha256"],
            adapter="person_detection_v1",
            device="CPU",
        )
    )
    yield
    await pool.close()
    host.store.close()
    temporary.cleanup()


app = FastAPI(lifespan=lifespan)
app.include_router(build_gateway_router(host, lambda: None), prefix="/v1")
uvicorn.run(app, host="127.0.0.1", port=18903, log_level="warning")
