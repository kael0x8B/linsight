from time import perf_counter

import numpy as np
from PIL import Image

from ai_runtime.app.model.contracts import (
    BoundingBox,
    DetectionObject,
    ModelTestParameters,
    ModelTestResult,
)
from ai_runtime.app.model.manifest import RuntimeManifest
from ai_runtime.app.model.person import _elapsed_ms, _nms, _to_object, decode_detection_rows


class GenericOnnxAdapter:
    """ONNX executor configured entirely by a runtime manifest."""

    def __init__(self, session, device: str, manifest: RuntimeManifest) -> None:
        inputs = session.get_inputs()
        if len(inputs) != 1:
            raise ValueError("generic runtime currently requires exactly one model input")
        self._session = session
        self._device = device
        self._manifest = manifest
        self._input = inputs[0]

    def infer(self, image_path: str, parameters: ModelTestParameters) -> ModelTestResult:
        with Image.open(image_path) as source:
            return self.infer_image(source, parameters)

    def infer_image(self, source: Image.Image, parameters: ModelTestParameters) -> ModelTestResult:
        if self._manifest.decoder.type == "CLASSIFICATION":
            return self.infer_images([source], parameters)[0]
        started = perf_counter()
        source_width, source_height = source.size
        width, height = self._input_size(parameters)
        tensor = self._prepare_array(source, width, height)[None, ...]
        preprocess_ms = _elapsed_ms(started)
        started = perf_counter()
        outputs = self._session.run(None, {self._input.name: tensor})
        inference_ms = _elapsed_ms(started)
        started = perf_counter()
        objects = self._decode(outputs, width, height, parameters)
        return ModelTestResult(
            sourceWidth=source_width,
            sourceHeight=source_height,
            objects=objects,
            backend=f"ONNX_RUNTIME_MANIFEST_{self._manifest.decoder.type}",
            device=self._device,
            preprocessMillis=preprocess_ms,
            inferenceMillis=inference_ms,
            postprocessMillis=_elapsed_ms(started),
        )

    def infer_images(
        self, sources: list[Image.Image], parameters: ModelTestParameters
    ) -> list[ModelTestResult]:
        """Classify multiple crops in one ONNX call when the model supports batching."""
        if not sources:
            return []
        if self._manifest.decoder.type != "CLASSIFICATION":
            raise ValueError("batched generic inference currently supports classification only")
        started = perf_counter()
        width, height = self._input_size(parameters)
        source_sizes = [source.size for source in sources]
        arrays = [self._prepare_array(source, width, height) for source in sources]
        tensor = np.stack(arrays)
        preprocess_ms = _elapsed_ms(started)

        started = perf_counter()
        outputs = self._session.run(None, {self._input.name: tensor})
        inference_ms = _elapsed_ms(started)
        started = perf_counter()
        batch_size = len(sources)
        for output in outputs:
            array = np.asarray(output)
            if array.ndim == 0 or array.shape[0] != batch_size:
                raise ValueError(
                    f"classification batch output has shape {list(array.shape)}, "
                    f"expected first dimension {batch_size}"
                )
        decoded = [
            self._decode(
                [np.asarray(output)[index : index + 1] for output in outputs],
                width,
                height,
                parameters,
            )
            for index in range(batch_size)
        ]
        postprocess_ms = _elapsed_ms(started)
        # Task metrics sum model-stage timings. Divide shared batch work so the
        # reported total represents one native call instead of N duplicate calls.
        preprocess_parts = _split_millis(preprocess_ms, batch_size)
        inference_parts = _split_millis(inference_ms, batch_size)
        postprocess_parts = _split_millis(postprocess_ms, batch_size)
        return [
            ModelTestResult(
                sourceWidth=source_width,
                sourceHeight=source_height,
                objects=objects,
                backend=f"ONNX_RUNTIME_MANIFEST_{self._manifest.decoder.type}",
                device=self._device,
                preprocessMillis=preprocess_parts[index],
                inferenceMillis=inference_parts[index],
                postprocessMillis=postprocess_parts[index],
            )
            for index, ((source_width, source_height), objects) in enumerate(
                zip(source_sizes, decoded, strict=True)
            )
        ]

    def _prepare_array(self, source: Image.Image, width: int, height: int) -> np.ndarray:
        image = source if source.mode == "RGB" else source.convert("RGB")
        resized = image.resize((width, height), Image.Resampling.BILINEAR)
        try:
            array = np.array(resized)
            preprocess = self._manifest.preprocess
            if preprocess.color == "BGR":
                array = array[..., ::-1].copy()
            if preprocess.dtype == "FLOAT32":
                array = array.astype(np.float32)
                array = array * preprocess.scale
                array = (array - np.asarray(preprocess.mean, dtype=np.float32)) / np.asarray(
                    preprocess.std, dtype=np.float32
                )
            else:
                array = array.astype(np.uint8)
            if preprocess.layout == "NCHW":
                array = np.transpose(array, (2, 0, 1))
            return array
        finally:
            resized.close()
            if image is not source:
                image.close()

    def _input_size(self, parameters: ModelTestParameters) -> tuple[int, int]:
        preprocess = self._manifest.preprocess
        shape = self._input.shape
        if preprocess.layout == "NCHW":
            shape_height = shape[2] if len(shape) == 4 else None
            shape_width = shape[3] if len(shape) == 4 else None
        else:
            shape_height = shape[1] if len(shape) == 4 else None
            shape_width = shape[2] if len(shape) == 4 else None
        width = preprocess.input_width or (
            shape_width if isinstance(shape_width, int) else parameters.input_width
        )
        height = preprocess.input_height or (
            shape_height if isinstance(shape_height, int) else parameters.input_height
        )
        return width, height

    def _decode(
        self,
        outputs: list[object],
        width: int,
        height: int,
        parameters: ModelTestParameters,
    ) -> list[DetectionObject]:
        return decode_manifest_outputs(self._manifest, outputs, width, height, parameters)


def decode_manifest_outputs(
    manifest: RuntimeManifest,
    outputs: list[object],
    width: int,
    height: int,
    parameters: ModelTestParameters,
) -> list[DetectionObject]:
    """The mathematical output contract is shared by CPU and NPU execution."""
    decoder = manifest.decoder
    if decoder.type == "AUTO_DETECTION":
        rows = decode_detection_rows(
            outputs, width, height, len(decoder.labels), parameters.confidence
        )
        candidates = [row for row in rows if float(row[4]) >= parameters.confidence]
        return [
            _to_object(row, decoder.labels) for row in _nms(candidates, parameters.nms_threshold)
        ]
    if decoder.type == "CLASSIFICATION":
        return _decode_classification(np.asarray(outputs[0]), decoder.labels, parameters.confidence)
    if decoder.type == "CTC_GREEDY":
        return _decode_ctc(
            np.asarray(outputs[0]), decoder.charset, decoder.blank_index, parameters.confidence
        )
    raise ValueError(f"decoder {decoder.type} requires a built-in protocol decoder")


def _split_millis(total: int, count: int) -> list[int]:
    quotient, remainder = divmod(total, count)
    return [quotient + (index < remainder) for index in range(count)]


def _decode_classification(
    output: np.ndarray, labels: tuple[str, ...], threshold: float
) -> list[DetectionObject]:
    logits = np.asarray(output, dtype=np.float64).reshape(-1)
    if logits.size != len(labels):
        raise ValueError(f"classification output has {logits.size} classes, expected {len(labels)}")
    logits -= logits.max(initial=0.0)
    probabilities = np.exp(logits)
    probabilities /= probabilities.sum()
    index = int(np.argmax(probabilities))
    confidence = float(probabilities[index])
    if confidence < threshold:
        return []
    return [
        DetectionObject(
            **{
                "class": labels[index],
                "confidence": confidence,
                "bbox": BoundingBox(x=0, y=0, width=1, height=1),
                "attributes": {"classId": index},
            }
        )
    ]


def _decode_ctc(
    output: np.ndarray,
    charset: tuple[str, ...],
    blank_index: int | None,
    threshold: float,
) -> list[DetectionObject]:
    logits = np.asarray(output, dtype=np.float64)
    if logits.ndim != 3 or logits.shape[0] != 1:
        raise ValueError(f"CTC output must be [1, classes, time], received {list(logits.shape)}")
    if logits.shape[1] != len(charset):
        raise ValueError(f"CTC output has {logits.shape[1]} classes, expected {len(charset)}")
    blank = len(charset) - 1 if blank_index is None else blank_index
    scores = logits[0]
    scores -= scores.max(axis=0, keepdims=True)
    probabilities = np.exp(scores)
    probabilities /= probabilities.sum(axis=0, keepdims=True)
    indices = np.argmax(probabilities, axis=0)
    text: list[str] = []
    selected: list[float] = []
    previous = -1
    for timestep, value in enumerate(indices):
        index = int(value)
        if index != previous and index != blank:
            text.append(charset[index])
            selected.append(float(probabilities[index, timestep]))
        previous = index
    confidence = sum(selected) / len(selected) if selected else 0.0
    if not text or confidence < threshold:
        return []
    return [
        DetectionObject(
            **{
                "class": "text",
                "confidence": confidence,
                "bbox": BoundingBox(x=0, y=0, width=1, height=1),
                "attributes": {"text": "".join(text), "ocrConfidence": confidence},
            }
        )
    ]
