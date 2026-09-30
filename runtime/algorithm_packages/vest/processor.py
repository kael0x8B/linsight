ATTRIBUTE = "vest"
PRESENT_CLASS = "vest"
ABSENT_CLASS = "no_vest"
LABELS = {"present": "已穿反光衣", "absent": "未穿反光衣", "unknown": "反光衣待确认"}


class Algorithm:
    def process(self, frame, sdk):
        cfg = frame["parameters"]
        people = [
            o
            for o in frame["objects"]
            if o["class"] == "person" and o["confidence"] >= cfg["personConfidence"]
        ]
        evidence = [
            o
            for o in frame["objects"]
            if o["class"] in {PRESENT_CLASS, ABSENT_CLASS}
            and o["confidence"] >= cfg["ppeConfidence"]
        ]
        result = []
        for person in people:
            box = person["bbox"]
            candidates = [
                o
                for o in evidence
                if box["x"] <= o["bbox"]["x"] + o["bbox"]["width"] / 2 <= box["x"] + box["width"]
                and box["y"] <= o["bbox"]["y"] + o["bbox"]["height"] / 2 <= box["y"] + box["height"]
            ]
            best = max(candidates, key=lambda o: o["confidence"], default=None)
            state = (
                "unknown"
                if best is None
                else "present"
                if best["class"] == PRESENT_CLASS
                else "absent"
            )
            display_box = box if cfg.get("showPersonBox", False) or best is None else best["bbox"]
            result.append(
                {
                    **person,
                    "attributes": {
                        **person.get("attributes", {}),
                        ATTRIBUTE: state,
                        "ppeConfirmedPerson": True,
                        "eventCandidate": state == "absent",
                        "displayLabel": LABELS[state],
                        "displayConfidence": best["confidence"] if best is not None else None,
                        "displayState": {
                            "absent": "alert",
                            "present": "normal",
                            "unknown": "unknown",
                        }[state],
                        "visibleByDefault": state == "absent",
                        "displayBoxX": display_box["x"],
                        "displayBoxY": display_box["y"],
                        "displayBoxWidth": display_box["width"],
                        "displayBoxHeight": display_box["height"],
                    },
                }
            )
        return {"objects": result}
