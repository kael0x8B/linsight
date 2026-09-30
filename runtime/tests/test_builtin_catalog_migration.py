import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / (
    "backend/sql/mysql/migrations/ai-video/V202609022330__add_universal_model_algorithm_catalog.sql"
)


def test_catalog_exceeds_phase_one_target_and_has_stable_unique_codes() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    algorithm_rows = re.findall(
        r"^\((72[2-4]\d{2}), '([^']+)', '([a-z0-9-]+)', 'EXTENSION'", sql, re.MULTILINE
    )
    codes = [row[2] for row in algorithm_rows]

    assert len(algorithm_rows) == 223
    assert len(codes) == len(set(codes))
    assert len(codes) >= 80


def test_catalog_preserves_acceptance_gates_and_requested_scene_groups() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for group in (
        "GENERAL_OBJECT",
        "PERSON",
        "PPE",
        "VEHICLE",
        "FACE",
        "OCR",
        "OPEN_VOCAB",
        "SEGMENTATION",
        "VIDEO_QUALITY",
        "COMPOSITE",
    ):
        assert f"'{group}'" in sql
    assert "BLOCKED_EXTERNAL_ASSETS" in sql
    assert "BLOCKED_RUNTIME_ADAPTER" in sql
    assert "BLOCKED_RUNTIME_IMPLEMENTATION" in sql
    assert "No model binary, license approval, SHA256 or acceptance evidence is fabricated" in sql
