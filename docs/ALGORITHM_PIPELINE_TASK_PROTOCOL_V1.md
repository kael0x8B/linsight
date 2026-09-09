# 算法、Pipeline 与 AI 任务协议 V1

本文冻结 Story 7 的控制面与计算面边界。控制面负责算法资产、不可变 Pipeline 版本、任务配置、状态与运行记录；Edge Agent 只执行耐久命令；AI Runtime 负责拉流、共享解码、抽帧和受控推理，不连接控制面数据库。

## 1. 算法与 Pipeline

- `ai_algorithm.code` 是稳定业务编码，创建后不可修改。
- Pipeline 每次保存都会创建新的草稿版本；已发布版本不可原地修改。
- DAG 协议版本仍为 `1.0`。除 `DETECTOR`、`TRACKER`、`CLASSIFIER`、`OCR`、`RULE` 外，
  以向后兼容方式增加 `POSE`、`SEGMENTER`、`RECOGNIZER`、`QUALITY` 受控节点；未知节点和任意代码仍被拒绝。
- 节点 ID 必须唯一，边的起止节点必须存在，拓扑校验必须无环。
- 发布前必须通过服务端 DAG 校验。算法的 `current_pipeline_version_id` 仅指向已发布版本。
- Runtime 通过受控适配器注册表支持原 12 个预置模型及通用 COCO、统一 PPE、吸烟/手机、
  火焰/烟雾、垃圾/杂物和车型检测的标准 `[N,6]` ONNX 输出。节点类型和能力键格式受控，
  业务能力键由算法资产与 Pipeline 动态登记，不再维护逐能力固定白名单。DAG 的 `acceptance.status` 会保留外部权重、许可证、专用 Adapter、OCR
  投票、车辆模型或现场精度阻断，不能仅凭 Pipeline 已发布宣布业务验收完成。

示例：

```json
{
  "schemaVersion": "1.0",
  "nodes": [
    { "id": "person-detector", "type": "DETECTOR", "capabilityKey": "detector.person" }
  ],
  "edges": []
}
```

## 2. 任务配置与门禁

任务绑定摄像头、算法、已发布 Pipeline 版本、一个或多个已发布且执行状态为 `READY` 的模型版本，以及可用节点。`modelBindings` 使用 Pipeline 节点 ID 作为键；节点声明 `modelId` 时必须绑定该模型的版本，否则回退到算法默认模型。所有绑定版本在目标节点的部署状态都必须为 `READY`。

任务参数使用 `schemaVersion: 1.0`。支持 `confidence`、`nmsThreshold`、`inputWidth`、
`inputHeight`、`sampleFps` 和 `classFilter`；同一个 COCO 80 类模型可通过 `classFilter`
承载人员、车辆、动物、手机、背包等多个算法。规则、事件与证据按后续已交付协议执行。

任务配置有独立递增的 `configVersion`。仅 `DRAFT` 或 `STOPPED` 状态允许修改和删除。

### 2.1 现场验证任务

`parameters.validationOnly` 为显式布尔值，缺省为 `false`。正式运行继续要求
`acceptance.status=PASS`；现场验证允许 `PENDING` 或 `BLOCKED_EXTERNAL_ASSETS` 的已发布
Pipeline 收集真实视频证据，解决“先有运行任务才能验收、未验收又不能启动”的闭环问题。
该模式不修改 Pipeline 验收状态，不允许 `BLOCKED_RUNTIME_ADAPTER` 等执行能力阻断，也不
放宽模型发布、目标节点 READY、单图测试、规则版本、权限、租户或完整受控链校验。
任务列表、创建摘要和监控明确标注“现场验证”，该参数随任务及事件配置快照保留。
旧 Runtime 对待验收 Pipeline 仍拒绝执行，因此先更新控制面，再更新 Runtime/Agent。

## 3. 状态与运行身份

任务同时保存期望状态与实际状态：

```text
DRAFT/STOPPED/FAILED/OFFLINE --start--> STARTING --report--> RUNNING
RUNNING/STARTING/FAILED/OFFLINE --stop--> STOPPING --report--> STOPPED
```

每次启动生成新的 `runId` 和运行记录。所有命令、运行上报都携带 `taskId`、`runId`、`configVersion`；控制面拒绝旧运行或旧配置的迟到上报，防止重启和网络抖动污染当前状态。

## 4. 耐久命令

控制面通过既有节点命令队列下发 `START_TASK` / `STOP_TASK`。Agent 拉取命令后读取任务详情，再调用本机 Runtime：

- `POST /v1/tasks/start`
- `DELETE /v1/tasks/{taskId}?runId={runId}`
- `GET /v1/tasks/statuses`

Agent 将命令阶段结果和 Runtime 周期状态分别上报。摄像头 URL 只在节点鉴权后的启动详情中短时出现，使用秘密类型承载，不写入命令、API 响应或日志。

## 5. 共享拉流与指标

同一 `cameraId` 的并行任务共享一个 FFmpeg 拉流/解码拥有者，每个任务使用容量为 1 的有界帧队列。队列满时丢弃旧帧，避免慢推理导致无界内存增长；最后一个订阅任务停止后才释放拉流进程。

Runtime 指标快照使用 `schemaVersion: 1.0`，包含：

- `inputFps`
- `analysisFps`
- `queueDepth`
- `droppedFrames`
- `inferenceMillis`

每个运行实例还返回不含敏感信息的 `diagnosticId`、错误码和脱敏错误摘要。控制面保存任务最新快照及运行历史，详细时序监控属于后续可观测性增强范围。

## 6. 兼容与安全约束

- 新字段必须向后兼容；协议破坏性变更必须升版本。
- Runtime 仅接受受控 DAG 和已加载模型，不执行任意用户代码或任意算子。
- 控制面不做业务决策或设备控制；任务启停仅管理 AI 分析计算生命周期。
- 真实摄像头、模型制品、节点凭据和生产参数不进入仓库。

## 7. 动态能力、识别参考库与视频验收扩展（2026-09-03）

- 算法中心支持从页面新增业务能力及参数 Schema；任务页面根据 Schema 动态生成参数控件。
- Pipeline 工作区支持 9 类受控节点的可视化增删改，并保留 JSON 高级编辑；业务能力键动态填写，仍禁止脚本和未知执行节点。
- 任务通过 `modelBindings` 为多个 Pipeline 节点选择模型版本；Runtime 对每个不重复版本执行推理并合并标准检测结果，事件证据同时冻结完整绑定快照。
- `ai_recognition_library` 与 `ai_recognition_library_entry` 统一承载人脸、车牌和场景姿态参考资产。页面按三个标签管理，不为单个识别能力复制新页面；识别引擎只能选择已发布且可执行的模型版本。
- 视频识别验收页面把算法、真实任务、固定测试集、指标、阈值、资源占用和证据引用写入新的不可变 Pipeline 版本。只有指标达到阈值且证据字段完整时才允许发布；真实模型与现场视频结论仍必须来自实际验收，自动化测试不能代替。
