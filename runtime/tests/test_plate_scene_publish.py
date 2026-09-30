import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "plate_publish", ROOT / "scripts/publish-yard-vehicle-recognition.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReadOnlyCatalog:
    def __init__(self, detector_sha=None, npu_ocr=False):
        self.models = []
        self.versions = {}
        for index, dependency in enumerate(
            module.scene_preset("yard-vehicle-recognition")["models"], 1
        ):
            self.models.append(
                {
                    "id": index,
                    "code": dependency["modelCode"],
                    "name": dependency["modelCode"],
                    "status": 0,
                }
            )
            self.versions[index] = [
                {
                    "id": index * 10,
                    "sha256": dependency["sha256"],
                    "validationStatus": "VERIFIED",
                    "executionStatus": "READY",
                    "publishStatus": "PUBLISHED",
                }
            ]
            if dependency["slot"] == "plate-detector":
                self.versions[index][0]["publishStatus"] = "SUPERSEDED"
                self.versions[index].append(
                    {
                        **self.versions[index][0],
                        "id": 138,
                        "sha256": detector_sha or dependency["alternativeSha256"][0],
                        "publishStatus": "PUBLISHED",
                    }
                )
            if dependency["slot"] == "plate-ocr" and npu_ocr:
                self.versions[index][0]["publishStatus"] = "SUPERSEDED"
                self.versions[index].append(
                    {
                        **self.versions[index][0],
                        "id": 139,
                        "sha256": dependency["alternativeSha256"][0],
                        "publishStatus": "PUBLISHED",
                    }
                )

    def api(self, path, body=None, method=None):
        assert body is None and method is None, "Dry run must never write"
        query = parse_qs(urlsplit(path).query)
        if path.startswith("/ai-video/model/page"):
            matches = [model for model in self.models if model["code"] == query["code"][0]]
            return {"list": matches, "total": len(matches)}
        if path.startswith("/ai-video/model/version/list"):
            return self.versions[int(query["modelId"][0])]
        raise AssertionError(path)


def test_existing_license_plate_and_yard_use_same_specialist_assets_but_keep_event_contracts():
    generic = module.scene_preset("license-plate")
    yard = module.scene_preset("yard-vehicle-recognition")
    assert generic["models"] == yard["models"]
    assert generic["algorithm"]["code"] == "license-plate"
    assert (
        generic["algorithm"]["eventType"]
        == generic["rule"]["eventType"]
        == generic["ruleAst"]["eventType"]
        == "LICENSE_PLATE"
    )
    assert (
        yard["algorithm"]["eventType"] == yard["ruleAst"]["eventType"] == "VEHICLE_PLATE_RECOGNIZED"
    )
    assert generic["rule"]["code"] != yard["rule"]["code"]
    assert generic["algorithm"]["defaultParameters"]["sampleFps"] == 4
    assert generic["pipeline"]["acceptance"]["status"] == "PENDING"
    assert {model["slot"] for model in yard["models"]} == {"plate-detector", "plate-ocr"}
    assert {node["id"] for node in yard["pipeline"]["nodes"]} == {
        "plate-detector", "plate-ocr", "iou-tracker"
    }


@pytest.mark.parametrize("scene", ["license-plate", "yard-vehicle-recognition"])
@pytest.mark.parametrize("npu_ocr", [False, True])
def test_dry_run_resolves_verified_published_npu_after_cpu_is_superseded(scene, npu_ocr):
    result = module.publish(ReadOnlyCatalog(npu_ocr=npu_ocr), apply=False, scene=scene)
    assert not result["applied"]
    assert result["models"]["plate-detector"]["modelVersionId"] == 138
    assert result["models"]["plate-ocr"]["modelVersionId"] == (139 if npu_ocr else 20)


def test_unrecognized_artifact_is_not_silently_selected():
    with pytest.raises(RuntimeError, match="unavailable"):
        module.publish(ReadOnlyCatalog("f" * 64), apply=False)


def test_failed_or_unpublished_ocr_cannot_be_selected():
    client = ReadOnlyCatalog()
    client.versions[2][0]["executionStatus"] = "NOT_READY"
    with pytest.raises(RuntimeError, match="unavailable"):
        module.publish(client, apply=False)


def test_unknown_scene_is_rejected():
    with pytest.raises(ValueError, match="Unknown"):
        module.scene_preset("typo")
