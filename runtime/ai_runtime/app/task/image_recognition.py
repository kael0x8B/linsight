"""One-shot task validation with fresh algorithm state and no stream/event side effects."""

import asyncio
import base64
import binascii
import logging
import tempfile
import time
import warnings
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from ai_runtime.app.capability.package_runner import PackageRunner
from ai_runtime.app.capability.plate_input import package_plate_input
from ai_runtime.app.capability.postprocess import CapabilityPostprocessor
from ai_runtime.app.capability.tracker import IoUTracker
from ai_runtime.app.model.pool import ModelCapacityError, ModelUnavailableError
from ai_runtime.app.task.contracts import TaskStartRequest
from ai_runtime.app.task.inference import TaskFrameInference

MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
IMAGE_TEST_TIMEOUT_SECONDS = 90
LOGGER = logging.getLogger("linsight.task.image-recognition")


class TaskImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: int = Field(alias="taskId", gt=0)
    image_base64: str = Field(
        alias="imageBase64", min_length=4, max_length=4 * ((MAX_IMAGE_BYTES + 2) // 3)
    )


class ImageRecognitionError(ValueError):
    def __init__(self, message: str, code: int = 422, diagnostic_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.diagnostic_id = diagnostic_id


def decode_image(encoded: str) -> Image.Image:
    try:
        content = base64.b64decode(encoded, validate=True)
        if len(content) > MAX_IMAGE_BYTES:
            raise ImageRecognitionError("图片不能超过 4 MB")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ImageRecognitionError("请选择 JPG、PNG 或 WebP 图片")
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ImageRecognitionError("图片不能超过 1600 万像素，请缩小后重试")
                if getattr(source, "n_frames", 1) != 1:
                    raise ImageRecognitionError("请选择静态图片，不支持动图")
                source.load()
                return ImageOps.exif_transpose(source).convert("RGB")
    except ImageRecognitionError:
        raise
    except (binascii.Error, OSError, ValueError, UnidentifiedImageError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ImageRecognitionError("图片损坏或格式不支持，请重新选择图片") from error


class TaskImageRecognizer:
    def __init__(self, root: Path, pool, registry):
        self.root, self.pool, self.registry = root, pool, registry
        self._lock = asyncio.Lock()

    async def recognize(self, request: TaskImageRequest, document: dict) -> dict:
        if self._lock.locked():
            raise ImageRecognitionError("网关正在识别另一张图片，请稍后重试", 409)
        diagnostic_id = str(uuid4())
        async with self._lock:
            try:
                async with asyncio.timeout(IMAGE_TEST_TIMEOUT_SECONDS):
                    return await self._recognize(request, document, diagnostic_id)
            except ImageRecognitionError:
                raise
            except ModelCapacityError as error:
                raise ImageRecognitionError(
                    "网关可用推理资源不足，请稍后重试", 409, diagnostic_id
                ) from error
            except ModelUnavailableError as error:
                raise ImageRecognitionError(
                    "任务所需模型尚未就绪，请先在当前网关部署模型", 409, diagnostic_id
                ) from error
            except TimeoutError as error:
                raise ImageRecognitionError(
                    "图片识别超时，请稍后重试", 504, diagnostic_id
                ) from error
            except Exception as error:
                LOGGER.warning(
                    "Image recognition failed taskId=%s diagnosticId=%s errorType=%s",
                    request.task_id, diagnostic_id, type(error).__name__,
                )
                raise ImageRecognitionError(
                    "图片识别失败，请检查任务模型及算法配置后重试", 422, diagnostic_id
                ) from error

    async def _recognize(self, request, document, diagnostic_id):
        # A private request, tracker and package process prevent sample images from
        # contaminating the running task's temporal evidence or OCR vote window.
        config = TaskStartRequest.model_validate(document["config"])
        started = time.perf_counter()
        image = await asyncio.to_thread(decode_image, request.image_base64)
        lease = ()
        package = None
        try:
            lease = await self.pool.acquire(
                sorted(set(config.model_bindings.values())), registry=self.registry
            )
            self.root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="image-test-", dir=self.root) as directory:
                inference = TaskFrameInference(config, self.pool, Path(directory) / "source.png")
                results, objects = await inference.infer(image)
                timestamp = datetime.now(UTC)
                millis = int(timestamp.timestamp() * 1000)
                if descriptor := config.pipeline.get("algorithmPackage"):
                    package = PackageRunner(
                        self.root, descriptor, config.parameters.algorithm,
                        config.model_bindings, self.pool,
                    )
                    await package.start()
                    if package_plate_input(config.pipeline):
                        objects = IoUTracker(motion_classes=frozenset({"license_plate"})).update(
                            objects, millis
                        )
                    objects = await package.run(
                        objects, image, millis, config.parameters, config.algorithm_resources
                    )
                else:
                    postprocessor = CapabilityPostprocessor(config.pipeline, config.parameters)
                    objects = IoUTracker().update(postprocessor.before_tracking(objects), millis)
                    objects = postprocessor.after_tracking(objects, millis)
                return {
                    "schemaVersion": "1.0",
                    "taskId": config.task_id,
                    "cameraId": config.camera_id,
                    "frameId": diagnostic_id,
                    "diagnosticId": diagnostic_id,
                    "timestamp": timestamp.isoformat(),
                    "revision": document["revision"],
                    "sourceWidth": image.width,
                    "sourceHeight": image.height,
                    "objects": [obj.model_dump(mode="json", by_alias=True) for obj in objects],
                    "backend": "+".join(sorted({item.backend for item in results})),
                    "device": "+".join(sorted({item.device for item in results})),
                    "preprocessMillis": sum(item.preprocess_millis for item in results),
                    "inferenceMillis": sum(item.inference_millis for item in results),
                    "postprocessMillis": sum(item.postprocess_millis for item in results),
                    "totalMillis": round((time.perf_counter() - started) * 1000),
                    "observationValid": package.observation_valid if package else True,
                }
        finally:
            if package:
                await package.close()
            if lease:
                await self.pool.release(lease)
            image.close()
