# 算法目录清理与行为识别候选验证（2026-09-08）

本次完成目录清理、任务选择限制、行为管线修复及本地实测。**没有完成三项新增能力的生产验收，也没有将它们标为可用。** 网关离线使实机部署/测试无法继续；跌倒候选质量未达可用要求，吸烟与接打电话仍存在漏检。

## 目录为什么有这么多

清理前有 148 个启用算法、14 个启用模型。算法验收标记分布为 PASS 52、BLOCKED_EXTERNAL_ASSETS 45、BLOCKED_RUNTIME_IMPLEMENTATION 26、BLOCKED_RUNTIME_ADAPTER 20、PENDING 4、BLOCKED_MODEL_IMPLEMENTATION 1。多数是早期场景模板，部分 PASS 只代表基础规则实现，不能代表该场景经过现场验收。任务选择器只看启用/已发布管线，造成误解。

本次将 140 个未验证模板停用，保留 8 个原有算法入口：安全帽、反光衣、人员闯入、区域入侵、人员离岗、人员基础检测、烟雾、火焰与烟雾联合检测。保留 7 个已有 READY 执行版本的模型族：通用目标、PPE、火焰烟雾、CPU 安全帽、RK3566 人员、RK3566 安全帽、YuNet/SFace 主动人脸核验。原有 PASS/PENDING 状态未提升，不表示全部已通过生产验收。

7 个原有无 READY 版本的模型停用。新增候选加入后，当前共有 149 个算法（8 启用、141 停用）、15 个模型（7 启用、8 停用）。未删除任务、模型版本或证据。清理前完整快照、逐项清单见 `artifacts/behavior-catalog-20260908/inventory-before.json` 和 `cleanup.json`，可按原字段恢复状态。

前端算法中心和模型中心默认显示启用项；任务下拉框还要求已发布管线的全部模型均存在 PUBLISHED + READY 版本。PENDING 明示“现场验证”，BLOCKED 模板不再出现在任务选择中。后端原有任务创建/启动校验仍验证算法状态、节点部署及单图测试。

## 三项候选的实际状态

| 能力 | 模型/版本 | 算法/管线 | 实测与结论 |
| --- | --- | --- | --- |
| 跌倒 | 71011 / 133，YOLO11n ONNX | 72007 / 82629 | 专用候选、旧权重、PPE fall 类均进行了正反例比较；质量不合格，停用 |
| 吸烟 | 71034 / 132，YOLOv8n RKNN FP16；本地有 ONNX 对照 | 72423 / 82630 | 原始香烟候选可检出多张正例；关联到人员上半身并时序确认后漏检较多，停用待改进和实机测试 |
| 接打电话 | 71016 / 21，已有量化 ViT ONNX | 72004 / 82628 | 复用不可变权重，逐个人员裁剪分类，calling 规范化为 phone_call；可区分多张接电话与低头看手机参考图，仍漏检，停用待实机/现场验收 |

三条管线均通过平台 DAG 校验并保存为 PUBLISHED，**算法 status=1、acceptance=PENDING**。发布的是可审查配置，不代表运行验收通过。没有创建新运行任务。详细配置见 `candidates.json`。

接打电话原有 83 MB 权重超过平台 64 MB 单文件上传上限，因此复用已登记版本 21，未绕过上传限制、未更改已发布版本。来源许可证元数据仍为 `LicenseRef-Upstream-Unspecified`，其商业授权尚不明确，不能称为已获商业授权的模型。

## 数据与检验边界

- 跌倒：DeZan/fall-detection 验证目录固定前 8 张，经图像检查为跌倒/倒地场景；跨数据源训练集是否重叠未知，不能用作独立精度证明。旧单类权重检出 7/8，同时在原先 16 张非跌倒参考图中有 10 张误报，拒绝启用。PPE fall 类检出 3/8，YOLO11n 三类候选检出 2/8；另试保比例填充也未解决问题。完整结果分别在 `cpu-reference.json`、`ppe-fall-reference.json`、`fall-v2-reference.json`、`fall-v2-letterbox.json`。
- 吸烟：固定前 8 张 smoking 与前 8 张 not_smoking 图。正例组包含 1 张香烟拼图，并非人员吸烟；原始检测在其余 7 张均有候选。完整人员关联管线的静态重复回放仅 2 张确认，8 张负例无确认。漏检包括近景、半身与香烟离开头部的情况，不能称为整体准确率通过。
- 接打电话：先检查 Bingsu 数据集 test 首段，发现标签与图像内容不一致，**未将其错误标签用于准确率统计**；这些图保留为人工检查过的其他行为反例。另取 train 前 100 条中 calling/texting 各前 6 条，作为功能参考，不能作为独立测试集。逐人管线在 calling 组 5/6 张中确认，在 texting 组 0/6 张确认；人工检查发现 texting-train-46 实际为接电话，故其未确认属于漏检，不能算真阴性。
- 时序验证为同一真实图片按 200 ms 间隔重复输入，验证 2 秒前不确认以及不同人员/断帧隔离，**不是实际跌倒过程或吸烟/接电话动作视频验收**。目标现场尚无上述三类正反例视频。

修复了人员裁剪、calling/texting 类别隔离、香烟与人员上半身关联、同一证据不重复关联两个人、过期时序历史清理。原候选默认 5 FPS、5 帧窗口、持续 2 秒互相矛盾，新候选改为 30 帧窗口、至少 3 帧、持续 2 秒（默认目标采样 2 FPS）。逐人分类最多处理画面中面积最大的 10 人，低分辨率人员跳过；密集人群和网关 CPU 性能需要另验。

## 网关状态与部署边界

192.168.2.17 最后心跳为 2026-09-08 17:52:41，平台显示离线，SSH/TCP 22 连接超时。在线升级在预检阶段失败，**未创建升级部署、未向网关安装本次运行时代码**。网关仍显示 source-696beef5138c。无法声称新 RKNN 模型与 ONNX 对照一致，也无法声称新增任务启动成功。

前一次工作保留的安全帽/反光衣恢复证据属于前一次版本，本次不能拿来代替新增行为的实机证据。期间另有任务状态变化，未擅自启动或恢复任务。

## 验证与复验

- Runtime 全量回归：261 项通过；之后增加重叠人员归属测试，并执行对应目标回归。
- Vue TypeScript 检查通过，Ruff 检查通过。
- 浏览器实际核对：算法中心“已启用”默认选中，共 8 项；任务创建下拉框只有上述 8 项，未验证新增候选不出现，未创建任务。
- 本地复现人员关联与时序功能：`runtime/.venv/bin/python scripts/verify-behavior-candidates.py`。脚本使用本次审计目录内样本、模型及已有 `var/model-assets/v1/human-action-vit-int8.onnx`，输出 `pipeline-reference.json`。
- 网关恢复后，先部署当前 Runtime（使用既有离线依赖包），逐个部署/单图测试候选，比较 CPU/NPU 输出并观测内存；保留已有任务的模型容量预算。模型池仅 4 槽，不能无条件并行启动所有模型。
- 跌倒需更换权重或取得目标现场数据进行针对性改进；吸烟、接打电话需现场正反例与持续动作视频复验。只有补齐单图、视频、误报/漏报和资源证据后，才启用候选并创建现场验证任务。不得直接写 READY/PASS 或使用静态重复回放冒充现场验收。

## 上游来源

- [吸烟 ONNX 原仓库](https://github.com/alihassanml/Smoking-detection-yolo11/tree/bbef478fad3d6d18e4a18bf02fadce1a09f55e15)，图内元数据声明 AGPL-3.0；raw 类名为 Smooking，输出主要围住香烟，因此算法只将其作为候选证据。
- [旧跌倒权重](https://huggingface.co/kamalchibrani/yolov8_fall_detection_25/tree/607a55e0f2a3c056cf1afb82a9a6f8e65a97bc0b)，实测误报后拒绝启用。
- [YOLO11n 跌倒候选](https://huggingface.co/melihuzunoglu/human-fall-detection)，固定版本与所有 SHA256 见审计文件。
- [已有 ViT ONNX](https://huggingface.co/onnx-community/Human-Action-Recognition-VIT-Base-patch16-224-ONNX/tree/43fb98d467b91ad92528249af8276608b64eacfb)，使用原始归一化参数和 learned calling/texting 类别。
- [跌倒样本](https://huggingface.co/datasets/DeZan/fall-detection/tree/234cdf4b71ab41d03880263620a36181bbd944e2)、[吸烟样本](https://huggingface.co/datasets/ccclllwww/smoking_test/tree/31931155090a812dd52a0fd6b0996bbb57e1d9fd)、[行为参考数据](https://huggingface.co/datasets/Bingsu/Human_Action_Recognition/tree/6c1a1284eb3557055d7c57b91cd7e68e3252b32c)。下载来源及图片 SHA256 在 `samples/sources.json`、`samples/phone-training-sources.json`；模型 SHA256 在 `asset-sha256.json`。
