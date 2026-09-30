"""Per-frame occupancy statistics; model NMS owns detection deduplication."""


class Algorithm:
    def process(self, frame: dict, sdk) -> dict:
        parameters = frame["parameters"]
        region = parameters["roi"]
        people = []
        for obj in frame["objects"]:
            if obj["class"] != "person" or obj["confidence"] < parameters["personConfidence"]:
                continue
            box = obj["bbox"]
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] * (1 if parameters["useFootPoint"] else 0.5)
            if not (
                region["x"] <= x <= region["x"] + region["width"]
                and region["y"] <= y <= region["y"] + region["height"]
            ):
                continue
            people.append(
                {
                    **obj,
                    "attributes": {
                        "eventCandidate": False,
                        "displayLabel": "统计区域内人员",
                        "displayState": "neutral",
                        "visibleByDefault": parameters["showPersonBoxes"],
                    },
                }
            )
        count = len(people)
        summary = {
            "class": "people_count",
            "confidence": 1,
            "bbox": dict(region),
            "trackId": "people-count-region",
            "attributes": {
                "eventCandidate": False,
                "displayLabel": f"当前人数：{count} 人",
                "displayConfidence": None,
                "displayState": "neutral",
                "visibleByDefault": True,
                "observedCount": count,
                "countScope": "CAMERA_ROI",
                "observedAtMillis": frame["timestampMillis"],
            },
        }
        # Leave one slot for the statistic under the SDK's 512-object output limit.
        return {"objects": [summary, *people[:511]]}
