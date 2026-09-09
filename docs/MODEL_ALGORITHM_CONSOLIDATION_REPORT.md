# 模型与算法目录收敛报告

- 执行日期：2026-09-04
- 变更方式：前向迁移、保留历史、可回滚
- 选择口径：当前 Runtime 可执行性、任务语义匹配、依赖数量、SHA256 固定；真实精度仍等待统一现场数据集

## 结果

| 项目 | 收敛前 | 收敛后 | 处理 |
|---|---:|---:|---|
| 启用逻辑模型 | 29 | 10 | 先停用 8 个重复别名，再逻辑删除 11 个不可执行模型族 |
| 生产目录模型版本 | 34 | 10 | 活动目录仅保留具有 Runtime Manifest 的候选版本 |
| 生产同步上游文件 | 28 | 10 | 不再同步不可执行权重和组合包 |
| 活动算法定义 | 235 | 148 | 删除与 11 个不可执行模型直接绑定的 87 个算法及 Pipeline |

## 已收敛模型

| 停用模型 | 保留主模型 | 理由 |
|---|---|---|
| `person-detection` | `generic-coco-object-detection` | 当前均使用同一 YOLO11n SHA；人员是 COCO 标签过滤 |
| `reflective-vest` | `unified-ppe-detection` | 当前权重 SHA 相同；反光衣是 PPE 标签/规则组合 |
| `flame` | `flame-smoke-detection` | 当前权重 SHA 相同；联合模型已经输出 flame/smoke |
| `abandoned-removed-object` | `generic-coco-object-detection` | 遗留/移除由通用检测 + Track ID + 时序规则完成，不是独立模型协议 |
| `safety-helmet` | `unified-ppe-detection` | 安全帽是统一 PPE 输出的标签与规则，不再单独加载一套模型 |
| `sleeping-on-duty`、`phone-call-detection` | `video-action-recognition` | 三者使用同一 15 类行为模型，睡岗/打电话由算法过滤标签 |
| `smoking-detection` | `smoking-phone-detection` | 第一阶段合并；联合包随后因裸 DAMO 权重不可执行而整体退出活动目录 |

迁移已把所有算法默认模型引用从上述别名切换到主模型。旧模型 `status=1`，不会进入新的生产选择；
旧版本、部署记录和事件快照未删除。

## 算法删除边界

数据库按 `event_type + pipeline DAG + default_parameters` 审计后，没有完全相同的算法，因此没有按名字
盲目去重。负责人随后明确要求删除不能由当前 Runtime 执行的模型及相关算法：87 个直接依赖算法和
87 个 Pipeline 已逻辑删除。车辆检测、车辆计数、车辆越线、车辆滞留等仍可复用保留的 COCO 模型，
它们输出事件和状态机不同，因此继续保留。

## 已退出当前交付范围

`face-mask`、`face-detection`、`human-pose-estimation`、`vehicle-type-classification`、
`face-recognition-embedding`、`general-ocr`、`meter-reading`、`open-vocabulary-detection`、
`general-segmentation`、`video-quality-assessment`、`smoking-phone-detection`。

相关历史任务、事件、测试和部署记录保留审计；19 个本地文件移动到
`var/model-assets/archive/unsupported-runtime-20260904/`，不再进入生产锁定清单。

## Runtime 收敛

- 新增 `runtime_manifest`，由模型版本声明预处理、任务类型、输出协议、标签/字符表。
- Java 控制面已移除 30 项业务模型 Adapter 映射，直接下发 Manifest。
- Edge Agent 会持久化 Manifest 并在重启后重新加载。
- Runtime 已提供通用 ONNX 检测、分类、CTC OCR 执行器；YuNet 四点车牌检测与 LPRNet 保留为协议解码器。
- 裸 PyTorch `state_dict`、姿态、分割、Embedding、多模型流水线仍需一次模型家族级导出/解码器，不能靠猜测张量完成。

## 当前结论

活动目录现有 10 个模型、10 个版本、10 个文件、148 个算法，模型清单技术违规项为 0。目录收敛和
执行契约通过不等于算法精度验收通过；必须在目标节点完成真实推理和现场 Benchmark。
