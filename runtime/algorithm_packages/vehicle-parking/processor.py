"""Vehicle candidates; the shared tracker and stationary rule measure parking time."""


class Algorithm:
    def process(self, frame, sdk):
        names = {"car": "小汽车", "truck": "货车", "bus": "客车"}
        return {
            "objects": [
                {
                    **obj,
                    "attributes": {
                        **obj.get("attributes", {}),
                        "eventCandidate": True,
                        "displayLabel": names[obj["class"]],
                    },
                }
                for obj in frame["objects"]
                if obj["class"] in names
                and obj["confidence"] >= frame["parameters"]["vehicleConfidence"]
            ]
        }
