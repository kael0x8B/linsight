#!/usr/bin/env python3
"""Assemble the evidence-backed LInsight Production Readiness Report."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts/production-readiness"
OUTPUT_JSON = ARTIFACTS / "production-readiness-report.json"
OUTPUT_MD = ARTIFACTS / "PRODUCTION_READINESS_REPORT.md"

PASS = "✅ PASS"
RISK = "⚠️ PASS_WITH_RISK"
FAIL = "❌ FAIL"
WAITING = "⏳ WAITING_FOR_FIELD_TEST"


def read_json(name: str) -> dict[str, Any]:
    path = ARTIFACTS / name
    if not path.is_file():
        return {"status": "MISSING", "reason": f"missing artifact: {path.relative_to(ROOT)}"}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"status": "INVALID"}
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "INVALID", "reason": str(error)}


def current_assessments(reports: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    model = reports["model"]
    release = reports["release"]
    security = reports["security"]
    model_violations = int(model.get("summary", {}).get("violations", 0))
    present_models = int(model.get("summary", {}).get("presentModelFiles", 0))
    declared_versions = int(model.get("summary", {}).get("declaredModelVersions", 0))
    release_blockers = release.get("blockers", [])
    critical_high = security.get("criticalAndHigh", [])
    model_ready = model_violations == 0 and declared_versions > 0 and present_models == declared_versions
    return [
        {"area": "算法", "capabilityState": "WAITING_FOR_FIELD_TEST", "status": WAITING,
         "basis": "逐算法统一 Benchmark 已就绪；真实数据集未提供，未生成 TP/FP/TN/FN。"},
        {"area": "模型", "capabilityState": "EXISTING_OK" if model_ready else "EXISTING_NEEDS_IMPROVEMENT",
         "status": WAITING if model_ready else FAIL,
         "basis": (
             f"活动目录 {present_models}/{declared_versions} 个模型文件完整，均已锁定 SHA256 并具备 Runtime Manifest；真实精度待现场验收。"
             if model_ready else
             f"生产目录权重 {present_models}/{declared_versions} 已存在并锁定 SHA256；仍有 {model_violations} 个输入规格或 Runtime Manifest 缺口。"
         )},
        {"area": "车辆识别", "capabilityState": "WAITING_FOR_FIELD_TEST", "status": WAITING,
         "basis": "保留 COCO 车辆检测和跟踪；不匹配的九类车型模型及其 8 个算法已移出当前交付范围，现有车辆能力仍需十二类场景视频验收。"},
        {"area": "车牌识别", "capabilityState": "WAITING_FOR_FIELD_TEST", "status": WAITING,
         "basis": "中文 LPRNet、FP32 YuNet 四角检测/矫正、OCR 置信度、多帧投票、稳定输出和车辆绑定已实现，制品已入库；现场视频待验。"},
        {"area": "性能", "capabilityState": "WAITING_FOR_FIELD_TEST", "status": WAITING,
         "basis": "已采集 preprocess/inference/postprocess/总延迟与 P50/P95/P99/FPS；尚无目标硬件实测。"},
        {"area": "边缘设备容量", "capabilityState": "WAITING_FOR_FIELD_TEST", "status": WAITING,
         "basis": "1/2/4/8/16/32 路逐级工具已就绪；最大稳定路数和推荐路数仍未知。"},
        {"area": "弱网", "capabilityState": "EXISTING_OK", "status": RISK,
         "basis": "已有 RK3566 30 分钟真实弱网证据通过，但不是本候选版本且未覆盖新增完整故障矩阵。"},
        {"area": "离线自治", "capabilityState": "EXISTING_OK", "status": RISK,
         "basis": "复用 SQLite WAL Outbox、重试、补传及去重；十类 Chaos 场景需在候选版本重跑。"},
        {"area": "数据可靠性", "capabilityState": "EXISTING_OK", "status": RISK,
         "basis": "已有事件/媒体零丢失、零重复证据；版本相关 exact-once、顺序和重启持久化需复验。"},
        {"area": "安全", "capabilityState": "WAITING_FOR_FIELD_TEST", "status": WAITING if not critical_high else FAIL,
         "basis": "依赖审计和容器静态检查已完成；最终镜像 CVE 与目标 OS/SSH/防火墙/端口待扫。"},
        {"area": "版本管理", "capabilityState": "EXISTING_NEEDS_IMPROVEMENT", "status": FAIL if release_blockers else PASS,
         "basis": f"发布清单工具与模型 SHA 已就绪；当前发布阻断项：{', '.join(release_blockers) or '无'}。"},
        {"area": "升级", "capabilityState": "EXISTING_OK", "status": RISK,
         "basis": "现有签名升级协议与版本状态机保留；目标硬件 V1→V2 尚未演练。"},
        {"area": "回滚", "capabilityState": "WAITING_FOR_FIELD_TEST", "status": WAITING,
         "basis": "失败注入及七项回滚后检查工具已就绪；尚未在隔离目标设备执行。"},
        {"area": "监控", "capabilityState": "WAITING_FOR_FIELD_TEST", "status": WAITING,
         "basis": "复用 Runtime Metrics，补齐 Prometheus、控制面投影、Grafana 与告警；现场通知链路待验。"},
        {"area": "运维", "capabilityState": "EXISTING_OK", "status": RISK,
         "basis": "Operations SOP 已覆盖每类告警；需由现场运维走查、确认联系人和处置权限。"},
    ]


def build() -> dict[str, Any]:
    reports = {
        "model": read_json("model-inventory.json"),
        "algorithm": read_json("algorithm-benchmark.json"),
        "capacity": read_json("edge-capacity-report.json"),
        "offline": read_json("offline-chaos-report.json"),
        "security": read_json("security-release-report.json"),
        "release": read_json("release-manifest.json"),
        "rollback": read_json("rollback-test-report.json"),
        "validation": read_json("validation-summary.json"),
    }
    assessments = current_assessments(reports)
    validation_passed = reports["validation"].get("status") in {"PASS", "PASS_WITH_RISK"}
    model_code_ready = int(reports["model"].get("summary", {}).get("violations", 0)) == 0
    phase = (
        "ENGINEERING_READY_WAITING_FOR_FIELD_ACCEPTANCE"
        if validation_passed and model_code_ready
        else "ENGINEERING_CLOSURE_IN_PROGRESS"
    )
    blockers = [
        "没有真实算法测试集和十二类车辆/车牌现场视频结果",
        "没有目标硬件容量、完整弱网矩阵、安全镜像/OS、升级回滚和告警闭环结果",
        "当前工作目录没有可解析 Git Commit，且生产镜像 Digest 未提供",
        "若客户合同仍要求已删除的 11 个模型族或 87 个算法，必须先重新引入可执行模型并完成验收；当前候选版本不再声明这些能力",
    ]
    return {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "productionReady": False,
        "phase": phase,
        "overallStatus": WAITING if validation_passed and model_code_ready else FAIL,
        "assessments": assessments,
        "blockingIssues": blockers,
        "sourceReports": {name: value.get("status", "UNKNOWN") for name, value in reports.items()},
        "answers": {
            "1": "按当前收缩后的交付范围，活动模型均具备确定性 Runtime 执行契约，代码层面已达到 Engineering Ready；仍不能替代现场精度和容量验收。",
            "2": "已补齐声明式 Runtime Manifest 全链路，移除 Java 业务 Adapter 映射，收敛 8 个重复逻辑模型；进一步移除 11 个不可执行模型族、87 个相关算法及 Pipeline，并修复 YOLO11 错误解码问题。",
            "3": "当前活动模型目录没有未解决的模型文件、SHA256、输入规格或 Runtime Manifest 问题。已删除能力只有在重新列入交付范围时才需要实现。",
            "4": "真实算法精度、十二类车辆/车牌视频、目标硬件容量、完整弱网矩阵、最终镜像与 OS 安全、升级回滚、Dashboard 告警闭环。",
            "5": "按现场 Runbook 依次做版本封版、模型验真、摄像头预检、逐算法基准、容量爬坡、弱网、安扫、升级回滚和告警演练。",
            "6": "任一保留算法现场阈值未达标、推荐路数未知、Critical/High 未清零、弱网丢失/重复、回滚失败，或合同仍要求已删除能力，都会阻止正式交付。",
            "7": "不能。没有真实现场证据时禁止判定 Production Ready。",
            "8": f"当前阶段：{phase}。通过全部现场验收并绑定到同一不可变版本后才能升级为 Production Ready。",
        },
    }


def render(report: dict[str, Any]) -> str:
    lines = [
        "# Production Readiness Report",
        "",
        f"- 生成时间：`{report['generatedAt']}`",
        f"- 总体状态：{report['overallStatus']}",
        f"- 当前阶段：`{report['phase']}`",
        "- Production Ready：**否**",
        "",
        "> 本报告不把工程测试、目录声明或历史版本证据冒充当前生产现场验收结果。",
        "",
        "## 能力评估",
        "",
        "| 领域 | 扫描判定 | 最终状态 | 依据 |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {item['area']} | `{item['capabilityState']}` | {item['status']} | {item['basis']} |"
        for item in report["assessments"]
    )
    lines.extend(["", "## 阻止正式交付的问题", ""])
    lines.extend(f"- {value}" for value in report["blockingIssues"])
    lines.extend(["", "## 八个结论", ""])
    questions = {
        "1": "当前代码层面是否已经具备生产条件？",
        "2": "当前哪些问题已经修复？",
        "3": "还有哪些代码问题没有解决？",
        "4": "哪些内容必须去客户现场才能验证？",
        "5": "明天如果部署到现场，具体需要执行哪些验收？",
        "6": "哪些问题会阻止正式交付？",
        "7": "当前项目能否判定为 Production Ready？",
        "8": "如果不能，目前处于什么阶段？",
    }
    for number, question in questions.items():
        lines.extend([f"### {number}. {question}", "", report["answers"][number], ""])
    lines.extend(
        [
            "## 证据入口",
            "",
            "- `artifacts/production-readiness/model-inventory.md`",
            "- `artifacts/production-readiness/algorithm-benchmark.json`",
            "- `artifacts/production-readiness/edge-capacity-report.json`",
            "- `artifacts/production-readiness/offline-chaos-report.json`",
            "- `artifacts/production-readiness/security-release-report.md`",
            "- `artifacts/production-readiness/release-manifest.json`",
            "- `artifacts/production-readiness/rollback-test-report.md`",
            "- `docs/PRODUCTION_FIELD_ACCEPTANCE_RUNBOOK.md`",
            "- `docs/OPERATIONS_SOP.md`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    report = build()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(render(report), encoding="utf-8")
    print(json.dumps({"status": report["overallStatus"], "phase": report["phase"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
