# 节点日志治理（2026-09-06）

## 原因与现场处理

节点 1 的 root logger 在 INFO 级别采集了 httpx 成功请求日志，连日志上传自身也产生下一批日志；心跳和未变化的任务状态也持续记录。初次统计成功 HTTP 请求 566,539 条、心跳 5,982 条，构成绝大部分增长。

本次只清理 tenant_id=1、node_id=1、EDGE_AGENT 的 INFO/DEBUG 成功 HTTP 2xx 与成功心跳，先固定最大 ID，再导出、验证每条 INSERT 数量与 gzip 完整性，最后每批 5,000 条删除。两次归档共 572,779 条，WARN/ERROR 和业务日志未纳入该清理。清理后约 1.38 万条（实时变化）。

归档位于 `artifacts/node-log-hygiene/node-1-routine-before-587992.sql.gz`（572,674 条，约 26 MB）与 `node-1-routine-before-588160.sql.gz`（105 条），权限 0600。条数和 SHA256 分别记录于同目录 `cleanup-result-initial.json`、`cleanup-result.json`。如需恢复，先在隔离数据库检验归档，再向目标库导入 gzip 内 SQL；导入保留原 ID，应先检查主键冲突。归档含日志信息，应按现场备份权限和生命周期管理。

## 已实现策略

- 服务端入库前过滤 EDGE_AGENT INFO/DEBUG 成功 HTTP 2xx 与成功心跳；旧 Agent 无需升级即可停止这些噪声入库，HTTP 失败及 WARN/ERROR 保留。
- 新 Agent 将 httpx/httpcore 提升至 WARNING、成功心跳降为 DEBUG；任务状态只在状态、runId 或错误变化时记录。相同 WARN/ERROR 首条立即投递，随后一分钟内重复次数汇总成新日志，不修改已投递条目，保持重试 ACK 一致性。去重缓存有容量上限。
- 默认 DEBUG/INFO/WARN/ERROR 保留 1/3/7/14 天，每分钟执行有界物理清理，每级最多 10 批、每批 5,000 条。新增 `(level, logged_at, id)` 索引支撑清理，避免每小时只删 5,000 条追不上写入。
- 页面时间显示为可读日期，自动刷新降为 10 秒；暂停、后台页和请求未完成时不重复刷新。

服务端可通过 `linsight.ai-video.node-log` 配置 `debug-retention-days`、`info-retention-days`、`warn-retention-days`、`error-retention-days`、`cleanup-interval-ms`、`cleanup-batch-size`、`cleanup-max-batches`。保留天数 1–365；批量 100–10,000；批次 1–100。Agent 的 `log_repeat_window_seconds` 默认 60，范围 10–600 秒。保留策略会删除过期日志，需按运维审计需求调整。

## 验证与部署边界

本机控制面已应用迁移 `V202609060950__index_node_log_retention.sql` 并重新启动，健康检查 UP。真实节点继续心跳、上传日志期间，在 ID 588160 之后未新增成功请求或成功心跳；索引 EXPLAIN 使用 `idx_ai_node_log_retention`。现场节点仍为 Agent 0.1.0：源头降噪与重复告警汇总代码待其升级，当前立即生效的是服务端过滤和保留清理。

Java AI 模块 125 项测试通过，Runtime 131 项测试通过，修改的 Python 文件 Ruff 通过；前端类型检查与生产构建通过。验证覆盖成功噪声过滤、失败保留、有界清理、重复告警汇总与重试稳定性。证据保存在 `artifacts/node-log-hygiene/`。本次没有将模拟测试视为现场 Agent 升级验证。
