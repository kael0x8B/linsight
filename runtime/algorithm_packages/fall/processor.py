"""Fall candidates from a trained fall detector; confirmation belongs to RuleEngine."""


class Algorithm:
    def process(self, frame, sdk):
        threshold = frame["parameters"]["fallConfidence"]
        return {
            "objects": [
                {
                    **obj,
                    "attributes": {
                        **obj.get("attributes", {}),
                        "eventCandidate": True,
                        "displayLabel": "疑似跌倒",
                    },
                }
                for obj in frame["objects"]
                if obj["class"] == "fall" and obj["confidence"] >= threshold
            ]
        }
