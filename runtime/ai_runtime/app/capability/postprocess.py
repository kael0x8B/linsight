import re
from collections import Counter, defaultdict, deque

from ai_runtime.app.model.contracts import BoundingBox, DetectionObject
from ai_runtime.app.task.contracts import TaskInferenceParameters


class CapabilityPostprocessor:
    """Deterministic pipeline semantics that sit above normalized model detections."""

    _BEHAVIOR_CLASSES = {
        "behavior.fall": "fall",
        "behavior.phone-call": "phone_call",
        "behavior.smoking": "smoking",
    }

    def __init__(self, pipeline: dict, parameters: TaskInferenceParameters) -> None:
        self._capabilities = {
            node.get("capabilityKey")
            for node in pipeline.get("nodes", [])
            if isinstance(node, dict)
        }
        self._parameters = parameters
        self._frame_sequence = 0
        self._behavior_history: dict[str, deque[tuple[int, int]]] = {}
        self._plate_votes: dict[str, deque[tuple[str, float, str | None, str | None]]] = {}

    def before_tracking(self, objects: list[DetectionObject]) -> list[DetectionObject]:
        if self._parameters.class_filter:
            allowed = set(self._parameters.class_filter)
            objects = [detected for detected in objects if detected.class_name in allowed]
        if "ppe.helmet" in self._capabilities:
            return _associate_ppe(
                objects,
                "helmet",
                "helmet",
                "no_helmet",
                self._parameters.person_confidence,
                self._parameters.ppe_confidence,
            )
        if "ppe.reflective-vest" in self._capabilities:
            return _associate_ppe(
                objects,
                "vest",
                "vest",
                "no_vest",
                self._parameters.person_confidence,
                self._parameters.ppe_confidence,
            )
        if "behavior.smoking" in self._capabilities:
            # A cigarette alone is not a smoking behavior. Associate the object
            # with one person's head/upper-body region before temporal tracking.
            people = [obj for obj in objects if obj.class_name == "person"
                      and obj.confidence >= self._parameters.person_confidence]
            cigarettes = [obj for obj in objects if obj.class_name in {"cigarette", "smoking"}]
            candidates = []
            by_person: dict[int, DetectionObject] = {}
            for cigarette in cigarettes:
                cx = cigarette.bbox.x + cigarette.bbox.width / 2
                cy = cigarette.bbox.y + cigarette.bbox.height / 2
                owners = [index for index, person in enumerate(people)
                          if person.bbox.x <= cx <= person.bbox.x + person.bbox.width
                          and person.bbox.y <= cy <= person.bbox.y + person.bbox.height * 0.45]
                if not owners:
                    continue
                # One piece of evidence belongs to one person, even with overlapping boxes.
                owner = min(owners, key=lambda index:
                            people[index].bbox.width * people[index].bbox.height)
                previous = by_person.get(owner)
                if previous is None or cigarette.confidence > previous.confidence:
                    by_person[owner] = cigarette
            for owner, best in by_person.items():
                candidates.append(best.model_copy(update={
                    "class_name": "smoking", "bbox": people[owner].bbox,
                    "attributes": {**best.attributes, "behaviorPersonAssociated": True,
                                   "smokingEvidence": "CIGARETTE_NEAR_UPPER_BODY"},
                }))
            return candidates
        return objects

    def after_tracking(
        self, objects: list[DetectionObject], occurred_at_millis: int
    ) -> list[DetectionObject]:
        self._frame_sequence += 1
        behavior_class = next(
            (
                class_name
                for capability, class_name in self._BEHAVIOR_CLASSES.items()
                if capability in self._capabilities
            ),
            None,
        )
        if behavior_class is not None:
            return self._confirm_behavior(objects, behavior_class, occurred_at_millis)
        if "ocr.license-plate" in self._capabilities:
            return self._vote_license_plates(objects)
        return objects

    def event_candidates(self, objects: list[DetectionObject]) -> list[DetectionObject]:
        """Keep all tracked people in overlays, but alarm only on explicit PPE absence.

        ROI rules match the person class. Passing compliant or unknown people to
        those rules would turn a PPE task into an ordinary intrusion alarm.
        """
        attribute = next(
            (
                name
                for capability, name in (("ppe.helmet", "helmet"), ("ppe.reflective-vest", "vest"))
                if capability in self._capabilities
            ),
            None,
        )
        if attribute is None:
            return objects
        return [
            detected
            for detected in objects
            if detected.class_name == "person"
            and detected.attributes.get("ppeConfirmedPerson") is True
            and detected.attributes.get(attribute) == "absent"
        ]

    def _confirm_behavior(
        self,
        objects: list[DetectionObject],
        behavior_class: str,
        occurred_at_millis: int,
    ) -> list[DetectionObject]:
        confirmed: list[DetectionObject] = []
        first_frame = self._frame_sequence - self._parameters.temporal_m + 1
        self._behavior_history = {
            track_id: history for track_id, history in self._behavior_history.items()
            if history and history[-1][0] >= first_frame
        }
        for detected in objects:
            if detected.class_name != behavior_class or detected.track_id is None:
                continue
            history = self._behavior_history.setdefault(
                detected.track_id, deque(maxlen=self._parameters.temporal_m)
            )
            if not history or history[-1][0] != self._frame_sequence:
                history.append((self._frame_sequence, occurred_at_millis))
            recent = [value for value in history if value[0] >= first_frame]
            duration_millis = occurred_at_millis - recent[0][1] if len(recent) >= 2 else 0
            is_confirmed = (
                len(recent) >= self._parameters.temporal_n
                and duration_millis >= self._parameters.duration_seconds * 1000
            )
            attributes = {**detected.attributes, "temporalConfirmed": is_confirmed}
            if is_confirmed:
                attributes.update(
                    {
                        "temporalFrames": len(recent),
                        "temporalWindow": self._parameters.temporal_m,
                    }
                )
                confirmed.append(detected.model_copy(update={"attributes": attributes}))
        return confirmed

    def _vote_license_plates(self, objects: list[DetectionObject]) -> list[DetectionObject]:
        vehicles = [detected for detected in objects if detected.class_name in _VEHICLE_CLASSES]
        voted: list[DetectionObject] = []
        for detected in objects:
            if detected.class_name != "license_plate" or detected.track_id is None:
                continue
            attributes = dict(detected.attributes)
            vehicle_track_id = _bind_vehicle_track(detected, vehicles)
            if vehicle_track_id is not None:
                attributes["vehicleTrackId"] = vehicle_track_id
            raw_text = attributes.get("plateText")
            text = _normalize_plate_text(raw_text) if isinstance(raw_text, str) else ""
            ocr_confidence = attributes.get("ocrConfidence")
            if not isinstance(ocr_confidence, (int, float)) or isinstance(ocr_confidence, bool):
                attributes["ocrStatus"] = "MISSING_CONFIDENCE"
                voted.append(detected.model_copy(update={"attributes": attributes}))
                continue
            confidence = float(ocr_confidence)
            attributes["ocrConfidence"] = round(confidence, 4)
            if not 0 <= confidence <= 1:
                attributes["ocrStatus"] = "INVALID_CONFIDENCE"
                voted.append(detected.model_copy(update={"attributes": attributes}))
                continue
            if text and _is_supported_chinese_plate(text):
                vote_key = vehicle_track_id or detected.track_id
                votes = self._plate_votes.setdefault(
                    vote_key,
                    deque(maxlen=self._parameters.ocr_vote_frames),
                )
                color = _clean_optional(attributes.get("plateColor"))
                plate_type = _clean_optional(attributes.get("plateType"))
                votes.append((text, confidence, color, plate_type))
                counts = Counter(value[0] for value in votes)
                confidence_by_text: dict[str, list[float]] = defaultdict(list)
                for candidate, candidate_confidence, _, _ in votes:
                    confidence_by_text[candidate].append(candidate_confidence)
                winner = max(
                    counts,
                    key=lambda candidate: (
                        counts[candidate],
                        sum(confidence_by_text[candidate]) / len(confidence_by_text[candidate]),
                    ),
                )
                count = counts[winner]
                winning_votes = [value for value in votes if value[0] == winner]
                attributes.update(
                    {
                        "ocrStatus": (
                            "CONFIRMED" if count >= self._parameters.ocr_min_votes else "PENDING"
                        ),
                        "ocrVoteCount": count,
                        "ocrVoteFrames": len(votes),
                        "ocrVoteAgreement": round(count / len(votes), 4),
                    }
                )
                if count >= self._parameters.ocr_min_votes:
                    attributes["plateNumber"] = winner
                    attributes["plateConfidence"] = round(
                        sum(value[1] for value in winning_votes) / len(winning_votes), 4
                    )
                    winning_color = _majority_optional(value[2] for value in winning_votes)
                    winning_type = _majority_optional(value[3] for value in winning_votes)
                    if winning_color is not None:
                        attributes["plateColor"] = winning_color
                    if winning_type is not None:
                        attributes["plateType"] = winning_type
            else:
                attributes["ocrStatus"] = "UNSUPPORTED_FORMAT" if text else "UNAVAILABLE"
            voted.append(detected.model_copy(update={"attributes": attributes}))
        return voted


_VEHICLE_CLASSES = {
    "car",
    "sedan",
    "suv",
    "van",
    "small_truck",
    "box_truck",
    "medium_truck",
    "heavy_truck",
    "trailer",
    "engineering_vehicle",
    "truck",
    "cargo_truck",
    "bus",
    "coach",
}
_CHINESE_PROVINCES = "京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼"
_PLATE_PATTERN = re.compile(rf"^[{_CHINESE_PROVINCES}][A-HJ-NP-Z][A-HJ-NP-Z0-9]{{5,6}}$")


def _normalize_plate_text(value: str) -> str:
    return re.sub(r"[\s·•._-]+", "", value).upper()


def _is_supported_chinese_plate(value: str) -> bool:
    return _PLATE_PATTERN.fullmatch(value) is not None


def _bind_vehicle_track(plate: DetectionObject, vehicles: list[DetectionObject]) -> str | None:
    explicit = plate.attributes.get("vehicleTrackId")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    candidates = [
        vehicle
        for vehicle in vehicles
        if vehicle.track_id is not None and _center_inside(plate.bbox, vehicle.bbox)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda vehicle: vehicle.confidence).track_id


def _clean_optional(value: object) -> str | None:
    return value.strip().upper() if isinstance(value, str) and value.strip() else None


def _majority_optional(values) -> str | None:
    counts = Counter(value for value in values if value is not None)
    return counts.most_common(1)[0][0] if counts else None


def _associate_ppe(
    objects: list[DetectionObject],
    attribute_name: str,
    present_class: str,
    absent_class: str,
    person_confidence: float,
    ppe_confidence: float,
) -> list[DetectionObject]:
    people = [
        detected
        for detected in objects
        if detected.class_name == "person" and detected.confidence >= person_confidence
    ]
    candidates = [
        detected
        for detected in objects
        if detected.class_name in {present_class, absent_class, "unknown"}
        and detected.confidence >= ppe_confidence
    ]
    result: list[DetectionObject] = []
    for person in people:
        matched = max(
            (candidate for candidate in candidates if _center_inside(candidate.bbox, person.bbox)),
            key=lambda candidate: candidate.confidence,
            default=None,
        )
        state = "unknown"
        if matched is not None and matched.class_name == present_class:
            state = "present"
        elif matched is not None and matched.class_name == absent_class:
            state = "absent"
        attributes = {
            **person.attributes,
            attribute_name: state,
            "ppeConfirmedPerson": True,
        }
        if matched is not None:
            attributes["ppeConfidence"] = matched.confidence
            attributes["ppeSourceClass"] = matched.class_name
            # Retain the detector's PPE region for display/evidence, while the
            # person bbox remains the input to tracking, ROI and event identity.
            attributes.update(
                {
                    "ppeBoxX": matched.bbox.x,
                    "ppeBoxY": matched.bbox.y,
                    "ppeBoxWidth": matched.bbox.width,
                    "ppeBoxHeight": matched.bbox.height,
                }
            )
        result.append(person.model_copy(update={"attributes": attributes}))
    return result


def _center_inside(inner: BoundingBox, outer: BoundingBox) -> bool:
    center_x = inner.x + inner.width / 2
    center_y = inner.y + inner.height / 2
    return (
        outer.x <= center_x <= outer.x + outer.width
        and outer.y <= center_y <= outer.y + outer.height
    )
