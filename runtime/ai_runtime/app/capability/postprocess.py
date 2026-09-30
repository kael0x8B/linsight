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
        self._plate_votes: dict[str, deque[tuple[str, float, str | None, str | None]]] = {}
        self._plate_vote_times: dict[str, deque[int]] = {}
        self._plate_presence: dict[str, tuple[str, int]] = {}

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
            people = [
                obj
                for obj in objects
                if obj.class_name == "person"
                and obj.confidence >= self._parameters.person_confidence
            ]
            cigarettes = [obj for obj in objects if obj.class_name in {"cigarette", "smoking"}]
            candidates = []
            by_person: dict[int, DetectionObject] = {}
            for cigarette in cigarettes:
                cx = cigarette.bbox.x + cigarette.bbox.width / 2
                cy = cigarette.bbox.y + cigarette.bbox.height / 2
                owners = [
                    index
                    for index, person in enumerate(people)
                    if person.bbox.x <= cx <= person.bbox.x + person.bbox.width
                    and person.bbox.y <= cy <= person.bbox.y + person.bbox.height * 0.45
                ]
                if not owners:
                    continue
                # One piece of evidence belongs to one person, even with overlapping boxes.
                owner = min(
                    owners, key=lambda index: people[index].bbox.width * people[index].bbox.height
                )
                previous = by_person.get(owner)
                if previous is None or cigarette.confidence > previous.confidence:
                    by_person[owner] = cigarette
            for owner, best in by_person.items():
                candidates.append(
                    best.model_copy(
                        update={
                            "class_name": "smoking",
                            "bbox": people[owner].bbox,
                            "attributes": {
                                **best.attributes,
                                "behaviorPersonAssociated": True,
                                "smokingEvidence": "CIGARETTE_NEAR_UPPER_BODY",
                            },
                        }
                    )
                )
            return candidates
        return objects

    def after_tracking(
        self, objects: list[DetectionObject], occurred_at_millis: int
    ) -> list[DetectionObject]:
        behavior_class = next(
            (
                class_name
                for capability, class_name in self._BEHAVIOR_CLASSES.items()
                if capability in self._capabilities
            ),
            None,
        )
        if behavior_class is not None:
            # Behavior classifiers emit per-frame candidates. RuleEngine is the
            # single owner of N/M, duration, cooldown and event confirmation.
            # Legacy temporal task parameters remain parseable but are ignored.
            return [
                detected.model_copy(
                    update={
                        "attributes": {
                            **detected.attributes,
                            "eventCandidate": True,
                            "temporalConfirmationOwner": "RULE",
                        }
                    }
                )
                for detected in objects
                if detected.class_name == behavior_class
            ]
        if "ocr.license-plate" in self._capabilities:
            return self._vote_license_plates(objects, occurred_at_millis)
        return objects

    def event_candidates(self, objects: list[DetectionObject]) -> list[DetectionObject]:
        """Keep all tracked people in overlays, but alarm only on explicit PPE absence.

        ROI rules match the person class. Passing compliant or unknown people to
        those rules would turn a PPE task into an ordinary intrusion alarm.
        """
        if "ocr.license-plate" in self._capabilities:
            # Tracking IDs can change while a truck waits. RuleEngine owns visit
            # recovery; use the confirmed plate identity only for event deduplication.
            return [
                detected.model_copy(
                    update={
                        "track_id": "plate:" + detected.attributes["plateNumber"],
                    }
                )
                for detected in objects
                if detected.class_name == "license_plate"
                and detected.attributes.get("ocrStatus") == "CONFIRMED"
                and isinstance(detected.attributes.get("plateNumber"), str)
            ]
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

    def rule_observations(
        self, objects: list[DetectionObject], occurred_at_millis: int
    ) -> list[DetectionObject]:
        candidates = self.event_candidates(objects)
        if "ocr.license-plate" not in self._capabilities:
            return candidates
        # OCR uncertainty is not proof that a vehicle left. Retain only the
        # identity of a previously confirmed, still-observed physical track.
        # These presence observations can keep an existing visit open, never
        # start/confirm an event or supply stale OCR as new evidence.
        self._plate_presence = {
            key: value for key, value in self._plate_presence.items()
            if 0 <= occurred_at_millis - value[1] <= 1500
        }
        for obj in objects:
            if obj.class_name != "license_plate" or obj.track_id is None:
                continue
            number = obj.attributes.get("plateNumber")
            if obj.attributes.get("ocrStatus") == "CONFIRMED" and isinstance(number, str):
                self._plate_presence[obj.track_id] = (number, occurred_at_millis)
            elif obj.track_id in self._plate_presence:
                number = self._plate_presence[obj.track_id][0]
                self._plate_presence[obj.track_id] = (number, occurred_at_millis)
                candidates.append(obj.model_copy(update={
                    "track_id": "plate:" + number,
                    "attributes": {**obj.attributes, "eventCandidate": False},
                }))
        return candidates

    def _vote_license_plates(
        self, objects: list[DetectionObject], occurred_at_millis: int
    ) -> list[DetectionObject]:
        cutoff = occurred_at_millis - round(self._parameters.ocr_vote_max_age_seconds * 1000)
        for key, times in list(self._plate_vote_times.items()):
            votes = self._plate_votes[key]
            while times and (times[0] < cutoff or times[-1] > occurred_at_millis):
                times.popleft()
                votes.popleft()
            if not times:
                self._plate_vote_times.pop(key)
                self._plate_votes.pop(key)
        vehicles = [detected for detected in objects if detected.class_name in _VEHICLE_CLASSES]
        advanced = set()
        for key, times in self._plate_vote_times.items():
            if times[-1] != occurred_at_millis:
                times.append(occurred_at_millis)
                self._plate_votes[key].append(("", 0, None, None))
                advanced.add(key)
        voted: list[DetectionObject] = []
        for detected in objects:
            if detected.class_name != "license_plate" or detected.track_id is None:
                continue
            attributes = dict(detected.attributes)
            attributes.pop("plateNumber", None)
            attributes.pop("plateConfidence", None)
            vehicle_track_id = _bind_vehicle_track(detected, vehicles)
            if vehicle_track_id is not None:
                attributes["vehicleTrackId"] = vehicle_track_id
            raw_text = attributes.get("plateText")
            text = _normalize_plate_text(raw_text) if isinstance(raw_text, str) else ""
            # Vehicle association is contextual metadata; it may disappear or
            # change independently of the continuously tracked number plate.
            vote_key = detected.track_id
            # Account for invalid/low-confidence frames in the bounded vote window.
            votes = self._plate_votes.setdefault(
                vote_key, deque(maxlen=self._parameters.ocr_vote_frames)
            )
            times = self._plate_vote_times.setdefault(
                vote_key, deque(maxlen=self._parameters.ocr_vote_frames)
            )
            if not times:
                times.append(occurred_at_millis)
                votes.append(("", 0, None, None))
                advanced.add(vote_key)
            new_frame = vote_key in advanced
            advanced.discard(vote_key)
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
            if confidence < self._parameters.ocr_min_confidence:
                attributes["ocrStatus"] = "LOW_CONFIDENCE"
                voted.append(detected.model_copy(update={"attributes": attributes}))
                continue
            # A strong average must not hide an uncertain province/letter. Older
            # OCR adapters without character scores keep their existing contract.
            if "ocrMinCharConfidence" in attributes:
                minimum = attributes["ocrMinCharConfidence"]
                if (
                    not isinstance(minimum, (int, float))
                    or isinstance(minimum, bool)
                    or not 0 <= minimum <= 1
                ):
                    attributes["ocrStatus"] = "INVALID_CONFIDENCE"
                    voted.append(detected.model_copy(update={"attributes": attributes}))
                    continue
                minimum_threshold = self._parameters.ocr_min_confidence
                if minimum < minimum_threshold:
                    attributes["ocrStatus"] = "LOW_CHAR_CONFIDENCE"
                    voted.append(detected.model_copy(update={"attributes": attributes}))
                    continue
            if text and is_supported_chinese_plate(text):
                color = _clean_optional(attributes.get("plateColor"))
                plate_type = _clean_optional(attributes.get("plateType"))
                if new_frame:
                    votes[-1] = (text, confidence, color, plate_type)
                counts = Counter(value[0] for value in votes if value[0])
                if not counts:
                    continue
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
                unambiguous = count > max(
                    (amount for candidate, amount in counts.items() if candidate != winner),
                    default=0,
                )
                confirmed = (
                    count >= self._parameters.ocr_min_votes
                    and count * 2 > len(votes)
                    and text == winner
                    and unambiguous
                )
                winning_votes = [value for value in votes if value[0] == winner]
                attributes.update(
                    {
                        "ocrStatus": (
                            "CONFIRMED"
                            if confirmed
                            else "PENDING"
                        ),
                        "ocrVoteCount": count,
                        "ocrVoteFrames": len(votes),
                        "ocrVoteAgreement": round(count / len(votes), 4),
                    }
                )
                if confirmed:
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
        while len(self._plate_votes) > 1024:
            oldest = min(self._plate_vote_times, key=lambda key: self._plate_vote_times[key][-1])
            self._plate_votes.pop(oldest)
            self._plate_vote_times.pop(oldest)
        return [self._plate_presentation(item, occurred_at_millis) for item in voted]

    def _plate_presentation(
        self, item: DetectionObject, occurred_at_millis: int
    ) -> DetectionObject:
        status = item.attributes.get("ocrStatus")
        candidate = item.attributes.get("plateText")
        display_label = item.attributes.get("plateNumber", "车牌待确认")
        if status == "PENDING" and isinstance(candidate, str):
            # A valid single-frame OCR read is useful feedback, but it is not
            # an event identity until the existing multi-frame vote confirms it.
            display_label = f"{_normalize_plate_text(candidate)}（待确认）"
        visible = status in {"PENDING", "CONFIRMED"}
        if not visible and status in {
            "LOW_CONFIDENCE",
            "LOW_CHAR_CONFIDENCE",
            "MISSING_CONFIDENCE",
            "UNAVAILABLE",
        }:
            # Bridge a brief OCR dropout only after this track supplied a valid,
            # confident plate. Detector confidence alone also admits timestamps,
            # signs and stickers. Invalid frames never extend this one-second hold
            # or reuse a confirmed number for events.
            votes = self._plate_votes.get(item.track_id, ())
            times = self._plate_vote_times.get(item.track_id, ())
            visible = any(
                vote[0] and 0 <= occurred_at_millis - observed_at <= 1000
                for vote, observed_at in zip(votes, times, strict=True)
            )
        return item.model_copy(
            update={
                "attributes": {
                    **item.attributes,
                    "displayLabel": display_label,
                    "displayConfidence": item.attributes.get("plateConfidence"),
                    "displayState": "normal" if status == "CONFIRMED" else "unknown",
                    "visibleByDefault": visible,
                    # This explicit geometry decision also prevents the
                    # generic overlay from restoring a rejected plate box.
                    "displayGeometryContinuity": True,
                }
            }
        )


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
_TRAILER_PLATE_PATTERN = re.compile(rf"^[{_CHINESE_PROVINCES}][A-HJ-NP-Z][A-HJ-NP-Z0-9]{{4}}挂$")


def _normalize_plate_text(value: str) -> str:
    return re.sub(r"[\s·•._-]+", "", value).upper()


def is_supported_chinese_plate(value: str) -> bool:
    if _PLATE_PATTERN.fullmatch(value) is not None:
        return True
    # GA 36: a trailer reserves its last position for 挂. Its four-character
    # serial contains at most two letters; the pattern also excludes I and O.
    return (
        _TRAILER_PLATE_PATTERN.fullmatch(value) is not None
        and sum(character.isalpha() for character in value[2:6]) <= 2
    )


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
