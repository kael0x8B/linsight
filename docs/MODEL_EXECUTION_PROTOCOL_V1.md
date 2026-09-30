# 模型部署与单图测试协议 V1

## 1. 范围与状态含义

本协议定义控制面、Edge Agent 与 AI Runtime 模型执行闭环。Java 控制面只保存业务真值、下发耐久命令并校验结果；模型下载、格式识别、加载和推理由节点上的 Agent/Runtime 完成。

模型版本的三个状态不能混用：

- `publishStatus=PUBLISHED`：资产目录默认版本已选定，来源、固定 revision、SHA256、格式和许可证门禁通过。
- `executionStatus=READY`：同一节点上至少一次部署进入 `READY`，且该版本在该节点完成一次符合本协议的单图推理。
- 业务/生产验收：仍需逐模型真实权重、固定测试集、精度指标和阈值基线，由验收证据决定；确定性契约模型只证明执行链可工作，不能替代此结论。

## 2. 耐久命令

控制面将命令存入 `ai_node_command`，Agent 通过节点认证接口拉取并上报。V1 命令类型为：

| 命令 | 聚合记录 | 作用 |
| --- | --- | --- |
| `DEPLOY_MODEL` | `ai_model_deployment` | 下载、SHA256 校验并加载版本 |
| `RUN_MODEL_TEST` | `ai_model_test` | 确保版本已加载并对一张图片推理 |

命令以 `commandId` 标识，以租户内 `idempotencyKey` 防止重复创建；`configVersion` 固定参与幂等键。状态为 `QUEUED → SENT → RUNNING → SUCCEEDED/FAILED`，`SENT` 超过重试窗口可再次拉取，最多尝试五次。重复上报相同终态必须重新驱动业务聚合状态收敛，不能重复产生新命令。

控制面仅向命令所属节点返回 10 分钟有效的模型和测试图片签名 URL。Agent 下载模型后必须在加载前校验 SHA256；错误上报只包含诊断 ID、错误类型和脱敏摘要，不回传签名 URL、节点凭据或对象存储内部引用。

## 3. Runtime 模型池与声明式执行契约

Runtime 使用 `(modelVersionId, device)` 作为 `ModelPool` 键。相同 SHA256、格式和 Runtime Manifest 的重复部署复用已加载实例；容量超过配置上限时淘汰最久未使用实例。V1 开放：

- 格式：ONNX、TorchScript、PyTorch checkpoint、ZIP 模型包；ADR-0007 增加 RKNN NPU。
  TensorRT Engine 仍只允许进入资产目录。RKNN 不会伪装成 CPU/ONNX 执行。
- RKNN 后端：Linux ARM64、Python 3.12、固定 `rknn-toolkit-lite2==2.3.2`，使用节点既有 RKNPU 驱动。
  制品必须为 RKNN、设备必须为 RKNPU，Manifest 必须显式声明输入尺寸、UINT8 NHWC。
  归一化在受控转换时编入模型；输出沿用通用 Manifest 解码。SDK 或芯片不兼容时明确失败。
- ONNX 后端：ONNX Runtime `CPUExecutionProvider`，支持标准 `[N,6]`、常见扁平 YOLO 输出和
  RKNN Model Zoo 的 DFL 多尺度检测头。
- TorchScript 后端：`torch.jit.load`；PyTorch checkpoint 后端：Ultralytics YOLO。PyTorch
  使用 pickle 反序列化，因此只接受控制面标记为 `PRESET` 且已完成 SHA256 校验的制品。
- ZIP 后端：安全解包、成员哈希校验和可执行成员识别。单模型包直接路由；多模型包必须由明确的
  组合/流水线适配器接管，禁止任意选择第一个成员。
- `runtimeManifest` 声明 `taskType`、输入宽高、RGB/BGR、NCHW/NHWC、dtype、scale、mean/std、
  解码协议和标签/字符表。控制面不再维护业务 model code 到 Adapter 的硬编码映射。
- `modelEnvironment` 从 Runtime 观测快照透传心跳，保留 `schemaVersion: 1.0`、`formats`、
  `rknnTargets`，并增加 `providers`。每个 provider 明确上报 `code`、`deviceType`、`vendor`、
  `targets`、`formats`、`runtime` 和 `runtimeVersion`。当前实现可上报 `onnxruntime`、
  `python-cpu`、`rknpu2`；未来盒子使用同一结构增加执行后端，不需要按盒子型号增加平台分支。
- 设备专用模型可在 `runtimeManifest.execution` 声明 `provider`、`target`、`runtime` 和
  `minRuntimeVersion`。控制面要求格式、执行后端、目标和最低运行库版本全部匹配后才允许下发。
  `targetPlatform` 继续作为历史目标字段，若与 `execution.target` 同时出现，两者必须一致。
  RKNN 与旧 `FACE_PAIR_SFACE_RKNN` 自动映射到 `rknpu2`，但芯片仍须由清单明确声明。
- 未声明执行后端或目标的历史设备专用模型只自动复用目标节点上已经 READY 的版本；不从名称、
  CPU 架构或 NPU 使用率推断芯片，不原地修改已发布版本。旧节点未上报执行环境时保留 ONNX
  及本机已就绪版本的兼容路径。能力匹配只判断部署前提，真正就绪仍须下载、校验和加载成功回执。
- 通用协议包括 `AUTO_DETECTION`、`CLASSIFICATION`、`CTC_GREEDY`；旧车牌模型继续使用
  `LPD_YUNET`、`LPRNET`。中文车牌专用模型新增 `YOLO_PLATE`（640×640 RGB letterbox，
  `[1,N,15]` 框、四角及单双层分数）与 `CHINESE_PLATE_CTC`（168×48 BGR，
  `[1,T,78]` 字符 logits 及 `[1,5]` 颜色 logits）。新解码器复用 ONNX Runtime CPU 后端；
  字符表和预处理与固定权重绑定，旧 decoder 与算法保持兼容。新增业务算法仍组合能力、跟踪和规则。
- `LETTERBOX` 当前仅用于 `YOLO_PLATE` 专用协议；其他模型继续使用原有 `STRETCH` 契约。
  车牌四角映射到原图后做几何检查和透视矫正；异常角点退回检测框，双层牌分行拼接。
  OCR 输入采用原图裁剪的 PNG，避免中间 JPEG 编码损失。
- `AUTO_DETECTION` 原始输出可为 `[N,6]`、`[1,N,6]`、常见 YOLO 扁平输出或 RKNN DFL
  多尺度头，统一转换为 `[x,y,width,height,score,classId]` 归一化坐标。
- 仅包含 `state_dict` 的 DAMO-YOLO checkpoint 仍需对应网络定义或先导出 ONNX；OCR、仪表、
  开放词汇、人脸特征等多阶段 ZIP 仍需模型家族级流水线。Manifest 不能凭空恢复制品中不存在的计算图。
- `adapter` 字段仅用于已部署旧节点的滚动升级兼容；新控制面命令只下发 `runtimeManifest`。

Runtime API 只接受位于 `runtimeDataRoot` 内的绝对文件路径，并要求 `X-Runtime-Key`。Agent 与 Runtime 应部署在同一受控节点；外部系统不能直接调用这些内部接口。

### 3.1 部署时自动准备运行环境

节点安装仅安装 Runtime 基础环境。用户下发模型部署或单图测试命令时，Agent 自动请求
`POST /v1/models/dependencies/prepare`，请求仅含 `artifactFormat`，不接受 requirements、
索引地址、shell 命令或模型附带的安装脚本。随后通过
`GET /v1/models/dependencies/{profile}` 查询准备状态，完成后继续原来的模型加载命令。
两个接口沿用 Runtime 身份认证，不暴露给浏览器。

- ONNX 使用基础环境；RKNN 在节点源码部署时安装固定 SDK，模型部署只检查 SDK，不下载模型附带代码。
  PYTORCH/TORCHSCRIPT/ARCHIVE 使用平台维护的 CPU profile。
  当前 profile 固定 Torch 2.14.0、torchvision 0.29.0、Ultralytics 8.4.142。
  ARCHIVE 保守准备同一 profile，但是否存在可执行成员仍由既有制品校验决定。
- 优先验证并复用已有兼容环境。缺失时在 `runtimeDataRoot/dependencies/{profile}` 创建独立
  venv，只读继承 Runtime 基础包路径，所有 pip 写入均限制在独立环境，不升级服务主环境。
  PYTORCH/TORCHSCRIPT/ARCHIVE 模型由 Runtime 内部子进程运行既有 Adapter，标准化结果与推理后端不变；不是新增网络服务。
- 新环境验证导入、固定版本、CPU 构建通过后才供模型使用。准备期间旧模型继续使用原进程。
  相同 profile 的并发请求合并；READY 请求复用；失败后的新部署请求可重试。
- 只使用官方 CPU/PyPI 索引、二进制 wheel 和固定顶层依赖。优先读取
  `runtimeDataRoot/dependencies/wheels` 离线缓存，联网下载保留 pip 缓存，最多三轮安装尝试。
  缓存必须由受信任运维渠道维护。不会把任意模型文件作为 Python 包安装。
- 准备总时限 20 分钟，Agent 等待上限 21 分钟，并每 5 秒上报阶段以续租原命令；
  不延长普通节点请求的超时。模型加载/测试单请求上限 150 秒，工作进程单次操作上限 120 秒。
- 阶段：`CHECKING_ENV / INSTALLING_DEPS / DOWNLOADING_DEPS / RETRYING_DEPS / VERIFYING_ENV`，
  然后 `LOADING / READY`。环境 READY 不等于模型 READY，只有模型加载成功才报告部署成功。
- 失败返回稳定错误码和不含凭据的说明，包括磁盘不足、不支持的架构、安装失败、验证失败和超时。
  失败的独立目录保留以便重试，不切换正在使用的环境。Runtime 关闭、模型替换/淘汰时回收子进程。

现有节点需先更新 Runtime 与 Agent 代码以获得该流程；无需用户手动补装模型依赖。
滚动发布顺序为控制面（接受新增阶段）→ Runtime（提供准备接口）→ Agent；旧节点仍兼容。
更新服务本身需要维护窗口，与后续每次模型部署的无共享环境修改是两个不同操作。

模型制品签名地址必须能从节点访问：远端节点不能使用控制面机器的 `127.0.0.1` 地址。
使用内置资产同步脚本登记时，应显式传入 `--public-endpoint`，并保持存储 domain 与资产引用一致。

## 4. 标准化检测结果

成功结果必须满足：

```json
{
  "schemaVersion": "1.0",
  "sourceWidth": 1280,
  "sourceHeight": 720,
  "objects": [
    {
      "class": "person",
      "confidence": 0.93,
      "bbox": { "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4 },
      "attributes": { "classId": 0 }
    }
  ]
}
```

`confidence` 与四个 bbox 数值均在 `[0,1]`，bbox 使用左上角加宽高，最多返回 500 个对象。控制面在保存前再次校验；不合规结果不会把测试或版本执行状态推进为成功。

## 5. P10 管理端

`/ai-video/model-test` 列出所有启用模型及其全部版本，不再固定 Person 或过滤为 ONNX。未发布版本可以查看但不能部署；版本选项同时显示格式和发布状态。页面可下发部署、轮询节点状态、上传 10MB 内 JPEG/PNG/WebP、设置置信度/NMS/输入尺寸，并展示标准结果、归一化 bbox、实际后端、分阶段耗时、诊断 ID 和脱敏后的加载失败原因。

测试图片使用对象存储内部引用；浏览器只展示本地选择的预览，节点按命令获取短时签名 URL。测试记录是技术执行证据，不是精度报告。

## 6. 验证与未覆盖项

自动化测试使用真实 ONNX Runtime 加载确定性 ONNX 图，并覆盖 Manifest 校验、通用检测/分类、
ZIP 单模型路由、PT 信任边界、格式透传、SHA256、模型池复用、阈值、NMS 和 V1 结果格式。
真实 YOLO11、行为分类、YuNet 也已完成加载冒烟；这些测试明确不验证模型检测精度。

V1 已定义可扩展 provider 匹配结构，但尚未实现 GPU/TensorRT Runtime 后端、显存/OOM 降级、大模型分片上传、测试图片生命周期任务、DAMO-YOLO 网络重建以及多阶段专项流水线；这些项目完成前不得宣称相应模型业务能力已生产验收。

## 7. RKNN 制品来源与回退（ADR-0007）

转换在 `deploy/rknn-conversion/Dockerfile` 的固定 Toolkit 2.3.2 环境执行，使用
`scripts/convert-rknn-model.py` 要求显式传入 `--target-platform`（如 `rk3566` 或 `rk3588`），记录源 ONNX/Manifest SHA256、目标芯片、精度、校准样本哈希和输出 SHA256，并把 `rknpu2` 执行要求写入输出 Manifest。
转换成功不自动表示精度通过：必须先比较同图输出，再走平台发布、部署与模型测试流程。
现场安全帽模型因合并输出中的坐标与置信度量级不同，直接 INT8 量化破坏置信度，已拒绝该制品；改用 FP16。
当前 CPU 目录版本保持可用，现场 RKNN 制品采用独立模型资产并记录父版本，回退由原任务配置启动新 Run。

- RKNN 复用现有 `IsolatedAdapter` 私有模型进程，每个模型一个串行 SDK 上下文，避免原生库的 CPU/GIL
  工作挤占 Runtime 媒体解释器。没有新增网络服务；节点基础环境中的固定 SDK 和原 Manifest 不变。
  同帧 RGB 通过长度声明的二进制管道传递（最大 32 MiB），保留源尺寸，不重复 JPEG 解码或 Base64 编码。
  原生 SDK 日志与结果协议描述符分开；加载预算 120 秒、RKNN 单次结果等待 10 秒，退出/超时明确失败。
  模型替换、淘汰、Runtime 关闭时回收工作进程；CPU 既有格式和依赖隔离路径保持原有行为。
- 同帧、彼此独立的全图 RKNN 模型每批最多并行执行两个，以重叠 CPU 预处理/后处理与设备执行；
  每个模型实例仍串行保护 SDK 上下文。按绑定顺序合并全部结果后才跟踪、判断规则，异常不会发布半份结果。
  CPU 模型维持原有串行方式，车牌检测后裁剪再 OCR 的依赖顺序不变。各模型推理耗时可重叠，
  完整分析处理时间以 `totalLatencyMillis` 为准，不能把各模型耗时之和当作并行管线墙钟耗时。
