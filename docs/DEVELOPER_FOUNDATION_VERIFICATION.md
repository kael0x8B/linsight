# 开发者基础能力第一轮：变更与回归记录

验证日期：2026-10-12（Asia/Shanghai）。开发分支：`codex/developer-foundation`，基线：`b9ed4eb`。

本轮面向通用视频 AI 平台与算法开发者，完成从本地算法调试、运行故障定位到独立评测留档的流程。代码沿用 Java 模块化单体、Vue/Vben 和 Python Runtime/Edge Agent；本地部署、真实接口和页面验证均通过。结果摘要同时保存在 [JSON 验证记录](developer-foundation-verification.json)。

## 变更说明

| 能力 | 本轮交付 | 实现位置 |
| --- | --- | --- |
| SDK 快速入门 | `init/check/run/pack`、示例与 golden fixture、明确退出码、可重复打包；CLI 与实际节点共用包校验器和运行器 | `runtime/ai_runtime/sdk.py`；[快速入门](algorithm-packages/QUICKSTART.md) |
| 结构化错误 | 错误阶段、类型、包版本/SHA256、包内文件/行号及诊断 ID；兼容旧 `error` 响应；失败与取消回收 worker | `runtime/ai_runtime/app/capability/`、`task/manager.py` |
| 错误展示 | 沿原任务指标上报链路展示定位信息，覆盖任务监控与网关预览 | 前端 `components/ai-video/algorithm-diagnostic.*`、任务页与网关工作台 |
| 独立评测 | 新增不可修改的人工评测记录，保留测试集、指标/阈值、失败项、任务配置、Pipeline、模型、规则及节点快照 | task Controller → Service → Mapper；`ai_task_evaluation` |
| 评测工作台 | 查询、录入、详情、JSON 导出、保存重试与权限/空态/错误态；评测保存不再发布 Pipeline | `/ai-video/algorithm-validation`，沿用原“视频识别验收”菜单 |
| 本地启动修复 | worker 改变工作目录前将算法目录解析为绝对路径，修复默认相对数据目录下的导入失败 | `PackageRunner` 与真实子进程回归用例 |

评测属于 task，通过所属领域的 Service DTO 获取算法、模型与节点快照。查询复用 `ai-video:task:query`，保存复用 `ai-video:task:update`；按租户隔离并保留审计字段。相同请求重试返回原 ID，不同正文复用请求号会冲突；新增记录同时校验平台配置版本与网关修订。完整 API、数据边界与错误码见 [功能契约](DEVELOPER_FOUNDATION.md)。

## 自动化回归结果

这些结果来自本轮实现与本地启用期间的实际执行，提交整理阶段核对了原始日志、Surefire XML 和端到端输出。

| 验证范围 | 结果 | 覆盖重点 |
| --- | --- | --- |
| Java AI 视频模块及依赖 reactor | **383 项通过**，0 失败/错误/跳过；受影响 reactor 成功 | 具体 Pipeline 版本、网关配置快照、失效版本、失败指标、幂等与冲突、租户 SQL、权限与架构约束 |
| Runtime 相关回归 | **97 项通过** | SDK fixture/golden/打包、结构化错误各阶段、超时、旧协议兼容、worker 回收、相对数据目录，以及任务、模型、图像验证、网关容量与事件流 |
| 前端定向 Vitest | **38 项通过**，4 个测试文件 | 节点任务配置、图像验证、模型绑定、算法部署 |
| 前端静态验证 | TypeScript、变更文件 ESLint、Oxfmt 通过 | 评测 API/页面、错误组件及浏览器脚本 |
| Python 静态验证 | Ruff 通过 | SDK、诊断、worker、runner 及新增测试 |
| 构建 | JDK 17 Maven install、前端生产构建、网关网页制品构建通过 | 后端 JAR、平台网页、Runtime 内的网关网页 |
| MySQL 8.4 临时容器 | 通过 | 新库迁移、重复执行、JSON 持久化、跨租户相同请求号、同租户重复拒绝、4 个索引 |
| 隔离浏览器回归 | 通过 | 入门、空态、失败保存重试、指标失败、快照导出、历史、列表故障恢复、查询/保存权限 |
| 真实本地浏览器回归 | 通过，0 页面异常 | 正常登录、真实诊断、真实数据库保存、已提交响应丢失后的重试、历史与导出、冲突/旧配置/跨租户拒绝 |

Java 383 项指 `linsight-module-ai-video-server` 的测试统计。Runtime 97 项包含真实启动发现的相对目录问题修复后的回归。前端 Vitest 与浏览器验证分别记账，不将 UI 场景数算作单元测试数。

## 真实本地链路

环境：macOS ARM64，JDK 17、Node 24.18.0 / pnpm 11.7.0、Python 3.13.5、MySQL 8.4。使用专用开发节点 #9、摄像头 #26、任务 #47，以及已发布 ONNX 模型版本 #18。视频来自 `127.0.0.1` 上的 RTSP 测试图。

| 步骤 | 实际结果 |
| --- | --- |
| SDK → 算法中心 | 生成示例、fixture 比较、打包、真实上传和发布成功，正常包 `developer-e2e-person@0.1.0` |
| 模型 → 视频任务 | 真实下发模型部署命令，RTSP 解码与 ONNX CPU 推理成功；平台收到 13 帧分析结果，执行后端 `CPU`、解码后端 `SOFTWARE_PYAV` |
| 故障 → 控制台 | 专用 `0.1.1-e2e-failure` 包在 `process` 中抛错；Runtime → Agent → Java → 页面显示 `ALGORITHM_PROCESS_FAILED`、`PROCESS`、`processor.py:4`、包摘要与诊断 ID；异常原文未泄漏 |
| 保存响应丢失 → 重试 | 第一次 POST 由真实服务器完成后丢弃响应，页面重试相同正文；两次均返回记录 **#1**，数据库仅保留一行 |
| 失败指标 → 导出 | 人工边界样本 P95=8500 ms、FPS=0 被保留，后端判定 `FAIL`，失败项为 `endToEndP95Ms`、`averageFps`；导出与历史查询一致 |
| 错误与权限 | 相同请求号不同正文返回 `1020003013`；旧配置返回 `1020003012`；跨租户查询返回 `403`；评测页面发起的 Pipeline 写操作为 0 |
| 版本变更 → 历史不变 | 测试任务恢复正常包并更新到配置 v3；记录仍保留配置 v2 / Pipeline #82676，完整 JSON 未改变；原始保存请求再次重试仍返回 #1 |
| 清理 | 测试任务处于 `STOPPED`，临时 RTSP 容器与发布进程停止，Runtime 活跃任务/视频流均为 0；本地开发 Agent 继续服务；原有 9 个任务的配置核对一致 |

SDK fixture 是固定模型响应；真实 RTSP 阶段执行了实际 ONNX 模型，但视频是测试图。评测 #1 的人工指标明确标记为 `E2E_BOUNDARY_FIXTURE`，用于接口边界验证，**不代表模型准确率、现场性能或生产验收**。本轮不包含自动视频指标计算、现场节点升级或新一轮生产验收。

## 迁移、启用与回滚

1. 本地数据库已通过 `mysqldump --single-transaction` 备份至 `var/backups/developer-foundation/before-V202610121000.sql`，权限 `0600`。
2. 使用既有 `scripts/apply-ai-video-migrations.sh`，以 `utf8mb4` 应用并登记 `V202610121000__independent_task_evaluations.sql`；既有迁移校验和匹配。实际库确认主键、租户/任务/请求唯一约束及两个查询索引。
3. JDK 17 重新构建并启动后端；重启前端；安装 editable Runtime 与 `linsight-sdk` 并启动 Runtime；重新生成网关网页制品。
4. 启用收尾时，后端 48888 / Runtime 48900 健康为 `UP`，前端 5666 / 网关入口 48901 返回 HTTP 200。进程 PID 与日志位于 `var/log/developer-foundation/`。

应用回滚时保留 `ai_task_evaluation` 表和已保存记录。迁移只新增表，不改写既有任务/Pipeline，也不将旧 `dag.acceptance` 转换为已验证记录。新版控制台兼容旧 Runtime 的错误摘要；结构化定位需要新版 Runtime。恢复旧页面会恢复其原有 Pipeline 发布行为，应按实际使用场景评估。

本次网关网页制品 SHA256：`b69685bc8e9ffa4bbac35826c5af600f2a7be98691b1978721ff431be7fca945`。

## 回归命令与复核入口

在仓库使用 JDK 17、Node 24 与声明的 pnpm；Runtime 测试依赖已安装后执行：

```bash
cd backend
mvn -pl linsight-module-ai-video/linsight-module-ai-video-server -am test
cd ../runtime
.venv/bin/python -m pytest tests/test_developer_sdk.py tests/test_algorithm_packages.py \
  tests/test_task_manager.py tests/test_image_validation.py tests/test_model_pool.py \
  tests/test_gateway_capacity_preflight.py tests/test_gateway_event_stream.py
cd ..
bash scripts/tests/task-evaluation-migration.sh
cd frontend
corepack pnpm@11.7.0 -F @linsight/console typecheck
corepack pnpm@11.7.0 exec vitest run tests/node-task-configuration.test.ts \
  tests/node-image-validation.test.ts tests/node-model-bindings.test.ts \
  tests/node-algorithm-deployment.test.ts
node tests/e2e/task-evaluation.mjs
corepack pnpm@11.7.0 build:antd
cd ..
bash scripts/build-gateway-console.sh
```

浏览器用例依赖已启动的前端与本机 Chrome。`task-evaluation.mjs` 拦截全部管理 API。`task-evaluation-live.mjs` 访问真实本地服务，要求显式设置 `LINSIGHT_LIVE_E2E=1`、`LINSIGHT_E2E_PASSWORD`、`LINSIGHT_E2E_STATE`，并先准备 `developer-e2e-*` 专用测试任务：故障包在第 4 行抛错，节点/模型已部署，测试流可用。state JSON 提供 `taskId`、`nodeId`、`diagnosticPackage.pipelineVersionId`，同目录保留 `sdk-result.json`。该用例会写入一条人工边界样本记录，完成后需停止测试任务和测试流、恢复正常包。

本次本地 state 为 `output/developer-foundation/live/state.json`；任务已恢复正常包并停止，因此重复 Live 用例前需要重新准备故障阶段，不能直接把已清理状态当作正在运行的故障任务。

原始证据位于本地忽略目录 `output/developer-foundation/live/`：正常运行、故障诊断、评测导出、浏览器结果、收尾状态和两张页面截图。版本库保存本记录、脱敏 JSON 摘要及原始文件 SHA256；数据库备份、凭据、原始日志、模型和构建产物继续留在本地。JSON 中的哈希可用于核对现有原始文件，原始文件不随 Git 分发。
