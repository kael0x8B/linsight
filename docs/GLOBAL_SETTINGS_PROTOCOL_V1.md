# LInsight AI 全局参数与版本下发协议 V1

## 1. 参数模型

当前 Schema 版本为 `1.0`，每次保存都创建不可变版本并记录字段级 diff：

| 字段 | 范围/语义 |
| --- | --- |
| `recordBeforeSeconds` | 0-120 秒，事件前录像窗口 |
| `recordAfterSeconds` | 0-120 秒，事件后录像窗口 |
| `defaultConfidence` | 0.01-1，默认检测置信度 |
| `defaultFps` | 0.1-10，默认分析 FPS |
| `evidenceStorageMode` | V1 固定为 `OBJECT_STORAGE` |
| `evidenceRetentionDays` | 1-3650 天，对象存储生命周期目标 |
| `notificationsEnabled` | Webhook 等通知的全局开关 |
| `nodeOfflineThresholdSeconds` | 10-3600 秒，节点心跳超时阈值 |

保存请求必须携带当前 `expectedVersionNo`。版本已变化时服务端拒绝覆盖，调用方应刷新并重新
比较。初始版本号为 0，默认值来自系统参数 `linsight.ai-video.settings.defaults`。

## 2. 生效范围

| 范围 | 行为 | 权限 |
| --- | --- | --- |
| `NEW_TASKS` | 只更新租户默认值；新建任务固化当前版本和 JSON 快照 | `ai-video:settings:update` |
| `GRAY` | 更新默认值，并向指定的运行中任务创建 `APPLY_TASK_SETTINGS` 命令 | 额外需要 `ai-video:settings:deploy` |
| `ALL_RUNNING` | 更新默认值，并向全部运行中任务创建命令 | 额外需要 `ai-video:settings:deploy` |

灰度范围必须至少选择一个任务，最多 100 个。任务保存“期望版本、已应用版本、设置快照”；
命令通过节点耐久命令通道下发。节点离线时版本状态为部分下发，不会把离线误报成成功。

## 3. Runtime 热更新

Edge Agent 收到 `APPLY_TASK_SETTINGS` 后调用 Runtime 的
`POST /v1/tasks/settings/apply`。运行任务无需重启即可更新置信度、分析 FPS、事件前后录像窗口
和证据 FPS；命令成功回执后控制面更新任务的已应用版本。

`notificationsEnabled` 由控制面 Webhook 入队读取，`nodeOfflineThresholdSeconds` 由中心节点
离线检测任务读取。`evidenceRetentionDays` 是对象存储生命周期目标，不授权控制面跨租户直接
删除文件；生产部署必须在对象存储 bucket 上配置匹配的生命周期规则。

## 4. 故障与恢复

- 重复命令按 `commandId/configVersion` 幂等执行。
- 下发失败保留任务的期望版本和原快照，节点恢复后可继续命令链路。
- `PARTIAL` 只表示部分运行任务未成功创建下发命令，不表示参数版本丢失。
- 回退通过保存一个内容等于旧版本的新版本完成，不原地修改或删除历史版本。
