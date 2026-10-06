"""Optional CTC observations for packages; never change greedy decoding."""

import json

import numpy as np

PROVINCES = "京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼"


def ctc_evidence(scores: np.ndarray, charset: tuple[str, ...], ignored: str = "") -> str:
    """Follow blank/repeat collapse; alternatives belong to the first province token.

    Preserve raw emission scores. Missing provinces have no fabricated evidence.
    These are aligned model scores, not calibrated sequence probabilities.
    """
    characters = []
    province_scores = {}
    previous = 0
    for timestep, value in enumerate(scores.argmax(axis=1)):
        index = int(value)
        if index and index != previous and charset[index] not in ignored:
            char = charset[index]
            if not characters and char in PROVINCES:
                province_scores = {
                    candidate: float(scores[timestep, candidate_index])
                    for candidate_index, candidate in enumerate(charset)
                    if len(candidate) == 1 and candidate in PROVINCES
                }
            characters.append({"char": char, "score": float(scores[timestep, index])})
        previous = index
    return json.dumps(
        {"schemaVersion": "1.0", "characters": characters, "provinceScores": province_scores},
        ensure_ascii=False, allow_nan=False, separators=(",", ":"),
    )


def body_agrees(first: dict, second: dict, threshold: float) -> bool:
    """Two source crops may agree on the body while the province remains weak.

    Used only for evidence-requesting callers. Never discard a confident,
    conflicting province in favor of a different crop's ambiguous province.
    """
    from ai_runtime.app.capability.postprocess import is_supported_chinese_plate

    def parse(attrs):
        evidence = json.loads(attrs.get("ocrEvidenceJson", "{}"))
        chars = evidence.get("characters", [])
        text = "".join(c["char"] for c in chars)
        if not text or text != attrs.get("plateText"):
            return None
        province = text[0] if text[0] in PROVINCES else ""
        body = text[len(province):]
        scores = [c["score"] for c in chars[len(province):]]
        if (not is_supported_chinese_plate("京" + body) or not scores
                or any(not isinstance(s, (float, int)) or not np.isfinite(s)
                       or not threshold <= s <= 1 for s in scores)):
            return None
        return body, province, chars[0]["score"] if province else 0

    try:
        left, right = parse(first), parse(second)
        if not left or not right or left[0] != right[0]:
            return False
        return left[1] == right[1] or max(left[2], right[2]) < threshold
    except (TypeError, ValueError, KeyError):
        return False
