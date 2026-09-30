"""Observe people; COUNT_BELOW decides absence even when this list is empty."""


class Algorithm:
    def process(self, frame: dict, sdk) -> dict:
        return {
            "objects": [
                {
                    **obj,
                    "attributes": {
                        **obj.get("attributes", {}),
                        "eventCandidate": True,
                        "displayLabel": "岗位人员候选",
                        "displayState": "neutral",
                        "visibleByDefault": True,
                    },
                }
                for obj in frame["objects"]
                if obj["class"] == "person"
                and obj["confidence"] >= frame["parameters"]["personConfidence"]
            ]
        }
