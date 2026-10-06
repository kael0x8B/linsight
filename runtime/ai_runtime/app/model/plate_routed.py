"""Route positively identified site-marker plates to a text-line recognizer.

Standard plates retain the specialist's exact preprocessing and decoder. The
site model is selected from visible marker evidence, never the predicted number.
"""

import math
from pathlib import Path
from time import perf_counter

import numpy as np
import onnxruntime as ort
from PIL import Image

from ai_runtime.app.model.contracts import (
    BoundingBox,
    DetectionObject,
    ModelTestParameters,
    ModelTestResult,
)
from ai_runtime.app.model.plate import ChinesePlateOcrAdapter, plate_number_region
from ai_runtime.app.model.plate_evidence import ctc_evidence


class RoutedPlateOcrAdapter:
    backend = "ONNX_RUNTIME_PLATE_OCR_ROUTED"
    device = "CPU"

    def __init__(self, directory: Path, onnx_intra_op_threads: int = 2):
        options = ort.SessionOptions()
        options.intra_op_num_threads = onnx_intra_op_threads
        options.inter_op_num_threads = 1
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        options.add_session_config_entry("session.inter_op.allow_spinning", "0")

        def session(name):
            return ort.InferenceSession(
                str(directory / name), sess_options=options, providers=["CPUExecutionProvider"]
            )

        self._specialist = ChinesePlateOcrAdapter(session("specialist.onnx"), self.device)
        self._site = PaddlePlateTextRecognizer(session("site.onnx"))

    def infer(self, image_path: str | Path, parameters: ModelTestParameters) -> ModelTestResult:
        with Image.open(image_path) as source:
            return self.infer_image(source, parameters)

    def infer_image(self, source: Image.Image, parameters: ModelTestParameters) -> ModelTestResult:
        started = perf_counter()
        number_region, offset = plate_number_region(source)
        try:
            if not offset:
                return self._specialist.infer_image(source, parameters)
            tensor = self._site.prepare(number_region)
            preprocess_ms = _millis(started)
            started = perf_counter()
            output = self._site.session.run(None, {self._site.input_name: tensor})
            inference_ms = _millis(started)
            started = perf_counter()
            if len(output) != 1:
                raise ValueError("site OCR requires exactly one probability output")
            text, raw_text, confidence, minimum = self._site.decode(output[0])
            objects = [
                DetectionObject(
                    **{
                        "class": "text",
                        "confidence": confidence,
                        "bbox": BoundingBox(x=0, y=0, width=1, height=1),
                        "attributes": {
                            "plateText": text,
                            "ocrRawText": raw_text,
                            "ocrConfidence": confidence,
                            "ocrMinCharConfidence": minimum,
                            "ocrNumberRegionLeft": offset / source.width,
                            "ocrLayout": "YELLOW_SIDEBAR",
                            "ocrModelFamily": "PPOCR_SITE",
                        },
                    }
                )
            ]
            if parameters.ocr_evidence:
                objects[0].attributes["ocrEvidenceJson"] = ctc_evidence(
                    np.asarray(output[0])[0], self._site.characters, " ·.-"
                )
            return ModelTestResult(
                sourceWidth=source.width,
                sourceHeight=source.height,
                objects=objects,
                backend=self.backend,
                device=self.device,
                preprocessMillis=preprocess_ms,
                inferenceMillis=inference_ms,
                postprocessMillis=_millis(started),
            )
        finally:
            if number_region is not source:
                number_region.close()


class PaddlePlateTextRecognizer:
    """Paddle CTC: BGR right-padded input and NTC probabilities, not logits."""

    def __init__(self, session):
        inputs, outputs = session.get_inputs(), session.get_outputs()
        if (
            len(inputs) != 1
            or len(inputs[0].shape) != 4
            or inputs[0].shape[1:3] != [3, 48]
            or inputs[0].type != "tensor(float)"
            or len(outputs) != 1
        ):
            raise ValueError("site OCR requires one float [N,3,48,W] input and one output")
        encoded = session.get_modelmeta().custom_metadata_map.get("character")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("site OCR requires its embedded character dictionary")
        characters = encoded.splitlines()
        if (
            any(len(char) != 1 for char in characters)
            or len(set(characters)) != len(characters)
            or " " in characters
        ):
            raise ValueError("site OCR character dictionary is malformed")
        self.characters = ("", *characters, " ")
        shape = outputs[0].shape
        if len(shape) != 3 or shape[2] != len(self.characters):
            raise ValueError("site OCR output must be [N,time,character_count]")
        self.session = session
        self.input_name = inputs[0].name

    @staticmethod
    def prepare(source: Image.Image) -> np.ndarray:
        # Real plates fit the standard width. Bound unusual crops while retaining
        # their aspect ratio; never stretch a W into a narrow V-shaped character.
        resized_width = math.ceil(48 * source.width / source.height)
        if resized_width > 1024:
            raise ValueError("site OCR crop exceeds the supported text-line aspect ratio")
        width = max(320, resized_width)
        with source.convert("RGB") as rgb:
            with rgb.resize((resized_width, 48), Image.Resampling.BILINEAR) as resized:
                bgr = np.asarray(resized, dtype=np.float32)[..., ::-1]
                normalized = (bgr / 255.0 - 0.5) / 0.5
                tensor = np.zeros((1, 3, 48, width), dtype=np.float32)
                tensor[0, :, :, :resized_width] = normalized.transpose(2, 0, 1)
                return tensor

    def decode(self, output: np.ndarray) -> tuple[str, str, float, float]:
        scores = np.asarray(output)
        if (
            scores.ndim != 3
            or scores.shape[0] != 1
            or scores.shape[1] < 1
            or scores.shape[2] != len(self.characters)
            or not np.isfinite(scores).all()
            or np.any(scores < 0)
            or np.any(scores > 1)
            or not np.allclose(scores.sum(axis=2), 1.0, atol=0.01)
        ):
            raise ValueError("site OCR output must contain normalized [1,time,chars] probabilities")
        scores = scores[0]
        indices = scores.argmax(axis=1)
        previous = -1
        raw, selected, confidences = [], [], []
        for timestep, value in enumerate(indices):
            index = int(value)
            if index != previous and index != 0:
                char = self.characters[index]
                raw.append(char)
                # Separators are printed decoration. Every letter/province stays
                # untouched, including an unwanted prefix that must be rejected.
                if char not in " ·.-":
                    selected.append(char)
                    confidences.append(float(scores[timestep, index]))
            previous = index
        average = sum(confidences) / len(confidences) if confidences else 0.0
        minimum = min(confidences) if confidences else 0.0
        return "".join(selected), "".join(raw), average, minimum


def _millis(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))
