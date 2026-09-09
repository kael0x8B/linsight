import json
import os
import select
import subprocess
import threading
from pathlib import Path

from PIL import Image

from ai_runtime.app.model.contracts import DeployModelRequest, ModelTestParameters, ModelTestResult


class IsolatedAdapter:
    """A serialized model worker; native model work cannot stall the media interpreter."""

    def __init__(self, python: Path, request: DeployModelRequest):
        self._lock = threading.Lock()
        self._model_version_id = request.model_version_id
        self._response_timeout = 120
        env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR"}
        }
        env.update(
            PYTHONPATH=str(Path(__file__).resolve().parents[3]),
            OMP_NUM_THREADS="1",
            OPENBLAS_NUM_THREADS="1",
            YOLO_AUTOINSTALL="false",
        )
        self._process = subprocess.Popen(  # noqa: S603 - fixed internal worker, no shell
            [str(python), "-m", "ai_runtime.app.model.worker"],
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=64 * 1024,
        )
        try:
            self.backend = self._exchange(request.model_dump(mode="json", by_alias=True))["backend"]
            if request.artifact_format == "RKNN":
                self._response_timeout = 10
        except BaseException:
            self.close()
            raise

    def _write(self, data: bytes) -> None:
        remaining = memoryview(data)
        while remaining:
            count = self._process.stdin.write(remaining)
            if not count:
                raise OSError("model worker input closed")
            remaining = remaining[count:]

    def _exchange(self, payload: dict, image_data: bytes | None = None) -> dict:
        with self._lock:
            if not self.alive:
                raise ValueError("模型工作进程已退出，请检查内存或重新部署")
            try:
                self._write((json.dumps(payload) + "\n").encode())
                if image_data is not None:
                    self._write(image_data)
                self._process.stdin.flush()
                readable, _, _ = select.select(
                    [self._process.stdout], [], [], self._response_timeout
                )
                if not readable:
                    self._process.kill()
                    self._process.wait()
                    raise ValueError("模型工作进程响应超时，请检查节点资源")
                line = self._process.stdout.readline(4 * 1024 * 1024)
                response = json.loads(line)
                if "error" in response:
                    raise ValueError(f"模型工作进程执行失败：{response['error']}")
                return response["result"]
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError("模型工作进程已退出，请检查内存或重新部署") from error

    def infer(self, image_path: str, parameters: ModelTestParameters) -> ModelTestResult:
        return ModelTestResult.model_validate(self._exchange({
            "modelVersionId": self._model_version_id,
            "imagePath": image_path,
            "parameters": parameters.model_dump(by_alias=True),
        }))

    def infer_image(self, image: Image.Image, parameters: ModelTestParameters) -> ModelTestResult:
        source = image if image.mode == "RGB" else image.convert("RGB")
        if source.width * source.height * 3 > 32 * 1024 * 1024:
            raise ValueError("decoded image exceeds the model worker input limit")
        data = source.tobytes()
        # Length-delimited binary pixels avoid a second JPEG decode or Base64 / JSON
        # expansion. The original image geometry stays attached to this request.
        return ModelTestResult.model_validate(self._exchange({
            "modelVersionId": self._model_version_id,
            "imageRgb": {"width": source.width, "height": source.height, "bytes": len(data)},
            "parameters": parameters.model_dump(by_alias=True),
        }, data))

    @property
    def alive(self) -> bool:
        return self._process.poll() is None

    def close(self) -> None:
        with self._lock:
            if self._process.poll() is None:
                try:
                    self._write(b'{"shutdown":true}\n')
                    self._process.stdin.flush()
                    self._process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    self._process.kill()
                    self._process.wait()
            self._process.stdin.close()
            self._process.stdout.close()
