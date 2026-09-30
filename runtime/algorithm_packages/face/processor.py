from collections import deque


class Algorithm:
    def __init__(self):
        self.features = {}
        self.window = deque(maxlen=30)

    def process(self, frame, sdk):
        parameters = frame["parameters"]
        people = [
            person
            for person in frame["resources"].get("people", [])
            if person.get("validUntil", 0) >= frame["timestampMillis"]
        ]
        if not people:
            return {"objects": []}
        missing = [p for p in people if p["id"] not in self.features]
        for person in missing[:2]:
            self.features[person["id"]] = sdk.reference_embedding("people", person["id"])[
                "embedding"
            ]
        if len(missing) > 2:
            return {"objects": []}
        result = sdk.extract_embedding("face", parameters["roi"])
        feature = result.get("embedding")
        if feature is None:
            self.window.clear()
            return {"objects": []}
        scores = sorted(
            [
                (
                    sum(a * b for a, b in zip(feature, self.features[p["id"]], strict=True)),
                    p,
                )
                for p in people
            ],
            key=lambda v: v[0],
            reverse=True,
        )
        score, person = scores[0]
        second = scores[1][0] if len(scores) > 1 else -1
        matched = score >= parameters["similarity"] and score - second >= parameters["margin"]
        self.window.append(person["id"] if matched else None)
        recent = list(self.window)[-parameters["windowFrames"] :]
        confirmed = (
            matched
            and len(recent) == parameters["windowFrames"]
            and recent.count(person["id"]) >= parameters["confirmFrames"]
        )
        roi = parameters["roi"]
        x1, y1, x2, y2 = result["box"]
        box = {
            "x": roi["x"] + x1 / frame["sourceWidth"],
            "y": roi["y"] + y1 / frame["sourceHeight"],
            "width": (x2 - x1) / frame["sourceWidth"],
            "height": (y2 - y1) / frame["sourceHeight"],
        }
        return {
            "objects": [
                {
                    "class": "face",
                    "confidence": max(0, min(1, score)),
                    "bbox": box,
                    "attributes": {
                        "displayLabel": person["name"] if confirmed else "身份待确认",
                        "identityId": person["id"] if confirmed else None,
                        "eventCandidate": confirmed,
                        "liveness": "NOT_VERIFIED",
                    },
                }
            ]
        }
