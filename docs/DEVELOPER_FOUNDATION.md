# 开发者基础能力：SDK、错误诊断与独立评测

沿用 Java 模块化单体、Vue/Vben、Python Runtime/Edge Agent。算法发布属于 algorithm，模型资产属于 model，独立评测属于 task。通过所属领域 Service DTO 查询快照，不跨领域读取 Mapper。

## SDK 与错误协议

[快速入门](algorithm-packages/QUICKSTART.md) 提供 `init/check/run/pack`。CLI 与节点共用生产包校验和隔离运行器，没有新增执行框架或服务。

worker 保留 `error` 字段，新增有界 `diagnostic`；新版 host 兼容旧消息。host 生成诊断 ID 并补齐包 SHA256、版本和帧时间。任务沿原 `errorCode/errorMessage/diagnosticId` 及 `metrics.algorithmError` 上报，由原 `metricsSnapshot` JSON 持久化。任务监控和网关预览失败区显示定位信息；旧节点继续使用错误摘要，无需新增任务表字段。

| code | stage | 含义 |
| --- | --- | --- |
| ALGORITHM_IMPORT_FAILED | IMPORT | 语法、导入或包内依赖失败 |
| ALGORITHM_INITIALIZE_FAILED | INITIALIZE | Algorithm 构造失败 |
| ALGORITHM_PROCESS_FAILED | PROCESS | process 方法异常 |
| ALGORITHM_SDK_FAILED | SDK | 角色、裁剪、资源或模型调用失败 |
| ALGORITHM_OUTPUT_FAILED | OUTPUT | objects/observationValid 契约错误 |
| ALGORITHM_PROTOCOL_FAILED | PROTOCOL | 消息损坏或进程退出 |
| ALGORITHM_TIMEOUT | IMPORT / PROCESS | 初始化或帧执行超时 |

schemaVersion 为 `1.0`；最多 6 个包内 Python 相对文件位置，无包内位置时为空。任务场景另带 taskId/runId/configVersion。没有任意异常原文、系统调用栈、凭据、图像、源码或无限日志缓冲。失败和取消回收工作进程；错误继承 ValueError，兼容现有处理。

## 独立评测契约

入口沿用 `/ai-video/algorithm-validation`，使用 Vben Grid/Form/Drawer。查询复用 `ai-video:task:query`，记录复用 `ai-video:task:update`。选择测试任务同时需要查询权限。

- `POST /admin-api/ai-video/task/evaluation/create`：保存不可修改的人工评测，返回 ID。
- `GET /admin-api/ai-video/task/evaluation/page`：按 taskId/status 分页；列表不附带大快照。
- `GET /admin-api/ai-video/task/evaluation/get?id=...`：完整记录，可从页面导出 JSON。

请求必填：requestId、taskId、expectedConfigVersion、expectedGatewayRevision、measuredAtMillis；测试集版本/SHA256、证据引用、实测环境；metrics、thresholds、resourceUsage、cooldownDedupPass。完整字段见 `TaskEvaluationCreateReqVO` 和前端 `EvaluationCreate` 类型。

准确率/召回率为 0–1，CPU 为 0–100，计数不得为负。P95 允许高延迟，FPS 允许 0，失败测量同样保留。证据引用使用报告编号/对象键，禁止查询签名或凭据。服务端计算 PASS/FAIL 和 failedChecks；**PASS 仅表示本次人工指标满足本次阈值，不是发布批准或现场验收**。来源固定为 MANUAL_VIDEO，客户端不能提交通过状态。

记录包含任务绑定的具体 Pipeline/算法包、模型角色/版本/SHA256、规则、参数、全局设置以及节点最近上报环境。不会改用算法“当前发布版本”，不保存模型下载 URL。存在本地修改时另存白名单内的 gatewayConfiguration（含实际规则）、网关修订/应用修订，并按网关模型绑定保存模型快照。平台规则模板和网关规则分别显示。

任务行锁保护配置读取与记录；同时检查平台配置与网关修订。平台编辑尚未与网关报告对齐时拒绝关联，需先核对测试版本。快照标记 PLATFORM_TASK_AT_RECORDING 或 GATEWAY_REPORTED_AT_RECORDING。环境是记录时最近上报，人工测试时间不构成历史环境的自动证明。

幂等范围为 `(tenant_id, task_id, request_id)`：相同正文重试返回原 ID，不同正文冲突。已保存请求可在任务配置变更后重试。任务删除后历史仍可查询；不存在的任务不能新增。无编辑/删除 API，修正需新增并在备注引用原编号。查询与快照领域查询均使用现有租户隔离。

旧 `dag.acceptance` 仅保留兼容，不迁移成已验证记录；新页面不调用 Pipeline 保存/校验/发布 API。本轮证据引用仅留档，不自动验证外部文件，不从生产事件总数推导测试集准确率。

## 部署与回滚

先执行 `backend/sql/mysql/migrations/ai-video/V202610121000__independent_task_evaluations.sql`，再部署控制面与前端。新表不改写既有任务/Pipeline。Runtime 更新后才产生结构化诊断；新控制台兼容旧节点。

应用回滚保留新表和数据；只有表为空或已备份时才可删除，详见迁移文件头。恢复旧评测页面会恢复其旧 Pipeline 发布行为。SDK 无常驻服务，移除 CLI 不影响已部署算法包。

## 回归入口

```bash
cd runtime
.venv/bin/python -m pytest tests/test_developer_sdk.py tests/test_algorithm_packages.py \
  tests/test_task_manager.py tests/test_image_validation.py tests/test_model_pool.py \
  tests/test_gateway_capacity_preflight.py tests/test_gateway_event_stream.py
cd ../backend
# JDK 17
mvn -pl linsight-module-ai-video/linsight-module-ai-video-server -am test
cd ..
bash scripts/tests/task-evaluation-migration.sh
cd frontend
# Node 24，仓库声明的 pnpm；浏览器回归需先启动开发页面
corepack pnpm -F @linsight/console typecheck
corepack pnpm exec vitest run tests/node-task-configuration.test.ts tests/node-image-validation.test.ts
node tests/e2e/task-evaluation.mjs
corepack pnpm build:antd
```

浏览器拦截全部管理 API（包括登录），覆盖入门、空态、保存重试、失败指标、快照导出、历史、错误恢复及权限，不访问现场任务。Java 覆盖具体版本关联、网关修订、失败证据、幂等冲突和租户 SQL 拦截。MySQL 8.4 使用临时容器验证新库/重复迁移、JSON、租户内唯一约束和索引，不改动业务库，不代替生产迁移演练。

## 第一轮交付与验证记录

本轮变更说明、383 项 Java / 97 项 Runtime / 38 项前端测试结果、真实端到端证据、迁移/回滚和本地启用状态，统一见 [第一轮变更与回归记录](DEVELOPER_FOUNDATION_VERIFICATION.md)；可审计的结果与证据摘要见 [JSON 验证记录](developer-foundation-verification.json)。
