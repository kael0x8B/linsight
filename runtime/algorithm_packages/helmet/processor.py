ATTRIBUTE = "helmet"
PRESENT_CLASS = "helmet"
ABSENT_CLASS = "no_helmet"
LABELS = {"present": "已佩戴安全帽", "absent": "未佩戴安全帽", "unknown": "安全帽待确认"}


def associate_heads(people, evidence):
    """One measured head per person. Confidence is not a person's identity.

    Restrict candidates to the upper part of the person, then reserve the best
    geometric pairs globally. A head inside overlapping people cannot be reused.
    Missing/ambiguous evidence stays unknown; no synthetic head boxes are made.
    """
    pairs = []
    for person_index, person in enumerate(people):
        body = person["bbox"]
        if body["width"] <= 0 or body["height"] <= 0:
            continue
        for head_index, item in enumerate(evidence):
            head = item["bbox"]
            cx = head["x"] + head["width"] / 2
            cy = head["y"] + head["height"] / 2
            if not (
                body["x"] <= cx <= body["x"] + body["width"]
                and body["y"] - head["height"] / 4 <= cy <= body["y"] + body["height"] * 0.45
                and 0 < head["width"] <= body["width"] * 1.25
                and 0 < head["height"] <= body["height"] * 0.85
            ):
                continue
            vertical = abs(head["y"] - body["y"]) / max(head["height"], body["height"] * 0.15)
            horizontal = abs(cx - body["x"] - body["width"] / 2) / body["width"]
            pairs.append(
                (
                    vertical + horizontal,
                    body["x"],
                    body["y"],
                    head["x"],
                    head["y"],
                    -item["confidence"],
                    person_index,
                    head_index,
                )
            )
    matched = {}
    used_heads = set()
    for *_, person_index, head_index in sorted(pairs):
        if person_index not in matched and head_index not in used_heads:
            matched[person_index] = evidence[head_index]
            used_heads.add(head_index)
    return matched


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
        matched = associate_heads(people, evidence)
        result = []
        for person_index, person in enumerate(people):
            box = person["bbox"]
            best = matched.get(person_index)
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
