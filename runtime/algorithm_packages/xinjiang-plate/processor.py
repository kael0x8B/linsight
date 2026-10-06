"""Region preference belongs to this versioned package, never to shared models."""

import json
import math
import re
from collections import Counter, deque

PROVINCES = "京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼"
BODY = re.compile(r"[A-HJ-NP-Z][A-HJ-NP-Z0-9]{5,6}")
TRAILER = re.compile(r"[A-HJ-NP-Z][A-HJ-NP-Z0-9]{4}挂")
CAPABILITY = "plate-ocr-evidence-v1"


def score(value):
    return (isinstance(value, (float, int)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 <= value <= 1)


def observation(attributes, parameters):
    """Fail closed on absent/misaligned character data or a weak number body."""
    encoded = attributes.get("ocrEvidenceJson")
    if not isinstance(encoded, str) or len(encoded) > 32768:
        return None
    try:
        evidence = json.loads(encoded)
        if evidence.get("schemaVersion") != "1.0":
            return None
        chars = evidence["characters"]
        if not isinstance(chars, list) or not 6 <= len(chars) <= 8:
            return None
        if any(not isinstance(c.get("char"), str) or len(c["char"]) != 1
               or not score(c.get("score")) for c in chars):
            return None
        text = "".join(c["char"] for c in chars)
        if text != attributes.get("plateText"):
            return None
        has_province = text[0] in PROVINCES
        body = text[1:] if has_province else text
        if not BODY.fullmatch(body) and not (
            TRAILER.fullmatch(body) and sum(c.isalpha() for c in body[1:5]) <= 2
        ):
            return None
        body_score = min(c["score"] for c in chars[int(has_province):])
        if body_score < parameters["bodyMinConfidence"]:
            return None
        candidates = evidence["provinceScores"]
        if not isinstance(candidates, dict) or any(
            len(c) != 1 or c not in PROVINCES or not score(s) for c, s in candidates.items()
        ):
            return None
        if has_province:
            if (text[0] not in candidates
                    or abs(candidates[text[0]] - chars[0]["score"]) > 1e-6):
                return None
        elif candidates:
            return None
        return {"body": body, "scores": candidates, "raw": text, "bodyScore": body_score}
    except (KeyError, TypeError, AttributeError, ValueError):
        return None


class Algorithm:
    def __init__(self):
        self.tracks = {}
        self.last_timestamp = None
        self._processed_at = {}

    def process(self, frame, sdk):
        if CAPABILITY not in frame.get("runtimeCapabilities", []):
            raise ValueError("当前网关缺少车牌字符候选能力")
        p = frame["parameters"]
        if p["minVotes"] > p["voteFrames"]:
            raise ValueError("一致帧数不能大于投票窗口")
        timestamp = frame["timestampMillis"]
        if self.last_timestamp is not None and timestamp < self.last_timestamp:
            self.tracks.clear()
            self._processed_at.clear()
        self.last_timestamp = timestamp
        max_age = p["maxAgeSeconds"] * 1000
        for key, votes in list(self.tracks.items()):
            while votes and timestamp - votes[0][0] > max_age:
                votes.popleft()
            if not votes:
                del self.tracks[key]
            elif votes[-1][0] != timestamp:
                # Missing/invalid frames consume a vote just like the original algorithm.
                votes.append((timestamp, None))
        result, seen = [], set()
        for obj in frame["objects"]:
            track = obj.get("trackId")
            if obj.get("class") != "license_plate" or not track or track in seen:
                continue
            seen.add(track)
            attributes = dict(obj.get("attributes", {}))
            for field in ("plateNumber", "plateConfidence", "provinceSource"):
                attributes.pop(field, None)
            current = observation(attributes, p)
            if track not in self.tracks:
                self.tracks[track] = deque(maxlen=p["voteFrames"])
            votes = self.tracks[track]
            # Repeated delivery of a frame never supplies a second or replacement vote.
            if not votes or votes[-1][0] != timestamp:
                votes.append((timestamp, current))
            elif votes[-1][1] is None and self._processed_at.get(track) != timestamp:
                votes[-1] = (timestamp, current)
            if self._processed_at.get(track) == timestamp:
                current = votes[-1][1]
            self._processed_at[track] = timestamp
            decision = self._decide(votes, current, p)
            attributes.update({
                "ocrStatus": "PENDING" if current else "LOW_BODY_CONFIDENCE",
                "eventCandidate": False,
                "displayLabel": "车牌待确认",
                "displayConfidence": None,
                "displayState": "unknown",
                "visibleByDefault": current is not None,
                "displayGeometryContinuity": True,
                "ocrVoteFrames": len(votes),
                "algorithmPolicy": "xinjiang-plate-1.0.0",
            })
            if current:
                attributes["ocrBodyMinConfidence"] = current["bodyScore"]
                attributes["displayLabel"] = current["raw"] + "（待确认）"
            if decision:
                number, source, count = decision
                inferred = source == "REGION_INFERRED"
                accepted = not inferred or p["allowInferredEvents"]
                attributes.update({
                    "plateNumber": number,
                    "provinceSource": source,
                    "ocrStatus": "CONFIRMED" if accepted else "INFERRED",
                    "eventCandidate": accepted,
                    "ocrVoteCount": count,
                    "ocrVoteAgreement": count / len(votes),
                    "displayLabel": number + ({
                        "OCR": "", "REGION_ASSISTED": "（新疆优先）",
                        "REGION_INFERRED": "（省份推断）",
                    }[source]),
                    "displayState": "unknown" if inferred else "normal",
                    "visibleByDefault": True,
                })
                # Region ranking never rewrites the model's confidence fields.
            result.append({**obj, "attributes": attributes})
        while len(self.tracks) > 128:
            oldest = min(self.tracks, key=lambda key: self.tracks[key][-1][0])
            del self.tracks[oldest]
        self._processed_at = {k: t for k, t in self._processed_at.items() if k in self.tracks}
        return {"objects": result}

    @staticmethod
    def _decide(votes, current, p):
        if not current:
            return None
        counts = Counter(v["body"] for _, v in votes if v)
        body, count = counts.most_common(1)[0]
        if (body != current["body"] or count < p["minVotes"] or count * 2 <= len(votes)):
            return None
        matching = [v for _, v in votes if v and v["body"] == body]
        strong = Counter(
            max(v["scores"], key=v["scores"].get)
            for v in matching if v["scores"]
            and max(v["scores"].values()) >= p["provinceMinConfidence"]
        )
        if len(strong) > 1:
            return None
        if strong:
            province, strong_count = strong.most_common(1)[0]
            if (strong_count >= p["minVotes"] and strong_count * 2 > len(votes)
                    and current["scores"].get(province, 0) >= p["provinceMinConfidence"]):
                return province + body, "OCR", strong_count
            if province != "新":
                return None  # A clear external province vetoes regional substitution.
        observed = [v for v in matching if v["scores"]]
        if (len(observed) >= p["minVotes"] and len(observed) * 2 > len(votes)
                and current["scores"].get("新", 0) >= p["xinMinScore"]):
            averages = {c: sum(v["scores"].get(c, 0) for v in observed) / len(observed)
                        for c in PROVINCES}
            xin, best = averages["新"], max(averages.values())
            support = sum(v["scores"].get("新", 0) >= p["xinMinScore"] for v in observed)
            if (support >= p["minVotes"] and support * 2 > len(votes)
                    and xin >= p["xinMinScore"] and best - xin <= p["maxProvinceGap"]
                    and xin + p["provinceBonus"] > best):
                return "新" + body, "REGION_ASSISTED", support
        if p["allowMissingProvince"] and not observed:
            return "新" + body, "REGION_INFERRED", count
        return None
