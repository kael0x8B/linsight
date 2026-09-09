# ADR-0005：声明式模型 Runtime 与目录去重

- 状态：Accepted
- 日期：2026-09-04
- 决策人：项目负责人（用户明确批准）

## 背景

原实现用 Java 中的 `model code -> Runtime Adapter` 硬编码表和 Python 中约 30 个业务命名
Adapter 描述模型。它把“模型输出协议”与“算法业务语义”耦合起来，导致同一权重被人员、车辆、
遗留物等算法重复注册，新模型也被误认为必须新增一个业务 Adapter。

数据库审计确认存在多组相同 SHA256 的模型版本；同时按算法代码、事件类型、Pipeline DAG、默认参数
比较，没有发现可以无损删除的完全等价算法。共享一个基础模型不等于算法重复，例如车辆计数、越线、
滞留共享检测器，但时序状态和事件语义不同。

## 决策

1. 模型版本新增 `runtime_manifest`。Manifest 固定描述任务类型、输入尺寸/颜色/布局/归一化、解码协议、
   标签或字符表。控制面直接下发 Manifest，不再按业务模型编码选择 Adapter。
2. Runtime 维护通用的检测、分类、CTC OCR 执行器；只有输出数学协议真正不同（例如 YuNet 车牌四点、
   LPRNet）时保留小型协议解码器。
3. 算法继续由 Pipeline DAG 组合模型、跟踪和规则。增加算法不需要增加模型 Adapter。
4. 物理文件按 SHA256 去重。逻辑目录中明确重复的旧模型不删除历史记录，改为停用；其算法默认引用迁移
   到通用主模型。旧版本改为 `SUPERSEDED`，已有部署、事件快照和审计记录仍可追溯。
5. “最优”分两层：本次只选择已能由现有 Runtime 执行、依赖更少、来源和 SHA 已固定的工程主版本；
   现场精度最优必须由同一真实测试集 Benchmark 决定，未测试不得宣称精度最优。

## 本次主模型

| 能力 | 保留主模型 | 被停用的重复目录 |
|---|---|---|
| COCO 通用检测（含人员/车辆基础检测） | `generic-coco-object-detection` / YOLO11n ONNX | `person-detection` |
| PPE 联合检测 | `unified-ppe-detection` / YOLOv8 PPE | `reflective-vest` |
| 火焰烟雾联合检测 | `flame-smoke-detection` / YOLOv8 Fire-Smoke | `flame` |
| 遗留/移除物基础检测 | 复用 COCO 主模型并由跟踪规则完成 | `abandoned-removed-object` |
| 安全帽/反光衣等 PPE | `unified-ppe-detection` | `safety-helmet`、`reflective-vest` |
| 睡岗/打电话/行为分类 | `video-action-recognition` | `sleeping-on-duty`、`phone-call-detection` |
| 吸烟/打电话联合检测 | 第一阶段曾保留 `smoking-phone-detection`，后因裸权重不可执行而退出交付目录 | `smoking-detection` |

没有删除“安全帽佩戴”和“未戴安全帽”等算法：二者事件输出和处置语义不同。目录精简报告必须区分
`PHYSICAL_DUPLICATE`、`LOGICAL_MODEL_ALIAS` 与 `DISTINCT_ALGORITHM_COMPOSITION`。

## 兼容性与回滚

- Runtime API 暂时接受旧 `adapter` 字段；新控制面只下发 `runtimeManifest`。
- 数据库只做前向迁移，不删除制品和历史数据。
- 回滚应用版本后，旧 Adapter 路径仍可执行迁移前已经下发并持久化的节点模型记录。

## 后果

- 常见 ONNX 检测/分类/CTC 模型只需登记 Manifest，无需编写 Runtime Adapter。
- 新输出协议、模型自带 Python 类的裸 `state_dict`、多阶段模型包仍需要一次“模型家族级”解码器或导出，
  但不再为每个业务算法重复开发。
- 模型能加载不代表算法精度通过；真实数据验收状态继续保持 `WAITING_FOR_REAL_DATA`。

## 2026-09-04 范围收缩决定

负责人进一步明确：当前 Runtime 无法确定性执行的模型和相关算法不进入交付目录。
`V202609041800` 因此逻辑删除 11 个模型族、11 个版本、87 个算法及 87 个 Pipeline：口罩 DAMO、
RetinaFace、YOLO Pose、错误的 ImageNet 车型分类、InsightFace、PP-OCR、仪表读数、YOLO-World、
YOLO Segmentation、BRISQUE 和吸烟/手机 DAMO。生产资产目录同步缩减为 10 个文件。

这是经批准的交付范围收缩，不代表上述能力已经实现。历史任务、事件、测试和部署记录继续保留；
如果合同重新要求其中任一能力，必须以新的可执行模型版本、Runtime Manifest、固定冒烟样例和现场
Benchmark 重新引入，不允许仅恢复旧目录状态。
