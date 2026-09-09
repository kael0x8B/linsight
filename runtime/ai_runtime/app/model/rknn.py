"""RKNN execution through the pinned vendor SDK, with the existing output contract."""

import importlib.metadata
import platform
import threading
from pathlib import Path
from time import perf_counter

import numpy as np
from PIL import Image

from ai_runtime.app.model.contracts import ModelTestParameters, ModelTestResult
from ai_runtime.app.model.generic import decode_manifest_outputs
from ai_runtime.app.model.manifest import RuntimeManifest
from ai_runtime.app.model.person import _elapsed_ms


def require_rknn_sdk():
    if platform.system() != "Linux" or platform.machine() != "aarch64":
        raise ValueError("RKNN requires a Linux ARM64 Rockchip node")
    try:
        if importlib.metadata.version("rknn-toolkit-lite2") != "2.3.2":
            raise ValueError("RKNN requires the pinned toolkit-lite2 2.3.2 SDK")
        from rknnlite.api import RKNNLite
    except (ImportError, importlib.metadata.PackageNotFoundError) as error:
        raise ValueError("RKNN SDK unavailable; deploy the ARM64 Python 3.12 Runtime") from error
    return RKNNLite


class RknnAdapter:
    def __init__(self, path: Path, manifest: RuntimeManifest) -> None:
        preprocess = manifest.preprocess
        if (
            not preprocess.input_width
            or not preprocess.input_height
            or preprocess.dtype != "UINT8"
            or preprocess.layout != "NHWC"
        ):
            raise ValueError("RKNN requires explicit dimensions and UINT8 NHWC input")
        if manifest.decoder.type not in {"AUTO_DETECTION", "CLASSIFICATION", "CTC_GREEDY"}:
            raise ValueError("RKNN decoder is not supported")
        self._manifest = manifest
        self._lock = threading.Lock()
        self._closed = False
        self._runtime = require_rknn_sdk()(verbose=False)
        try:
            if self._runtime.load_rknn(str(path)) != 0:
                raise ValueError("RKNN artifact could not be loaded")
            if self._runtime.init_runtime() != 0:
                raise ValueError("RKNN device or model target is incompatible")
        except BaseException:
            self._runtime.release()
            self._closed = True
            raise

    def infer(self, image_path: str, parameters: ModelTestParameters) -> ModelTestResult:
        with Image.open(image_path) as source:
            return self.infer_image(source, parameters)

    def infer_image(self, source: Image.Image, parameters: ModelTestParameters) -> ModelTestResult:
        started = perf_counter()
        preprocess = self._manifest.preprocess
        width, height = preprocess.input_width, preprocess.input_height
        source_width, source_height = source.size
        rgb = source if source.mode == "RGB" else source.convert("RGB")
        image = rgb.resize((width, height), Image.Resampling.BILINEAR)
        array = np.asarray(image, dtype=np.uint8)
        if preprocess.color == "BGR":
            array = array[..., ::-1]
        # Normalization/quantization is fused into the converted RKNN artifact.
        tensor = np.ascontiguousarray(array[None, ...])
        preprocess_ms = _elapsed_ms(started)
        started = perf_counter()
        with self._lock:
            if self._closed:
                raise ValueError("RKNN model has been released")
            outputs = self._runtime.inference(inputs=[tensor], data_format=["nhwc"])
            if outputs is None or len(outputs) == 0:
                raise ValueError("RKNN inference failed")
            # SDK buffers may be reused by the next call from another task.
            outputs = [np.array(output, copy=True) for output in outputs]
        inference_ms = _elapsed_ms(started)
        started = perf_counter()
        objects = decode_manifest_outputs(self._manifest, outputs, width, height, parameters)
        return ModelTestResult(
            sourceWidth=source_width,
            sourceHeight=source_height,
            objects=objects,
            backend=f"RKNN_RUNTIME_MANIFEST_{self._manifest.decoder.type}",
            device="RKNPU",
            preprocessMillis=preprocess_ms,
            inferenceMillis=inference_ms,
            postprocessMillis=_elapsed_ms(started),
        )

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._runtime.release()
                self._closed = True
