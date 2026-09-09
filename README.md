# LInsight AI 视频智能分析平台

本仓库已经完成平台基座初始化，并已进入“视频接入 → AI 分析 → 事件闭环 → 边缘自治”的纵向开发。当前包含摄像头/分组、节点注册与心跳、连通检测、ONVIF/RTSP 单路 HLS 预览、1/4/9/16 分屏与用户布局方案、模型资产门禁、受控 ONNX 适配器注册表、11 类算法 Pipeline、AI 任务生命周期、ROI/规则状态机、事件证据处置闭环、弱网持久化补传、Edge 签名升级/回滚，以及 V1.0 生产发布门禁。

## 基座组成

- 后端：Java 17、Spring Boot，基于 `yudao-cloud-mini v2026.07(jdk17/21)` 精简
- 前端：Vue 3、TypeScript、Vben Admin、Ant Design Vue，基于 `yudao-ui-admin-vben v2026.07` 精简
- 本地依赖：MySQL 8.4、Redis 7.4、MinIO

当前 Java 包名、Maven groupId/artifactId 和基座目录已统一为 `com.linsight` / `linsight-*`；上游菜单、推广入口、文档链接、演示业务和无关前端页面均已清理。

## 本地启动

依赖：Docker Desktop、JDK 17、Maven 3.9+、Corepack。

```bash
make infra
make runtime
make backend
make frontend
```

`make infra` 会在 MySQL 健康后自动以 `utf8mb4` 执行并登记尚未应用的 AI 视频增量迁移；也可以在
基础设施已运行时单独执行 `make migrate`。请勿使用未指定字符集的 `mysql < migration.sql` 导入。

实时预览由 Edge Agent 使用节点凭据主动连接控制面的反向预览通道，再调用网关本机仅监听
`127.0.0.1:48900` 的 Runtime。边缘 Runtime 负责将摄像头配置中的 RTSP 主/子码流转换为 HLS，
Java 控制面按节点代理播放会话和媒体，浏览器不会直接访问 Runtime 或看到 RTSP 凭据。
本地单进程开发仍需在 `.env` 中设置 `LINSIGHT_RUNTIME_ENABLED=true` 和非空的
`LINSIGHT_RUNTIME_API_KEY` 并启动 Runtime 与 Agent。ONVIF 摄像头和标准 RTSP 视频源使用同一预览链路；当前已实现的
浏览器传输协议是 HLS，WebRTC 仍是后续低延迟适配项。

`backend` 和 `frontend` 是常驻进程，建议分别在独立终端执行。检查状态：

```bash
make status
```

边缘初装/在线升级支持将离线 Python 依赖随源码一起通过 SSH 下发，避免现场 PyPI 不稳定导致失败。
构建机可执行 `uv run --with pip --no-project python scripts/prepare-node-wheelhouse.py --arch aarch64 --python-version 3.12`；
控制面按依赖契约、CPU 架构和 Python 小版本匹配与校验制品，预检显示是否离线就绪。
制品准备、发布和现场验证说明见 [节点部署依赖修复](docs/EDGE_DEPLOYMENT_DEPENDENCY_FIX_20260906.md)。

## 访问地址

| 服务 | 地址 | 本地凭据 |
| --- | --- | --- |
| 管理端 | http://127.0.0.1:5666 | `admin / admin123` |
| 后端 API | http://127.0.0.1:48888 | - |
| 接口文档 | http://127.0.0.1:48888/doc.html | - |
| MySQL | `127.0.0.1:23306/linsight` | `root / linsight_dev` |
| Redis | `127.0.0.1:26379` | 无密码 |
| MinIO Console | http://127.0.0.1:29001 | `linsight / linsight_minio_dev` |

端口和凭据可在根目录 `.env` 修改；模板见 `.env.example`。这些凭据仅用于本地开发，不可直接用于生产。

## 目录

```text
backend/     Java 后端基座
frontend/    Vue 管理端基座
deploy/      本地容器编排
scripts/     启动与状态脚本
docs/        基线、架构和开发计划
```

需求汇总见 [docs/REQUIREMENTS_SUMMARY.md](docs/REQUIREMENTS_SUMMARY.md)，详细基线见 [docs/BASELINE.md](docs/BASELINE.md)，开发计划与逐页规格见 [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)，所有新增代码必须遵循 [docs/ARCHITECTURE_AND_CODING_GUIDELINES.md](docs/ARCHITECTURE_AND_CODING_GUIDELINES.md)。

视频预览契约见 [docs/PREVIEW_AND_OVERLAY_PROTOCOL_V1.md](docs/PREVIEW_AND_OVERLAY_PROTOCOL_V1.md)，模型资产版本契约见 [docs/MODEL_ASSET_VERSION_CONTRACT_V1.md](docs/MODEL_ASSET_VERSION_CONTRACT_V1.md)，节点部署和单图推理契约见 [docs/MODEL_EXECUTION_PROTOCOL_V1.md](docs/MODEL_EXECUTION_PROTOCOL_V1.md)，算法 Pipeline 与任务生命周期契约见 [docs/ALGORITHM_PIPELINE_TASK_PROTOCOL_V1.md](docs/ALGORITHM_PIPELINE_TASK_PROTOCOL_V1.md)，规则、事件与区域入侵闭环契约见 [docs/RULE_EVENT_AREA_INTRUSION_PROTOCOL_V1.md](docs/RULE_EVENT_AREA_INTRUSION_PROTOCOL_V1.md)。

生产发布前执行 `make release-check`，并按 [docs/V1_RELEASE_RUNBOOK.md](docs/V1_RELEASE_RUNBOOK.md)
提供真实模型、现场弱网、负载、安全和回滚证据。缺少外部证据时门禁返回
`BLOCKED_EXTERNAL`，不会把工程契约测试误报为生产验收。

## 网关双入口

平台“边缘节点 → 网关工作台”与 `http://网关IP:48901` 共用设备执行配置，支持本地模型、参数、ROI、任务和识别结果管理；无需切换模式。网页随现有 Python Runtime 自动启动，节点安装和升级统一处理，无需逐台安装额外服务。构建、升级与独立登录见 [网关双入口说明](docs/GATEWAY_DUAL_ENTRY.md)。
