class Algorithm:
    def process(self, frame, sdk):
        region = frame["parameters"]["roi"]
        objects = []
        for obj in frame["objects"]:
            if obj["class"] != "person":
                continue
            box = obj["bbox"]
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"]
            inside = (
                region["x"] <= x <= region["x"] + region["width"]
                and region["y"] <= y <= region["y"] + region["height"]
            )
            objects.append(
                {
                    **obj,
                    "attributes": {
                        **obj.get("attributes", {}),
                        "eventCandidate": inside,
                        "displayLabel": "警戒区内人员" if inside else "区域外人员",
                    },
                }
            )
        return {"objects": objects}
