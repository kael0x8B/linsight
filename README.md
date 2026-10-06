# LInsight AI 视频智能分析平台

本仓库已经完成平台基座初始化，并已进入“视频接入 → AI 分析 → 事件闭环 → 边缘自治”的纵向开发。当前包含摄像头/分组、节点注册与心跳、连通检测、ONVIF/RTSP 子码流 WebRTC 预览、1/4/9/16 分屏与用户布局方案、模型资产门禁、受控 ONNX/RKNN 适配器、算法 Pipeline 与可部署算法包、AI 任务生命周期、ROI/规则状态机、事件证据处置闭环、弱网持久化补传、Edge 签名升级/回滚，以及 V1.0 生产发布门禁。

## 基座组成

- 后端：Java 17、Spring Boot，基于 `yudao-cloud-mini v2026.07(jdk17/21)` 精简
- 前端：Vue 3、TypeScript、Vben Admin、Ant Design Vue，基于 `yudao-ui-admin-vben v2026.07` 精简
- 本地依赖：MySQL 8.4、Redis 7.4、MinIO

当前 Java 包名、Maven groupId/artifactId 和基座目录已统一为 `com.linsight` / `linsight-*`；上游菜单、推广入口、文档链接、演示业务和无关前端页面均已清理。

## 本地启动

依赖：Docker、JDK 17、Maven 3.9+、Node.js 22.18+（或 24）、Corepack、Python 3.12/3.13、uv。
从干净克隆启动前，先安装前端和 Runtime 依赖，并配置本机密钥：

```bash
make init
uv sync --project runtime --python 3.12
cd frontend && corepack pnpm@11.7.0 install --frozen-lockfile && cd ..
```

在 `.env` 中设置 `LINSIGHT_RUNTIME_ENABLED=true` 和随机生成的非空
`LINSIGHT_RUNTIME_API_KEY`，不要提交 `.env`。边缘节点部署或升级前还需执行
`make gateway-console`，生成已校验的网页制品。随后分别在独立终端启动：

```bash
make model-assets-init
make runtime
make backend
make frontend
```

首次部署使用 `make model-assets-init`：启动 MySQL/Redis/MinIO、执行增量 SQL，并把随仓库交付的
15 个当前发布模型的权重、执行契约和版本导入 MinIO/MySQL，无需访问外部模型下载站。
模型中心默认展示模型资产；新环境的执行状态需在目标节点部署和单图测试后确认。
已运行基础设施的环境可执行 `make model-assets-sync` 补齐模型。
跨机器部署节点时，先在 `.env` 配置 `LINSIGHT_MODEL_PUBLIC_ENDPOINT` 为节点可访问的 MinIO 地址。
步骤和硬件格式说明见 [模型资产初始化说明](deploy/model-assets/README.md)。

`make infra` 会在 MySQL 健康后自动以 `utf8mb4` 执行并登记尚未应用的 AI 视频增量迁移；也可以在
基础设施已运行时单独执行 `make migrate`。请勿使用未指定字符集的 `mysql < migration.sql` 导入。

实时预览由页面创建 recvonly WebRTC Offer，经 Java 控制面和 Edge Agent 的反向通道交给网关本机仅监听
`127.0.0.1:48900` 的 Runtime 协商。媒体通过 ICE/DTLS-SRTP 从边缘节点送达浏览器，控制面不代理逐帧媒体；
Overlay 使用同源 `streamId/sourcePts/frameKey` 与播放帧对齐。旧 HLS 接口只作为显式回滚路径保留，
不会在 WebRTC 失败时静默降级。浏览器不会获得 RTSP 地址、Runtime 密钥或节点凭据。
本地单进程开发还需启动 Runtime 与 Agent。ONVIF 摄像头和标准 RTSP 视频源都使用已保存的
子 RTSP 码流进入同一 WebRTC 预览链路。

`backend` 和 `frontend` 是常驻进程，建议分别在独立终端执行。检查状态：

```bash
make status
```

边缘初装/在线升级支持将离线 Python 依赖和已校验的网关控制台制品随 Runtime 源码一起通过 SSH 下发，
避免现场 PyPI 不稳定或静态资源版本漂移导致失败。首次部署或前端变更后先执行 `make gateway-console`；
构建输出位于被 Git 忽略的 `runtime/gateway-console/`，其中 manifest 固定制品 SHA256 和逐文件摘要。
构建机可执行 `uv run --with pip --no-project python scripts/prepare-node-wheelhouse.py --arch aarch64 --python-version 3.12`；
控制面按依赖契约、CPU 架构和 Python 小版本匹配与校验制品，预检显示是否离线就绪。
制品准备、发布和现场验证说明见 [边缘节点部署说明](docs/EDGE_DEPLOYMENT_GUIDE.md)。

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

项目文档入口见 [文档导航](docs/README.md)，按规范、协议、使用和运维分类。

| 目录 | 用途 | 生产部署时如何处理 |
| --- | --- | --- |
| `frontend/` | Vue 管理端源码、共享组件和构建配置 | 构建后部署 `apps/web-antd/dist/`；源码和 `node_modules/` 留在开发/构建机 |
| `backend/` | Java 后端、公共框架、权限系统和数据库迁移 | 部署打包后的服务 JAR，保留初始化/增量 SQL 供部署和升级使用 |
| `runtime/` | Python AI 推理服务和边缘 Agent | 节点安装/升级需要源码、依赖声明、算法包及已校验的网关控制台制品；`deployment-wheels/` 用于离线安装 |
| `deploy/` | 容器编排、监控配置和模型转换环境 | 按部署场景选用；当前 `docker-compose.dev.yml` 是本地开发配置 |
| `scripts/` | 启动、数据库迁移、模型同步、节点打包和发布检查脚本 | 保留部署与运维所需脚本 |
| `docs/` | 架构、接口协议、开发计划和运维手册 | 保留在源码仓库及交付文档中，无需放入服务运行目录 |
| `acceptance/` | 算法、容量、断网和回滚验收的配置模板与数据集说明 | 验收/发布检查需要，无需随服务启动 |
| `evidence/` | 现场验收报告、原始附件和证据清单 | 作为发布验收记录保存；不属于可以随意删除的缓存 |
| `artifacts/` | 检查报告、模型实验结果和生成的交付产物 | 发布检查会读取其中的报告；历史产物可归档，无需整目录部署 |
| `var/` | 本机下载的模型资产、日志及运行数据 | 根据实际配置保留或迁移；模型资产不能当作临时文件删除 |
| `.codex-tmp/` | 开发调试临时文件、试验构建和回滚备份 | 不属于标准部署目录；清理前确认没有进程从中运行，并归档有用备份 |

`runtime/var/` 同样可能包含本机运行数据。网关本地管理页面不再以数百个带 hash 的生成文件纳入源码；
`make gateway-console` 会生成 `runtime/gateway-console/manifest.json`、内容寻址的 `tar.gz` 制品和本地
`current/` 展开目录。该目录可重建但部署前必须存在并通过摘要校验。前后端测试目录继续保留用于回归。

可重新生成的缓存包括 `.pytest_cache/`、`.ruff_cache/`、`__pycache__/` 和 `frontend/.turbo/`。
根目录偶尔出现的 `node_modules/.vite/vitest/` 只是测试结果缓存；真正的前端依赖位于
`frontend/node_modules/`。不要在服务运行时删除其依赖、JAR、网页资源或 Python 虚拟环境。

需求汇总见 [docs/REQUIREMENTS_SUMMARY.md](docs/REQUIREMENTS_SUMMARY.md)，详细基线见 [docs/BASELINE.md](docs/BASELINE.md)，开发计划与逐页规格见 [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)，所有新增代码必须遵循 [docs/ARCHITECTURE_AND_CODING_GUIDELINES.md](docs/ARCHITECTURE_AND_CODING_GUIDELINES.md)。

当前 WebRTC 与 Overlay 契约见 [docs/PREVIEW_AND_OVERLAY_PROTOCOL_V2.md](docs/PREVIEW_AND_OVERLAY_PROTOCOL_V2.md)，
[V1 HLS 契约](docs/PREVIEW_AND_OVERLAY_PROTOCOL_V1.md)仅用于显式回滚与历史兼容。模型资产版本契约见 [docs/MODEL_ASSET_VERSION_CONTRACT_V1.md](docs/MODEL_ASSET_VERSION_CONTRACT_V1.md)，节点部署和单图推理契约见 [docs/MODEL_EXECUTION_PROTOCOL_V1.md](docs/MODEL_EXECUTION_PROTOCOL_V1.md)，算法 Pipeline 与任务生命周期契约见 [docs/ALGORITHM_PIPELINE_TASK_PROTOCOL_V1.md](docs/ALGORITHM_PIPELINE_TASK_PROTOCOL_V1.md)，规则、事件与区域入侵闭环契约见 [docs/RULE_EVENT_AREA_INTRUSION_PROTOCOL_V1.md](docs/RULE_EVENT_AREA_INTRUSION_PROTOCOL_V1.md)。

生产发布前执行 `make release-check`，并按 [docs/V1_RELEASE_RUNBOOK.md](docs/V1_RELEASE_RUNBOOK.md)
提供真实模型、现场弱网、负载、安全和回滚证据。缺少外部证据时门禁返回
`BLOCKED_EXTERNAL`，不会把工程契约测试误报为生产验收。

## 网关双入口

平台“边缘节点 → 网关工作台”与 `http://网关IP:48901` 共用设备执行配置，支持本地模型、参数、ROI、任务和识别结果管理；无需切换模式。网页随现有 Python Runtime 自动启动，节点安装和升级统一处理，无需逐台安装额外服务。构建、升级与独立登录见 [网关双入口说明](docs/GATEWAY_DUAL_ENTRY.md)。
