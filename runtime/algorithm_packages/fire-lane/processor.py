"""Filter supported targets; shared tracking and Rule AST own temporal confirmation."""


class Algorithm:
    def process(self, frame, sdk):
        names = {
            "car": "小汽车",
            "truck": "货车",
            "bus": "客车",
            "bicycle": "自行车",
            "motorcycle": "摩托车",
            "chair": "椅子",
            "couch": "沙发",
            "bench": "长椅",
            "backpack": "背包",
            "handbag": "手提包",
            "suitcase": "行李箱",
        }
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
                if obj["class"] in names and obj["confidence"] >= frame["parameters"]["confidence"]
            ]
        }
