"""Shared, stateless frame inference for live tasks and uploaded-image validation."""

import asyncio
from pathlib import Path

from PIL import Image

from ai_runtime.app.model.contracts import ModelTestParameters, ModelTestRequest
from ai_runtime.app.model.pool import ModelPool
from ai_runtime.app.task.contracts import TaskStartRequest


class TaskFrameInference:
    def __init__(self, request: TaskStartRequest, model_pool: ModelPool, frame_path: Path):
        self.request = request
        self.model_pool = model_pool
        self.frame_path = frame_path

    async def infer(self, image: Image.Image | None = None):
        parameters = ModelTestParameters(
            schemaVersion="1.0",
            confidence=self.request.parameters.confidence,
            nmsThreshold=self.request.parameters.nms_threshold,
            inputWidth=self.request.parameters.input_width,
            inputHeight=self.request.parameters.input_height,
            outputCoordinates="NORMALIZED_XYWH",
        )
        capabilities = {
            node["id"]: node["capabilityKey"]
            for node in self.request.pipeline.get("nodes", [])
            if isinstance(node, dict) and "id" in node and "capabilityKey" in node
        }
        crop_nodes = [
            node
            for node in self.request.pipeline.get("nodes", [])
            if node.get("inputMode") == "PERSON_CROPS"
        ]
        if crop_nodes:
            return await self._infer_person_behavior(crop_nodes, capabilities, parameters, image)
        ocr_nodes = {
            node_id
            for node_id, capability in capabilities.items()
            if capability == "ocr.license-plate"
        }
        if not ocr_nodes:
            requests = [
                ModelTestRequest(
                    modelVersionId=model_version_id,
                    imagePath=self.frame_path,
                    parameters=parameters,
                )
                for model_version_id in dict.fromkeys(self.request.model_bindings.values())
            ]
            image_argument = {"image": image} if image is not None else {}
            if len(requests) > 1 and all(
                self.model_pool.is_loaded(value.model_version_id, "RKNPU") for value in requests
            ):
                # Independent full-frame NPU models can overlap CPU preparation /
                # output decoding with the other model's device execution. Keep
                # at most two in flight and merge only completed same-frame results.
                results = []
                for offset in range(0, len(requests), 2):
                    batch = await asyncio.gather(
                        *(
                            self.model_pool.test(value, **image_argument)
                            for value in requests[offset : offset + 2]
                        ),
                        return_exceptions=True,
                    )
                    for value in batch:
                        if isinstance(value, BaseException):
                            raise value
                        results.append(value)
            else:
                results = [
                    await self.model_pool.test(value, **image_argument) for value in requests
                ]
            return results, [item for result in results for item in result.objects]

        if len(ocr_nodes) != 1:
            raise ValueError("license plate pipeline must contain exactly one OCR node")
        ocr_node = next(iter(ocr_nodes))
        ocr_model_id = self.request.model_bindings.get(ocr_node)
        if ocr_model_id is None:
            raise ValueError("license plate OCR node has no model binding")
        detector_nodes = {
            node_id
            for node_id, capability in capabilities.items()
            if capability in {"detector.license-plate", "detector.vehicle"}
        }
        if not any(capabilities[node_id] == "detector.license-plate" for node_id in detector_nodes):
            raise ValueError("license plate OCR requires a plate detector binding")
        from ai_runtime.app.task.plate_pipeline import infer_license_plates

        return await infer_license_plates(
            self, detector_nodes, capabilities, ocr_model_id, parameters, image
        )

    async def _infer_person_behavior(self, crop_nodes, capabilities, parameters, image):
        """Classify each detected person, never a whole multi-person camera frame."""
        if len(crop_nodes) != 1:
            raise ValueError("behavior pipeline requires exactly one person-crop model")
        behavior_node = crop_nodes[0]
        target_class = {"behavior.phone-call": "phone_call"}.get(behavior_node.get("capabilityKey"))
        detectors = [
            node_id
            for node_id, capability in capabilities.items()
            if capability == "detector.person"
        ]
        if target_class is None or len(detectors) != 1:
            raise ValueError("person-crop behavior requires a behavior and person detector")
        detector_id = self.request.model_bindings[detectors[0]]
        behavior_id = self.request.model_bindings[behavior_node["id"]]
        owned_image = image is None
        source = image if image is not None else Image.open(self.frame_path).convert("RGB")
        try:
            detection = await self.model_pool.test(
                ModelTestRequest(
                    modelVersionId=detector_id,
                    imagePath=self.frame_path,
                    parameters=parameters,
                ),
                image=source,
            )
            results = [detection]
            objects = []
            # Bounded CPU work on the 2 GB gateway; smaller people remain unclassified.
            people = sorted(
                (
                    obj
                    for obj in detection.objects
                    if obj.class_name == "person"
                    and obj.confidence >= self.request.parameters.person_confidence
                ),
                key=lambda obj: obj.bbox.width * obj.bbox.height,
                reverse=True,
            )[:10]
            person_crops = []
            for person in people:
                box = person.bbox
                left = max(0, int(box.x * source.width))
                top = max(0, int(box.y * source.height))
                right = min(source.width, int((box.x + box.width) * source.width))
                bottom = min(source.height, int((box.y + box.height) * source.height))
                if right - left < 32 or bottom - top < 64:
                    continue
                person_crops.append((person, source.crop((left, top, right, bottom))))
            try:
                if hasattr(self.model_pool, "test_batch"):
                    behavior_results = await self.model_pool.test_batch(
                        ModelTestRequest(
                            modelVersionId=behavior_id,
                            imagePath=self.frame_path,
                            parameters=parameters,
                        ),
                        [crop for _, crop in person_crops],
                    )
                else:
                    behavior_results = [
                        await self.model_pool.test(
                            ModelTestRequest(
                                modelVersionId=behavior_id,
                                imagePath=self.frame_path,
                                parameters=parameters,
                            ),
                            image=crop,
                        )
                        for _, crop in person_crops
                    ]
            finally:
                for _, crop in person_crops:
                    crop.close()
            for (person, _), result in zip(person_crops, behavior_results, strict=True):
                results.append(result)
                accepted_labels = {target_class}
                if target_class == "phone_call":
                    accepted_labels.add("calling")  # Upstream action model's canonical class.
                candidates = (obj for obj in result.objects if obj.class_name in accepted_labels)
                candidate = max(candidates, key=lambda obj: obj.confidence, default=None)
                if candidate is not None:
                    objects.append(
                        candidate.model_copy(
                            update={
                                "class_name": target_class,
                                "bbox": person.bbox,
                                "attributes": {
                                    **candidate.attributes,
                                    "behaviorPersonAssociated": True,
                                },
                            }
                        )
                    )
            return results, objects
        finally:
            if owned_image:
                source.close()
