# Rule、Event 与区域入侵闭环协议 V1

本文冻结 Story 8、9、10 的控制面/计算面边界。Java 控制面拥有规则版本、任务绑定、事件、处置、证据索引与 outbox 真值；Edge Agent 负责耐久命令和断网补传；AI Runtime 独占分析拉流、推理、跟踪、规则状态机与证据帧缓存。Runtime 和 Agent 不连接控制面数据库。

## 1. Rule AST 与任务绑定

- ROI 使用 `[0,1]` 归一化坐标，多边形至少三个不重复点，必须在边界内、无自交且面积达到下限。
- AST 根携带 `schemaVersion: "1.0"`；逻辑节点只允许 `AND/OR/NOT`，条件节点只允许白名单字段和操作符。
- RuleVersion 一经发布不可覆盖。任务保存 `ruleId + ruleVersionId`，启动时再次校验版本属于该规则且已经发布。
- dry-run 只消费显式帧样本并返回确定性状态轨迹，不写业务事件。

Runtime 对每个 `cameraId + taskId + eventType + trackId` 维护状态：

```text
DETECTED → PENDING → CONFIRMED → ALARM → COOLDOWN → RECOVERED → CLOSED
```

N/M 帧、持续时长和冷却均来自已发布规则快照。`dedupKey` 标识一个尚未结束的活动事件；每次告警活动另有稳定 `sourceEventId`，不得把两者混用。进入 `CLOSED` 或人工标记 `FALSE_POSITIVE` 后才释放活动去重键。
Runtime 是规则窗口和轨迹去重的唯一所有者；控制面只以 `sourceEventId` 做创建幂等，不得再次用
`dedupKey` 合并事件。否则离线补传时，同一轨迹的连续告警活动会在状态转换上传前被错误折叠。

## 2. Event 与证据

Runtime 在 `ALARM` 时立即把事件事实与截图写入本地 SQLite WAL 队列；内存环形缓冲保留默认告警前 10 秒帧，告警后继续采集 20 秒，再使用 FFmpeg 生成 MP4。Edge Agent 的投递顺序为：

1. 按 `sourceEventId` 幂等创建中心事件；
2. 上传截图；
3. 视频完成后按内容 SHA-256 幂等上传；
4. 上报 `RECOVERED/CLOSED` 转移；
5. 仅在中心确认后删除本地待投递记录。

证据状态为 `PENDING → PARTIAL → READY`，任一媒体持久化失败则为 `FAILED`。对象存储只保存媒体，数据库保存事实、SHA-256、时间窗口和对象引用；浏览器只取得短期签名地址。

录像按实际观察到的帧时间戳合成，帧间隔写入 FFmpeg concat 时间轴；配置的录像 FPS 仅控制输出编码频率。低于目标 FPS 的推理吞吐不得使录像加速。预录环形缓存保留窗口边界前的最近一帧，末帧只保持一个输出帧间隔；任务刚启动或发生断流时，以实际可用画面为准，不补造缺失的现场过程。

事件创建、证据更新和处置在 `ai_event_outbox` 生成版本化消息。消息体固定包含 `type/version/messageId/occurredAt/data`；事务提交后尝试发送，失败由租户感知的调度器指数退避重试。前端只消费外层 `ai-video-event` 主题并重新读取服务端真值。

## 3. 区域入侵纵向样板

受控 Pipeline 为：

```text
detector.person → tracker.iou → rule.area-intrusion
```

启动门禁要求 Person 模型版本 `executionStatus=READY`、Pipeline `validationStatus=VALID`、RuleVersion 已发布、摄像头与节点可用。检测框使用脚底中心点或规则指定判断点与 ROI 做命中判定；同一 track 在活动窗口内只产生一个中心事件。

自动化测试使用确定性帧序列验证跟踪、N/M 帧、持续、冷却、恢复、去重、SQLite 重启恢复和真实 MP4 编码。自动化结果不是现场精度结论；物理验收必须记录 RTSP、模型版本、事件级 Precision/Recall、每路每小时误报、端到端延迟和资源占用。

## 4. 运维与恢复

- 数据库迁移按 `utf8mb4` 执行并登记 SHA-256；已登记文件禁止编辑。
- 控制面暂时不可用时 Agent 保留本地队列并重试，不重新生成 `sourceEventId`。
- 重复创建、重复媒体和重复状态转移必须返回既有结果或安全忽略。
- 控制面明确返回“事件不存在”且 Runtime 已无对应待传事件时，Agent 必须把状态转换原文、重试次数、
  原因和隔离时间原子移入 `dead_letter_transition`，禁止静默删除；待传事件仍存在时禁止隔离并继续退避。
- 现场弱网验收允许保留历史死信基线，但采集期间 `deadLetterTransitions` 不得增长；新增死信视为数据完整性失败。
- 媒体路径在 Agent 读取前必须解析为 Runtime 数据根目录内的真实路径，拒绝 `..` 和符号链接逃逸。
- 规则发布后如需修正，创建新版本并通过任务 `configVersion` 下发，不修改历史事件快照。
