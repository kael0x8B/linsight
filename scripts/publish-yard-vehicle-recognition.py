#!/usr/bin/env python3
"""Publish the vehicle scene through owner APIs, reusing verified model assets.

Default is read-only. --publish registers the algorithm/pipeline and event rule;
it never starts a camera, reinstalls a deleted task, or changes delivery targets.
"""

from __future__ import annotations

import argparse
import copy
import getpass
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
PRESET = ROOT / "runtime/algorithm_presets/yard-vehicle-recognition.json"


class Client:
    def __init__(self, base_url: str, tenant: int, username: str, password: str):
        endpoint = urlsplit(base_url)
        if (
            endpoint.scheme not in {"http", "https"}
            or not endpoint.hostname
            or endpoint.username
        ):
            raise ValueError(
                "Provide an HTTP(S) admin API URL without embedded credentials"
            )
        self.base_url = base_url.rstrip("/")
        self.headers = {"Content-Type": "application/json", "tenant-id": str(tenant)}
        self.opener = build_opener(ProxyHandler({}))
        login = self.api(
            "/system/auth/login", {"username": username, "password": password}
        )
        self.headers["Authorization"] = "Bearer " + login["accessToken"]

    def api(self, path: str, body=None, method=None):
        request = Request(
            self.base_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=self.headers,
            method=method,
        )
        with self.opener.open(request, timeout=45) as response:
            value = json.load(response)
        if value.get("code") != 0:
            raise RuntimeError(
                f"API {path.split('?')[0]}: {value.get('code')} {value.get('msg')}"
            )
        return value.get("data")

    def upload_model(self, fields, artifact):
        boundary = "linsight-" + uuid4().hex
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
            for key, value in fields.items()
        ]
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{artifact.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
            + artifact.read_bytes()
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        request = Request(
            self.base_url + "/ai-video/model/version/upload",
            data=b"".join(parts),
            headers={
                **self.headers,
                "Content-Type": "multipart/form-data; boundary=" + boundary,
            },
        )
        with self.opener.open(request, timeout=90) as response:
            result = json.load(response)
        if result.get("code") != 0:
            raise RuntimeError(f"Model upload failed: {result.get('msg')}")
        return result["data"]


def records(client, domain, **query):
    rows = []
    page = 1
    while True:
        result = client.api(
            f"/ai-video/{domain}/page?"
            + urlencode(
                {
                    "pageNo": page,
                    "pageSize": 100,
                    **query,
                }
            )
        )
        rows.extend(result["list"])
        if len(rows) >= result["total"] or not result["list"]:
            return rows
        page += 1


def publish_models(
    client, directory: Path, *, apply: bool, catalog_path: Path | None = None
):
    catalog = json.loads(
        (
            catalog_path
            or ROOT / "runtime/model_assets/chinese-plate-specialist-v1.json"
        ).read_text()
    )
    # Validate every artifact before creating anything in the platform.
    for entry in catalog["models"]:
        artifact = directory / entry["fileName"]
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Unexpected artifact digest: {artifact.name}")
    output = []
    for entry in catalog["models"]:
        definition = {
            key: entry[key] for key in ("name", "code", "sourceType", "description")
        }
        definition["status"] = 0
        existing = [
            m
            for m in records(client, "model", code=entry["code"])
            if m["code"] == entry["code"]
        ]
        if not apply:
            output.append(
                {"code": entry["code"], "sha256": entry["sha256"], "applied": False}
            )
            continue
        model_id = (
            existing[0]["id"]
            if existing
            else client.api("/ai-video/model/create", definition)
        )
        versions = client.api(f"/ai-video/model/version/list?modelId={model_id}")
        version = next((v for v in versions if v["sha256"] == entry["sha256"]), None)
        if version:
            manifest = version["runtimeManifest"]
            if isinstance(manifest, str):
                manifest = json.loads(manifest)
            if manifest != entry["runtimeManifest"]:
                raise ValueError(
                    "Existing model version has a different execution contract"
                )
        if version:
            version_id = version["id"]
        else:
            fields = {
                key: entry[key]
                for key in (
                    "version",
                    "sourceRepository",
                    "sourceRevision",
                    "licenseSpdx",
                )
            }
            fields.update(
                {
                    "modelId": model_id,
                    "runtimeManifest": json.dumps(entry["runtimeManifest"]),
                }
            )
            version_id = client.upload_model(fields, directory / entry["fileName"])
        if not version or version["publishStatus"] != "PUBLISHED":
            client.api(
                f"/ai-video/model/version/publish?id={version_id}", method="POST"
            )
        output.append(
            {
                "code": entry["code"],
                "modelId": model_id,
                "modelVersionId": version_id,
                "sha256": entry["sha256"],
                "applied": True,
            }
        )
    return output


def scene_preset(code: str):
    preset = json.loads(PRESET.read_text())
    if code == "license-plate":
        preset["algorithm"].update(
            name="车牌识别", code=code, category="CORE", eventType="LICENSE_PLATE",
            description="中文车牌专用四角定位、原图透视裁剪、专用 OCR 与多帧确认；输出车牌号码和证据。现场效果待验收。",
        )
        preset["rule"].update(
            name="车牌号码确认", code="license-plate-confirmed", eventType="LICENSE_PLATE",
        )
        preset["ruleAst"]["eventType"] = "LICENSE_PLATE"
    elif code != "yard-vehicle-recognition":
        raise ValueError("Unknown plate scene")
    return preset


def publish(client, *, apply: bool, update_existing: bool = False,
            scene: str = "yard-vehicle-recognition"):
    preset = scene_preset(scene)
    resolved = {}
    for dependency in preset["models"]:
        matches = [
            m
            for m in records(client, "model", code=dependency["modelCode"])
            if m["code"] == dependency["modelCode"] and m["status"] == 0
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Missing enabled model {dependency['modelCode']}")
        model = matches[0]
        versions = client.api(f"/ai-video/model/version/list?modelId={model['id']}")
        versions = [
            v
            for v in versions
            if v["sha256"] in {dependency["sha256"], *dependency.get("alternativeSha256", [])}
            and v["validationStatus"] == "VERIFIED"
            and v["executionStatus"] == "READY"
            and v["publishStatus"] == "PUBLISHED"
        ]
        if len(versions) != 1:
            raise RuntimeError(
                f"Verified published model version unavailable: {model['name']}"
            )
        resolved[dependency["slot"]] = {
            "modelId": model["id"],
            "modelVersionId": versions[0]["id"],
            "name": model["name"],
            "sha256": versions[0]["sha256"],
        }
    algorithm = preset["algorithm"]
    algorithm["defaultModelId"] = resolved["plate-detector"]["modelId"]
    dag = copy.deepcopy(preset["pipeline"])
    dag["preset"] = {"code": algorithm["code"], "revision": preset["revision"]}
    for node in dag["nodes"]:
        if node["id"] in resolved:
            node["modelId"] = resolved[node["id"]]["modelId"]
    output = {"name": algorithm["name"], "models": resolved, "applied": apply}
    if not apply:
        return output
    existing = [
        a
        for a in records(client, "algorithm", code=algorithm["code"])
        if a["code"] == algorithm["code"]
    ]
    if existing:
        algorithm_id = existing[0]["id"]
        if any(existing[0].get(k) != v for k, v in algorithm.items()):
            if not update_existing:
                raise RuntimeError(
                    "Scene metadata differs; use --update-existing for this upgrade"
                )
            client.api(
                "/ai-video/algorithm/update",
                {**algorithm, "id": algorithm_id},
                method="PUT",
            )
    else:
        algorithm_id = client.api("/ai-video/algorithm/create", algorithm)
    versions = client.api(
        f"/ai-video/algorithm/pipeline/list?algorithmId={algorithm_id}"
    )
    version = next((v for v in versions if v["dag"] == dag), None)
    pipeline_id = (
        version["id"]
        if version
        else client.api(
            "/ai-video/algorithm/pipeline/save",
            {"algorithmId": algorithm_id, "dag": dag},
        )
    )
    if not version or version["validationStatus"] != "PUBLISHED":
        errors = client.api(
            f"/ai-video/algorithm/pipeline/validate?id={pipeline_id}", method="POST"
        )
        if errors:
            raise RuntimeError(f"Pipeline validation failed: {errors}")
        client.api(
            f"/ai-video/algorithm/pipeline/publish?id={pipeline_id}", method="POST"
        )
    rule = preset["rule"]
    rules = [
        r
        for r in records(client, "rule", eventType=rule["eventType"])
        if r["code"] == rule["code"]
    ]
    if rules and any(rules[0].get(k) != v for k, v in rule.items()):
        raise RuntimeError(
            "Existing rule metadata differs; review it before publishing"
        )
    rule_id = rules[0]["id"] if rules else client.api("/ai-video/rule/create", rule)
    versions = client.api(f"/ai-video/rule/version/list?ruleId={rule_id}")
    version = next((v for v in versions if v["ast"] == preset["ruleAst"]), None)
    rule_version_id = (
        version["id"]
        if version
        else client.api(
            "/ai-video/rule/version/save", {"ruleId": rule_id, "ast": preset["ruleAst"]}
        )
    )
    if not version or version["validationStatus"] != "PUBLISHED":
        errors = client.api(
            f"/ai-video/rule/version/validate?id={rule_version_id}", method="POST"
        )
        if errors:
            raise RuntimeError(f"Rule validation failed: {errors}")
        client.api(
            f"/ai-video/rule/version/publish?id={rule_version_id}", method="POST"
        )
    return {
        **output,
        "algorithmId": algorithm_id,
        "pipelineVersionId": pipeline_id,
        "ruleId": rule_id,
        "ruleVersionId": rule_version_id,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:48888/admin-api")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--models-only", action="store_true")
    parser.add_argument("--model-artifacts", type=Path)
    parser.add_argument("--model-catalog", type=Path)
    parser.add_argument("--update-existing", action="store_true")
    parser.add_argument("--scene", choices=("yard-vehicle-recognition", "license-plate"),
                        default="yard-vehicle-recognition")
    args = parser.parse_args()
    endpoint = urlsplit(args.api_url)
    if (
        endpoint.scheme not in {"http", "https"}
        or not endpoint.hostname
        or endpoint.username
    ):
        parser.error("Provide an HTTP(S) admin API URL without embedded credentials")
    password = os.environ.get("LINSIGHT_PUBLISH_PASSWORD") or getpass.getpass(
        "Platform password: "
    )
    client = Client(args.api_url, args.tenant_id, args.username, password)
    if args.models_only:
        if args.model_artifacts is None:
            parser.error("--models-only requires --model-artifacts")
        result = publish_models(
            client,
            args.model_artifacts,
            apply=args.publish,
            catalog_path=args.model_catalog,
        )
    else:
        result = publish(
            client, apply=args.publish, update_existing=args.update_existing, scene=args.scene
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
