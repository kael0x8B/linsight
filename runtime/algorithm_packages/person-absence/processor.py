"""Assigned-person occupancy with conservative, short-lived body association.

Only a clear match proves presence. A clear non-match or an empty post proves
absence; unreadable faces never prove absence. Identity leases do not survive
missing bodies, ambiguous crossings, source gaps, or their fixed expiry.
"""

from collections import deque
from math import isfinite, sqrt


def overlap(a: dict, b: dict) -> float:
    width = max(0, min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"]))
    height = max(0, min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"]))
    intersection = width * height
    union = a["width"] * a["height"] + b["width"] * b["height"] - intersection
    return intersection / union if union > 0 else 0


def similarity(a: list, b: list) -> float:
    if len(a) != len(b) or not a or not all(isfinite(x) for x in [*a, *b]):
        raise ValueError("Invalid identity feature")
    norm = sqrt(sum(x * x for x in a) * sum(x * x for x in b))
    if norm < 1e-8:
        raise ValueError("Invalid identity feature")
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm


class Algorithm:
    def __init__(self):
        self.tracks = []
        self.reference = None
        self.reference_id = None
        self.last_stamp = None

    def process(self, frame: dict, sdk) -> dict:
        if "observation-validity-v1" not in frame.get("runtimeCapabilities", []):
            raise ValueError("Upgrade gateway: observation validity support required")
        p = frame["parameters"]
        if (
            len(p["personIds"]) != 1
            or p["confirmFrames"] > p["windowFrames"]
            or p["rejectSimilarity"] >= p["similarity"]
        ):
            raise ValueError("Select one person and valid identity thresholds")
        now = frame["timestampMillis"]
        if self.last_stamp is not None and not 0 < now - self.last_stamp <= 3000:
            self.tracks = []
        self.last_stamp = now
        person_id = p["personIds"][0]
        reference = next(
            (
                r
                for r in frame["resources"].get("people", [])
                if r["id"] == person_id and r.get("validUntil", 0) >= now
            ),
            None,
        )
        if reference is None:
            self.tracks = []
            self.reference = None
            return self.result(p, "指定人员参考不可用", "unknown")
        name = reference["name"]
        if self.reference is None or self.reference_id != person_id:
            self.reference = sdk.reference_embedding("people", person_id)["embedding"]
            self.reference_id = person_id
        roi = p["roi"]
        # Body centroid tolerates seated people; the face is still matched separately.
        bodies = []
        uncertain_detection = False
        for obj in frame["objects"]:
            if obj["class"] != "person":
                continue
            box = obj["bbox"]
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            if not (
                roi["x"] <= x <= roi["x"] + roi["width"]
                and roi["y"] <= y <= roi["y"] + roi["height"]
            ):
                continue
            if obj["confidence"] < p["personConfidence"]:
                uncertain_detection = True
                continue
            if box["width"] > 0 and box["height"] > 0:
                bodies.append(obj)
        if len(bodies) > 8:
            self.tracks = []
            return self.result(p, name, "unknown")
        candidates = [
            [i for i, old in enumerate(self.tracks) if overlap(obj["bbox"], old["box"]) >= 0.3]
            for obj in bodies
        ]
        claims = [sum(i in matches for matches in candidates) for i in range(len(self.tracks))]
        next_tracks = []
        states = []
        for obj, matches in zip(bodies, candidates, strict=True):
            if len(matches) == 1 and claims[matches[0]] == 1:
                track = self.tracks[matches[0]]
            else:
                track = {"history": deque(maxlen=p["windowFrames"]), "verifiedAt": None}
            track["box"] = obj["bbox"]
            feature = sdk.extract_embedding("face", obj["bbox"]).get("embedding")
            score = similarity(feature, self.reference) if feature is not None else None
            observation = (
                True
                if score is not None and score >= p["similarity"]
                else False
                if score is not None and score <= p["rejectSimilarity"]
                else None
            )
            track["history"].append(observation)
            confirmed = (
                observation is True
                and sum(v is True for v in track["history"]) >= p["confirmFrames"]
            )
            if observation is False:
                # Never carry the previous person's identity onto a clear impostor.
                track["verifiedAt"] = None
            if confirmed:
                track["verifiedAt"] = now
            held = (
                observation is not False
                and track["verifiedAt"] is not None
                and now - track["verifiedAt"] <= p["identityHoldSeconds"] * 1000
            )
            if held:
                states.append("present")
            elif (
                observation is False
                and sum(v is False for v in track["history"]) >= p["confirmFrames"]
            ):
                states.append("other")
            else:
                states.append("unknown")
            next_tracks.append(track)
        self.tracks = next_tracks
        if "present" in states:
            state = "present"
        elif "unknown" in states or uncertain_detection:
            state = "unknown"
        else:
            state = "absent"
        return self.result(p, name, state)

    @staticmethod
    def result(parameters: dict, name: str, state: str) -> dict:
        labels = {"present": "本人在岗", "absent": "本人未在区域内", "unknown": "身份待确认"}
        return {
            "observationValid": state != "unknown",
            "objects": [
                {
                    "class": "post_status",
                    "confidence": 1,
                    "bbox": parameters["roi"],
                    "attributes": {
                        "eventCandidate": state == "absent",
                        "displayLabel": f"{name} · {labels[state]}",
                        "displayState": {
                            "present": "normal",
                            "absent": "alert",
                            "unknown": "unknown",
                        }[state],
                        "displayConfidence": None,
                        "visibleByDefault": True,
                        "assignedPersonId": parameters["personIds"][0],
                        "assignedPersonName": name,
                        "presenceState": state,
                        "liveness": "NOT_VERIFIED",
                    },
                }
            ],
        }
