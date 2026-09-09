# LInsight 内置通用模型与算法目录 V1

## 1. 交付口径

本目录采用“模型尽量少而通用，算法必须可执行”的策略：10 个启用逻辑模型族承载 148 个算法定义。
另外 11 个无法由当前 Runtime 确定性执行的模型族及其 87 个算法已退出当前交付范围。每个保留算法都有稳定 code、场景组、实现方式、依赖能力、
默认模型和不可变 Pipeline v1。

当前活动逻辑模型均已具备 Runtime Manifest。V1 的物理权重可以通过
`make model-assets-sync` 下载、校验并登记，但模型文件仍须分别通过单图测试、
节点部署和固定测试集验收。许可证事实会记录在版本上，不参与下载；生产发布仍保留独立审核门禁。
Pipeline 的状态含义如下：

| 状态 | 含义 |
| --- | --- |
| `PASS` | Pipeline 结构及现有 Runtime 语义可用；仍需通过模型版本和节点门禁 |
| `BLOCKED_EXTERNAL_ASSETS` | 缺真实权重、权重许可证或固定测试集证据 |
| `BLOCKED_RUNTIME_ADAPTER` | 需要关键点、时序、OCR、embedding、mask 等专用输出 Adapter |
| `BLOCKED_RUNTIME_IMPLEMENTATION` | 需要越线、方向、静止、距离、组合或视频质量等运行时规则语义 |

目录初始包含 29 个模型、235 个算法；ADR-0005 首先收敛 8 个重复模型别名。随后按负责人决定，
11 个缺少可验证 Runtime 协议的模型族、87 个相关算法和 Pipeline 被逻辑删除。当前活动目录为
10 个模型、148 个算法，模型清单技术违规项为 0。历史 Pipeline 是不可变审计记录，不会物理抹除。

### 1.1 物理资产同步状态

- 机器可读目录：`runtime/model_assets/builtin-model-assets-v1.json`
- 本地落盘目录：`var/model-assets/v1/`
- 本地锁定清单：`var/model-assets/v1/assets-lock.json`
- 本地开发对象存储：MinIO 私有桶 `linsight-models/builtin/v1/`
- 当前覆盖：10 个启用逻辑模型、10 个生产候选版本、10 个生产上游下载文件、0 个组合包
- 退出生产目录的制品移动到 `var/model-assets/archive/unsupported-runtime-20260904/`，仅用于恢复和审计

`make model-assets-download` 只下载并计算 SHA256；`make model-assets-sync` 还会应用数据库迁移、
上传本地 MinIO 并登记 `DRAFT + VERIFIED` 版本。重复执行会跳过已校验文件和已登记版本。

## 2. 模型复用矩阵

| 模型族 | 主要复用范围 | 推荐公开候选 | 当前适配 |
| --- | --- | --- | --- |
| 通用 COCO 目标检测 | COCO 80 类检测、类别过滤、计数、ROI、跟踪、车辆/人员规则 | YOLO11/YOLOv8、DAMO-YOLO | 标准 `[N,6]` ONNX + `classFilter` |
| 统一 PPE | 安全帽、反光衣、口罩、工服及联合完整性 | YOLOv8n PPE 6 类 | 通用 Ultralytics 检测执行器 |
| 视频行为 | 已保留模型标签支持的行为分类 | 15 类 Human Action ViT INT8 ONNX | 通用分类执行器 + 时序规则 |
| 火焰烟雾联合检测 | 火焰、烟雾、浓烟与联合告警 | YOLOv8s fire/smoke ONNX | 通用检测执行器 |
| 车牌检测与 OCR | 四点检测、矫正、中文车牌识别 | YuNet + LPRNet ONNX | `LPD_YUNET`、`LPRNET` 协议解码器 |
| 积水、跌倒、垃圾杂物 | 对应专项检测 | Ultralytics PyTorch 权重 | 通用检测执行器 |
| 人脸活体 | 照片/真人二分类 | Anti-Spoof INT8 ONNX | 通用分类执行器 |

通用 COCO 的类别顺序固定为标准 80 类，Runtime 在推理后按 `classFilter` 过滤，因此人员、汽车、
卡车、公交车、摩托车、自行车、动物、手机、背包、手提包、雨伞、瓶子和椅子无需各加载一份模型。

## 3. 公开来源与许可证记录

- Ultralytics YOLO11/YOLOv8 可作为候选，但其官方发布采用 AGPL-3.0 或商业许可证；商用闭源部署
  的授权风险仅记录在版本元数据中，不阻断导入、发布或部署。
- DAMO-YOLO 仓库为 Apache-2.0，并提供预训练与 ONNX/TensorRT 路径；具体权重仍需固定 revision
  并校验下载来源。
- PaddleOCR、MMPose、MMAction2、MMSegmentation 的项目代码采用 Apache-2.0；每个实际 checkpoint
  的训练数据与权重条款随版本一并记录。
- SAM 2 的官方代码和 checkpoints 使用 Apache-2.0，可作为分割候选，但仍需实现平台 mask 输出契约。
- InsightFace 代码为 MIT，但官方公开预训练模型标注为非商业研究；该信息保留在版本元数据中，
  平台不设置商业审核门禁。

当前 V1 按用户要求不设置商业审核，许可证仅作为资产来源信息展示；下载、目录发布、Runtime 适配、
节点部署和生产验收仍是相互独立的状态。
模型中心仍以每个 `ModelVersion` 的 `sourceRepository`、
`sourceRevision`、`licenseSpdx` 和 `sha256` 为供应链记录。

## 4. 算法覆盖

活动算法按通用目标、人员、PPE、跌倒、行为、车辆、车牌、火焰烟雾、积水、垃圾杂物、跟踪和组合等场景组织。
吸烟专项、姿态、车型、人脸识别、通用 OCR、仪表、开放词汇、分割和视频质量等依赖不可执行模型的算法已退出当前交付范围。
迁移中的固定清单是机器真值；控制台和 API 通过 `sceneGroup`、`implementationType`、
`requiredCapabilities` 与 `pipelineAcceptanceStatus` 暴露目录状态。

全部 223 个新增算法的当前 Pipeline 已通过控制面/Runtime 双重结构校验。车牌 OCR 的 5 个初始
模板因缺少检测前置链路而保留为审计用 v1，`V202609022340` 新建不可变 v2 并切换当前指针。

新增算法时优先选择以下模式，不为规则型能力创建伪模型：

1. `MODEL_FILTER`：复用通用检测器，仅改变 `classFilter`。
2. `TRACK_RULE`：复用 Detector + IoU Tracker + 版本化 Rule AST。
3. `MODEL_DIRECT`：确有不同输出语义时使用专项模型 Adapter。
4. `CLASSICAL_CV`：视频质量等确定性算法优先使用帧统计/帧间计算。
5. `COMPOSITE`：组合已有目标、属性、轨迹和规则结果，不重复推理。

## 5. 解除阻断顺序

1. 导入并验收一个标准输出的 COCO 80 类 ONNX 版本，完成 YOLO11/YOLOv8/DAMO-YOLO 至平台
   `[N,6]` 输出的转换验证。
2. 用固定视频回放验证 `classFilter`、跟踪、ROI、COUNT/COUNT_BELOW、持续时间、冷却和去重。
3. 实现 line-crossing、direction、stationary、distance 与 composition 规则插件。
4. 对保留模型执行逐模型冒烟、错误输入和输出契约验证，不再为已删除能力开发 Adapter。
5. 补齐事件级 Precision/Recall、每路每小时误报、端到端时延和资源基线，再发布
   新的不可变 Pipeline 版本；禁止修改既有迁移或原地覆盖 Pipeline。
