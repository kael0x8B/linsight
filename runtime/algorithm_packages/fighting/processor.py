"""Classify neighboring pairs; closeness alone never becomes a fight candidate."""


class Algorithm:
    def process(self, frame, sdk):
        params = frame["parameters"]
        people = sorted(
            (
                o
                for o in frame["objects"]
                if o["class"] == "person" and o["confidence"] >= params["personConfidence"]
            ),
            key=lambda o: o["confidence"],
            reverse=True,
        )[:32]
        pairs = []
        for i, first in enumerate(people):
            a = first["bbox"]
            for j, second in enumerate(people[i + 1 :], i + 1):
                b = second["bbox"]
                dx = abs(a["x"] + a["width"] / 2 - b["x"] - b["width"] / 2)
                dy = abs(a["y"] + a["height"] / 2 - b["y"] - b["height"] / 2)
                if dx > (a["width"] + b["width"]) or dy > max(a["height"], b["height"]):
                    continue
                x, y = max(0, min(a["x"], b["x"])), max(0, min(a["y"], b["y"]))
                right = min(1, max(a["x"] + a["width"], b["x"] + b["width"]))
                bottom = min(1, max(a["y"] + a["height"], b["y"] + b["height"]))
                if right > x and bottom > y:
                    pairs.append(
                        (dx + dy, i, j, {"x": x, "y": y, "width": right - x, "height": bottom - y})
                    )
        result = []
        used = set()
        calls = 0
        for _, i, j, box in sorted(pairs, key=lambda pair: pair[0]):
            if i in used or j in used:
                continue
            if calls >= params["maxPairs"]:
                break
            # One person cannot supply evidence for several simultaneous pair alarms.
            used.update((i, j))
            calls += 1
            objects = sdk.infer("action", box)["objects"]
            best = max(objects, key=lambda o: o["confidence"], default=None)
            if (
                best
                and best["class"] == "fighting"
                and best["confidence"] >= params["fightConfidence"]
            ):
                result.append(
                    {
                        "class": "fighting",
                        "bbox": box,
                        "confidence": best["confidence"],
                        "attributes": {
                            "eventCandidate": True,
                            "displayLabel": "疑似打架 · 待复核",
                            "requiresReview": True,
                        },
                    }
                )
        return {"objects": result}
