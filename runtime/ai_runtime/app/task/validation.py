"""Reusable, device-owned image checks. Runs freeze inputs; inference has no event side effects."""

import asyncio
import base64
import copy
import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from ai_runtime.app.capability.packages import AlgorithmPackageStore
from ai_runtime.app.task.image_recognition import (
    ImageRecognitionError,
    TaskImageRequest,
    decode_image,
)

LOGGER = logging.getLogger("linsight.task.image-validation")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ExpectedResult(Contract):
    category: str = Field(default="", max_length=100)
    count: int = Field(default=0, ge=0, le=1000)
    text: str = Field(default="", max_length=100)
    confidence: float = Field(default=0.5, ge=0, le=1)


class Identity(Contract):
    id: UUID


class Mutation(Identity):
    request_id: UUID = Field(alias="requestId")
    expected_revision: int = Field(alias="expectedRevision", ge=0)


class SaveSet(Mutation):
    name: str = Field(min_length=1, max_length=100)


class RemoveSample(Mutation):
    sample_id: UUID = Field(alias="sampleId")


class SaveSample(Mutation):
    sample_id: UUID = Field(alias="sampleId")
    name: str = Field(min_length=1, max_length=200)
    expected: ExpectedResult
    note: str = Field(default="", max_length=2000)
    image_base64: str | None = Field(default=None, alias="imageBase64", max_length=5_592_408)


class SampleIdentity(Identity):
    offset: int = Field(default=0, ge=0, le=4 * 1024 * 1024)
    sample_id: UUID = Field(alias="sampleId")


class StartRun(Mutation):
    task_id: int = Field(alias="taskId", gt=0)
    task_revision: int = Field(alias="taskRevision", ge=1)
    model_bindings: dict[str, int] = Field(
        default_factory=dict, alias="modelBindings", max_length=20
    )
    algorithm_sha256: str | None = Field(
        default=None, alias="algorithmSha256", pattern=r"^[a-f0-9]{64}$"
    )


class RunItem(Identity):
    sample_id: UUID = Field(alias="sampleId")


def validate_image(encoded: str) -> None:
    with decode_image(encoded):
        pass


def now() -> str:
    return datetime.now(UTC).isoformat()


def comparison_confidence(obj: dict) -> float:
    attributes = obj.get("attributes") or {}
    if obj.get("class") == "license_plate":
        # A plate pipeline has two independent scores. Once OCR has accepted a
        # candidate for presentation, validation should measure the final plate
        # reading rather than reject it solely because the distant detector box
        # scored lower. Hidden OCR failures are excluded separately below.
        for key in ("plateConfidence", "ocrConfidence"):
            value = attributes.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    return float(obj["confidence"])


def compare(expected: dict, result: dict) -> tuple[str, int]:
    if not result.get("observationValid", True):
        return "INCONCLUSIVE", 0
    objects = [
        obj
        for obj in result["objects"]
        if (obj.get("attributes") or {}).get("visibleByDefault") is not False
        and comparison_confidence(obj) >= expected["confidence"]
        and (not expected["category"] or obj["class"] == expected["category"])
        and (
            not expected["text"]
            or expected["text"]
            == str(
                obj.get("attributes", {}).get("plateText")
                or obj.get("attributes", {}).get("plateNumber")
                or ""
            )
        )
    ]
    return ("PASS" if len(objects) == expected["count"] else "FAIL"), len(objects)


class ValidationRepository:
    """Shares the existing encrypted gateway journal; images stay outside SQLite."""

    def __init__(self, db, cipher, root: Path):
        self.db, self.cipher, self.root = db, cipher, root / "validation"
        self.root.mkdir(mode=0o700, exist_ok=True)
        with db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS image_validation ("
                "id TEXT PRIMARY KEY, kind TEXT NOT NULL, parent_id TEXT NOT NULL, "
                "document BLOB NOT NULL)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS image_validation_parent "
                "ON image_validation(kind, parent_id)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS image_validation_receipt ("
                "id TEXT PRIMARY KEY, parent_id TEXT NOT NULL, fingerprint TEXT NOT NULL, "
                "document BLOB NOT NULL)"
            )
        # An in-flight inference cannot survive process restart. Preserve all other results.
        for run in self.iterate("run"):
            changed = False
            for item in run["items"]:
                if item["status"] == "RUNNING":
                    item.update(status="ERROR", error="网关重启中断了本次识别，请重新运行验证集")
                    changed = True
            if changed:
                self.put(run)

    def get(self, identity: str, kind: str | None = None) -> dict:
        row = self.db.execute(
            "SELECT kind, document FROM image_validation WHERE id=?", (identity,)
        ).fetchone()
        if row is None or (kind and row[0] != kind):
            raise KeyError(identity)
        return json.loads(self.cipher.decrypt(row[1]))

    def iterate(self, kind: str, parent: str | None = None):
        rows = self.db.execute(
            "SELECT document FROM image_validation WHERE kind=? AND (? IS NULL OR parent_id=?) "
            "ORDER BY rowid DESC",
            (kind, parent, parent),
        )
        for row in rows:
            yield json.loads(self.cipher.decrypt(row[0]))

    def list(self, kind: str, parent: str | None = None) -> list[dict]:
        return list(self.iterate(kind, parent))

    def count(self, kind: str, parent: str | None = None) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM image_validation WHERE kind=? AND (? IS NULL OR parent_id=?)",
            (kind, parent, parent),
        ).fetchone()[0]

    def put(self, doc: dict):
        with self.db:
            self.db.execute(
                "INSERT INTO image_validation VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET document=excluded.document",
                (
                    doc["id"],
                    doc["kind"],
                    doc.get("setId", doc["id"]),
                    self.cipher.encrypt(json.dumps(doc).encode()),
                ),
            )

    def replay(self, change: Mutation) -> dict | None:
        row = self.db.execute(
            "SELECT fingerprint, document FROM image_validation_receipt WHERE id=?",
            (str(change.request_id),),
        ).fetchone()
        if row is None:
            return None
        fingerprint = hashlib.sha256(change.model_dump_json().encode()).hexdigest()
        if row[0] != fingerprint:
            raise ImageRecognitionError("请求编号已用于不同操作，请刷新后重试", 409)
        return json.loads(self.cipher.decrypt(row[1]))

    def commit(self, change: Mutation, doc: dict):
        # One transaction for the new revision and its idempotency receipt.
        with self.db:
            self.db.execute(
                "INSERT INTO image_validation VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET document=excluded.document",
                (
                    doc["id"],
                    doc["kind"],
                    doc.get("setId", doc["id"]),
                    self.cipher.encrypt(json.dumps(doc).encode()),
                ),
            )
            self.db.execute(
                "INSERT INTO image_validation_receipt VALUES (?, ?, ?, ?)",
                (
                    str(change.request_id),
                    str(change.id),
                    hashlib.sha256(change.model_dump_json().encode()).hexdigest(),
                    self.cipher.encrypt(json.dumps(doc).encode()),
                ),
            )
        LOGGER.info(
            "Validation saved id=%s kind=%s requestId=%s", doc["id"], doc["kind"], change.request_id
        )
        return doc

    def image(self, sample: dict) -> bytes:
        content = (self.root / sample["sha256"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != sample["sha256"]:
            raise ImageRecognitionError("验证图片校验失败，请重新上传", 422)
        return content


class ImageValidationService:
    def __init__(self, gateway):
        self.gateway = gateway
        self.repo = gateway.store.validation
        self.lock = asyncio.Lock()

    def checked_set(self, change: Mutation):
        doc = self.repo.get(str(change.id), "set")
        if doc["revision"] != change.expected_revision:
            raise ImageRecognitionError("验证集已修改，请刷新后重试；当前草稿仍保留", 409)
        return doc

    async def invoke(self, action: str, payload: dict):
        if action == "validation.list":
            Contract.model_validate(payload)
            return [
                {k: v for k, v in doc.items() if k != "samples"} | {"count": len(doc["samples"])}
                for doc in self.repo.list("set")
            ]
        if action == "validation.options":
            Contract.model_validate(payload)
            snapshot = self.gateway.snapshot()
            return {
                "tasks": snapshot["tasks"],
                "models": snapshot["models"],
                "algorithms": AlgorithmPackageStore(self.gateway.settings.runtime_data_root).list(),
            }
        if action == "validation.get":
            return self.repo.get(str(Identity.model_validate(payload).id), "set")
        if action == "validation.runs":
            identity = str(Identity.model_validate(payload).id)
            return [
                {
                    "id": run["id"],
                    "createdAt": run["createdAt"],
                    "setRevision": run["setRevision"],
                    "target": {"name": run["target"]["name"]},
                }
                for run in self.repo.iterate("run", identity)
            ]
        if action == "validation.result":
            request = RunItem.model_validate(payload)
            doc = self.repo.get(str(request.id), "run")
            item = next(
                (item for item in doc["items"] if item["id"] == str(request.sample_id)), None
            )
            if item is None:
                raise KeyError(request.sample_id)
            return item
        if action == "validation.run-get":
            return self.public_run(self.repo.get(str(Identity.model_validate(payload).id), "run"))
        if action == "validation.image":
            request = SampleIdentity.model_validate(payload)
            doc = self.repo.get(str(request.id))
            if doc["kind"] not in {"set", "run"}:
                raise KeyError(request.id)
            samples = doc["samples"] if doc["kind"] == "set" else doc["items"]
            sample = next((item for item in samples if item["id"] == str(request.sample_id)), None)
            if sample is None:
                raise KeyError(request.sample_id)
            content = self.repo.image(sample)
            chunk = content[request.offset : request.offset + 384 * 1024]
            return {
                "imageBase64": base64.b64encode(chunk).decode(),
                "mime": sample["mime"],
                "size": len(content),
                "offset": request.offset,
                "length": len(chunk),
            }
        if action == "validation.save":
            change = SaveSet.model_validate(payload)
            if replay := self.repo.replay(change):
                return replay
            if change.expected_revision == 0:
                if self.repo.count("set") >= 50:
                    raise ImageRecognitionError("当前网关最多保存 50 个验证集")
                try:
                    self.repo.get(str(change.id))
                except KeyError:
                    pass
                else:
                    raise ImageRecognitionError("验证集编号已存在", 409)
                doc = {
                    "schemaVersion": "1.0",
                    "kind": "set",
                    "id": str(change.id),
                    "revision": 0,
                    "samples": [],
                    "createdAt": now(),
                }
            else:
                doc = self.checked_set(change)
            doc.update(name=change.name.strip(), revision=doc["revision"] + 1)
            if not doc["name"]:
                raise ImageRecognitionError("请填写验证集名称")
            return self.repo.commit(change, doc)
        if action == "validation.sample-save":
            change = SaveSample.model_validate(payload)
            if replay := self.repo.replay(change):
                return replay
            doc = self.checked_set(change)
            existing = next((s for s in doc["samples"] if s["id"] == str(change.sample_id)), None)
            if existing is None and len(doc["samples"]) >= 50:
                raise ImageRecognitionError("每个验证集最多 50 张图片")
            sample = {
                "id": str(change.sample_id),
                "name": change.name,
                "expected": change.expected.model_dump(),
                "note": change.note,
            }
            if change.image_base64 is not None:
                await asyncio.to_thread(validate_image, change.image_base64)
                if replay := self.repo.replay(change):
                    return replay
                doc = self.checked_set(change)
                content = base64.b64decode(change.image_base64, validate=True)
                digest = hashlib.sha256(content).hexdigest()
                # Bound retained media independently of the request-size and per-set limits.
                path = self.repo.root / digest
                if not path.exists():
                    if (
                        sum(p.stat().st_size for p in self.repo.root.iterdir()) + len(content)
                        > 512 * 1024 * 1024
                    ):
                        raise ImageRecognitionError(
                            "验证图片已达到 512 MB 配额，请删除不需要的验证集"
                        )
                    temporary = self.repo.root / f".upload-{uuid4()}"
                    try:
                        with temporary.open("xb") as output:
                            os.chmod(temporary, 0o600)
                            output.write(content)
                            output.flush()
                            os.fsync(output.fileno())
                        os.replace(temporary, path)
                    finally:
                        temporary.unlink(missing_ok=True)
                with Image.open(BytesIO(content)) as image:
                    mime = Image.MIME[image.format]
                sample.update(sha256=digest, mime=mime)
            elif existing:
                sample.update(sha256=existing["sha256"], mime=existing["mime"])
            else:
                raise ImageRecognitionError("请上传图片")
            doc["samples"] = [sample if s["id"] == sample["id"] else s for s in doc["samples"]]
            if existing is None:
                doc["samples"].append(sample)
            doc["revision"] += 1
            return self.repo.commit(change, doc)
        if action == "validation.sample-delete":
            change = RemoveSample.model_validate(payload)
            if replay := self.repo.replay(change):
                return replay
            doc = self.checked_set(change)
            doc["samples"] = [s for s in doc["samples"] if s["id"] != str(change.sample_id)]
            doc["revision"] += 1
            return self.repo.commit(change, doc)
        if action == "validation.delete":
            change = Mutation.model_validate(payload)
            try:
                self.checked_set(change)
            except KeyError:
                return {"deleted": True}
            if self.lock.locked():
                raise ImageRecognitionError("识别进行中，请稍后删除", 409)
            with self.repo.db:
                self.repo.db.execute(
                    "DELETE FROM image_validation WHERE parent_id=?", (str(change.id),)
                )
                self.repo.db.execute(
                    "DELETE FROM image_validation_receipt WHERE parent_id=?", (str(change.id),)
                )
            retained = {s["sha256"] for d in self.repo.list("set") for s in d["samples"]}
            retained |= {s["sha256"] for d in self.repo.iterate("run") for s in d["items"]}
            for path in self.repo.root.iterdir():
                if path.name not in retained:
                    path.unlink()
            LOGGER.info("Validation deleted id=%s requestId=%s", change.id, change.request_id)
            return {"deleted": True}
        if action == "validation.run-create":
            return self.public_run(self.create_run(StartRun.model_validate(payload)))
        if action == "validation.run-item":
            return await self.run_item(RunItem.model_validate(payload))
        raise ImageRecognitionError("不支持的验证操作", 400)

    def create_run(self, change: StartRun):
        if replay := self.repo.replay(change):
            return self.repo.get(replay["id"], "run")
        try:
            self.repo.get(str(change.request_id))
        except KeyError:
            pass
        else:
            raise ImageRecognitionError("运行编号已存在，请重试", 409)
        dataset = self.checked_set(change)
        if not dataset["samples"]:
            raise ImageRecognitionError("请先上传验证图片")
        if self.repo.count("run", dataset["id"]) >= 100:
            raise ImageRecognitionError("每个验证集最多保留 100 次运行，请导出后创建新的验证集")
        document = copy.deepcopy(self.gateway.store.get(change.task_id))
        if not document:
            raise KeyError(change.task_id)
        if document["revision"] != change.task_revision:
            raise ImageRecognitionError("任务版本已改变，请刷新版本选项后重试", 409)
        config = document["config"]
        if set(change.model_bindings) - set(config["modelBindings"]):
            raise ImageRecognitionError("模型角色与所选算法不匹配")
        config["modelBindings"].update(change.model_bindings)
        if config["modelBindings"]:
            config["modelVersionId"] = next(iter(config["modelBindings"].values()))
        descriptor = config["pipeline"].get("algorithmPackage")
        if change.algorithm_sha256:
            _, manifest = AlgorithmPackageStore(self.gateway.settings.runtime_data_root).resolve(
                change.algorithm_sha256
            )
            if not descriptor or manifest["code"] != descriptor["manifest"]["code"]:
                raise ImageRecognitionError("只能选择同一算法的已安装版本")
            config["pipeline"]["algorithmPackage"] = {
                "sha256": change.algorithm_sha256,
                "manifest": manifest,
            }
        try:
            self.gateway._validate(config)
        except ValueError as error:
            raise ImageRecognitionError(
                "模型或算法版本与任务角色、参数不兼容，请检查版本选择"
            ) from error
        models = {m["modelVersionId"]: m for m in self.gateway.models.summaries()}
        selected = set(config["modelBindings"].values())
        if not selected or not selected <= models.keys():
            raise ImageRecognitionError("所选模型版本尚未部署到当前网关")
        target = {
            "taskId": change.task_id,
            "taskRevision": change.task_revision,
            "name": document.get("name", str(change.task_id)),
            "pipelineVersionId": config["pipelineVersionId"],
            "algorithm": config["pipeline"].get("algorithmPackage"),
            "modelBindings": config["modelBindings"],
            "parameters": config["parameters"],
            "models": [
                {
                    k: models[i].get(k)
                    for k in (
                        "modelVersionId",
                        "sha256",
                        "displayName",
                        "version",
                        "device",
                        "artifactFormat",
                    )
                }
                for i in sorted(selected)
            ],
        }
        doc = {
            "schemaVersion": "1.0",
            "kind": "run",
            "id": str(change.request_id),
            "setId": dataset["id"],
            "setName": dataset["name"],
            "setRevision": dataset["revision"],
            "createdAt": now(),
            "target": target,
            "_configuration": document,
            "items": [{**sample, "status": "PENDING"} for sample in dataset["samples"]],
        }
        return self.repo.commit(change, doc)

    @staticmethod
    def public_run(doc: dict):
        public = {k: v for k, v in doc.items() if not k.startswith("_")}
        # Keep the shared reverse-channel response below its 1 MB JSON limit.
        public["items"] = [
            {
                **item,
                **({"result": {**item["result"], "objects": []}} if item.get("result") else {}),
            }
            for item in doc["items"]
        ]
        return public

    async def run_item(self, request: RunItem):
        if self.lock.locked():
            raise ImageRecognitionError("已有验证图片正在运行，请稍后继续", 409)
        async with self.lock:
            doc = self.repo.get(str(request.id), "run")
            item = next((s for s in doc["items"] if s["id"] == str(request.sample_id)), None)
            if item is None:
                raise KeyError(request.sample_id)
            if item["status"] != "PENDING":
                return item
            item["status"] = "RUNNING"
            self.repo.put(doc)
            try:
                current = {
                    m["modelVersionId"]: m["sha256"] for m in self.gateway.models.summaries()
                }
                if any(
                    current.get(m["modelVersionId"]) != m["sha256"] for m in doc["target"]["models"]
                ):
                    raise ImageRecognitionError("模型版本已卸载或制品改变，请重新选择版本运行")
                result = await self.gateway.image_recognizer.recognize(
                    TaskImageRequest(
                        taskId=doc["target"]["taskId"],
                        imageBase64=base64.b64encode(self.repo.image(item)).decode(),
                    ),
                    doc["_configuration"],
                )
                if len(json.dumps(result).encode()) > 256 * 1024:
                    raise ImageRecognitionError(
                        "识别结果超过单图报告大小限制，请提高任务置信度后重试"
                    )
                item["status"], item["actualCount"] = compare(item["expected"], result)
                item["result"] = result
            except ImageRecognitionError as error:
                item.update(status="ERROR", error=str(error), diagnosticId=error.diagnostic_id)
            except (OSError, ValueError):
                item.update(status="ERROR", error="验证图片或版本不可用，请检查后重新运行")
            except asyncio.CancelledError:
                item.update(status="ERROR", error="识别已中断，请重新运行验证集")
                raise
            finally:
                item["finishedAt"] = now()
                self.repo.put(doc)
            return item
