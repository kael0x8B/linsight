# 现场未佩戴安全帽场景部署记录（2026-09-06）

后续当前状态见 [2026-09-07 漏检修复记录](HELMET_RECALL_FIX_20260907.md)：部署 25 已修复分析 JPEG 过度压缩，并复核真实未戴帽结果及事件证据。下文为各阶段历史部署记录。

当前状态：**部署及功能联调完成，任务保持运行**。真实未戴帽事件 219、220 的截图、录像上传和恢复/关闭流转已核对；录像播放加速问题已修复并在节点验证。最终 Runtime 为 `source-61d11147a953`，当前 Run 为 `0cbfdaa3-c431-4761-85eb-fae2e9d5c054`。场景以现场验证模式运行，正式精度验收仍为 `PENDING`。

## 部署范围与配置

- 通过 LInsight 控制面现有摄像头、模型、算法 Pipeline、规则、任务、节点部署接口完成业务配置，没有直接修改业务数据库。
- 摄像头：ID `2`，`CAM-FIELD-207`，海康 DS-2CD3T86FWDV2-I3S，`192.168.2.207`。
- 节点：ID `1`，`rk3566-field-001`，`192.168.2.17`，Ubuntu 24.04.3 / ARM64 / Python 3.12，RK3566 CPU，约 2 GB RAM。
- 采用现有 ONNX Runtime CPU 和共享摄像头子码流，不引入新推理服务或新的硬件执行路线。
- 算法 `72001 / safety-helmet`，Pipeline `82622`：人员检测 → 安全帽关联 → IoU 跟踪。
- 人员模型：模型族 `71013`，版本 `18`，`yolo11n.onnx`，640×640。
- 安全帽模型：独立模型族 `71030`，版本 `120 / yolov8n-hardhat-287b-onnx320-v1`，320×320，标签 `helmet / no_helmet`。共享 PPE 模型族恢复原发布版本 `19`，避免替换反光衣、口罩等场景的默认模型。
- 规则 `73002`、规则版本 `73103`：全画面，连续窗口 2/3 帧且持续至少 1 秒，冷却 30 秒，按人员轨迹去重，全天运行。
- 初始推理参数：采样 0.5 FPS，整体置信度 0.25，人员 0.30，安全帽 0.50，NMS 0.45，无法确认状态 `NO_ALARM`。
- 场景使用显式 `parameters.validationOnly=true`。Pipeline 验收状态保留 `PENDING`，不能据此宣称已达到生产精度指标。

## 模型来源及可追溯性

### 人员模型

来源：[airockchip/rknn_model_zoo](https://github.com/airockchip/rknn_model_zoo)，记录版本 `bad6c7334531becaf90a561988519b7bec34d0ab`。复用平台已有 ONNX 解码契约和资产；实际执行器为 ONNX Runtime CPU。

- ONNX SHA256：`62a3751662e06c678debb54b113c211d918f245ea6d3aea0b09fc418b8fc7705`。
- 平台原有许可记录：`AGPL-3.0-only`。

### 安全帽模型

来源：[keremberke/yolov8n-hard-hat-detection](https://huggingface.co/keremberke/yolov8n-hard-hat-detection/tree/287bafa2feb311ee45d21f9e9b33315ff6ff955d)，固定修订 `287bafa2feb311ee45d21f9e9b33315ff6ff955d`。

- 原始两类标签 `Hardhat / NO-Hardhat` 映射到平台 `helmet / no_helmet`。
- PT SHA256：`05ed3a517485292d42d6eb6c9be3987ea51cd162e04807d2741eadcac8a19e6c`。
- 最终 320×320 ONNX SHA256：`07cf81b9a793918fca981b3f40a2e87f91d2a1c478366fde0f798472cfd8c177`。
- 导出：Ultralytics 8.4.142、PyTorch 2.10.0 CPU、ONNX 1.20.1，固定输入、opset 17。
- 上游未声明许可证，平台如实记录 `LicenseRef-Upstream-Unspecified`，未套用其他派生仓库的许可。

## 部署中发现并解决的问题

1. 原六类 PPE 模型实际只识别六类防护用品，没有人员或未戴帽类别，但预置 manifest 错列了十类。已修正源 manifest，保留已发布历史版本记录；最终场景采用独立人员模型和具有明确未戴帽标签的模型。
2. 原 PT 模型的在线 PyTorch 依赖安装失败并占用命令队列。终止了该失败安装的 pip 子进程，让平台自然记为失败；清理仅限本轮未使用的失败依赖目录与下载缓存，保留原环境和回滚快照。最终 ONNX 模型复用已有依赖。
3. PPE 后处理原本把正常佩戴和未知状态人员也交给通用 ROI 规则，可能产生错误告警。新增明确未佩戴候选过滤；预览继续保留全部人员及其 PPE 状态。规则窗口在候选消失时补入负样本并重置持续时间，避免间断观测累积成连续违规。
4. 原流程要求 Pipeline 先验收 PASS 才能运行，但现场视频验收又依赖运行任务。补充显式现场验证模式，Java、Runtime 和任务 UI 一致执行。只允许 PENDING / BLOCKED_EXTERNAL_ASSETS 的现场验证；模型发布、目标节点部署 Ready、单图测试、规则和租户检查全部保留，正式运行仍要求 PASS。
5. 联调期间控制端日志队列阻塞，HTTP 请求超时。保存线程诊断后恢复控制端，并从独立复制的已构建 JAR 启动，控制台输出写文件；后续构建不覆盖正在运行的 JAR。

## 验证记录

- 摄像头连接检查 `5` 成功：认证、取流、关键帧均通过；主码流为 3840×2160 HEVC，浏览器子码流实测为 640×480。
- Runtime 回归：153 项通过；覆盖正常佩戴、未知状态不告警，明确缺失告警，负帧重置窗口和现场验证门禁。
- Java 定向回归：AlgorithmServiceImplTest 13 项、TaskValidationModeTest 2 项、TaskSettingsServiceImplTest 1 项通过。
- Java reactor 打包、前端 TypeScript 检查、任务页面 ESLint 通过。
- 浏览器检查：任务向导默认“正式运行”，开启“现场验证”后显示明确说明及待验证安全帽 Pipeline；未提交检查用表单。
- 固定公开测试集：[keremberke/construction-safety-object-detection](https://huggingface.co/datasets/keremberke/construction-safety-object-detection)，修订 `a19eace121442bce60da9f5036dc16bf9f2f6fa6`，test split 前 30 张，先固定样本再推理，保存标签和逐文件哈希。
- 320 输入在这 30 张参考样本中，helmet TP/FP/FN 为 17/3/5，no_helmet 为 4/1/3。该小样本存在漏检，不能作为工业现场正式验收或上游自报精度的复现。
- 比较过 17 类 PPE 替代版本 `118`；其人员检测在参考样本和现场画面不满足组合需求，最终未用于任务。比较记录与失败部署均保留。

证据目录：`artifacts/helmet-deployment-20260906/`。`selected-models.json` 为最终模型绑定；`hardhat-comparison.json` 为逐图比较；`rule.json`、`pipeline.json` 为平台返回记录。目录不含设备密码、登录令牌或临时签名下载地址。

## 首次上线检查（12:27 历史快照）

- 最终节点部署 **22**：`SUCCEEDED / COMPLETED / 100%`，目标与实际版本均为 **`source-12943852cbb3`**。本轮先前部署 21 同样成功，其后由 22 加入完整现场验证协议。Runtime `/v1/health=UP`，两个 systemd 服务均 active；控制面 `/actuator/health=UP`。
- 人员模型部署 **9**、安全帽模型部署 **10** 均 `READY / ONNX_RUNTIME_MANIFEST / CPU`。
- 节点单图测试 **8、10** 使用真实摄像头先前抓拍照片：识别 2 名人员，其中 1 名关联明确 `helmet=absent`，另一名 `unknown`；只有明确缺失者成为事件候选。人员推理 1331 ms，安全帽推理 368 ms。
- 节点单图测试 **9、11** 使用公开戴帽参考图 `test-001.jpg`：人员置信度 0.8784、安全帽置信度 0.8963；按同一 Pipeline 后处理得到 `helmet=present`，事件候选数为 0。此项是**参考图片实机推理与后处理验证**，不是摄像头前的真人戴帽测试。
- 任务 **2**：`现场未佩戴安全帽识别 / field-no-helmet-207`，实际与期望状态均 `RUNNING`，配置版本 1。
- 本次 Run：**`4df72acb-f532-4571-8039-eaeadc6491bd`**，启动于 2026-09-06 12:23:29（北京时间）；启动命令 `3836a18b-6761-4a93-aec9-cf8bdc64d6b5`。
- 12:27:08 快照：已连续运行 219 秒，分析 0.414 FPS，单轮总耗时 2387 ms，分析处理耗时 P95 2586 ms，队列深度 1，无错误码。该耗时是 Runtime 分析指标，不等同于从摄像头到浏览器或告警送达的端到端延迟。配置采样率为 0.5 FPS，硬件实际吞吐低于设定值。
- 通过平台 WebSocket 接收到该 Run 的连续 18 个真实 Overlay 帧，原始尺寸 640×480。当前工位画面未形成可确认人员目标，帧对象列表为空；平台任务事件数 **0**。
- 节点资源观察：可用内存约 668 MiB、可用磁盘约 1703 MiB；没有发生 OOM 或服务失败。源部署的回滚快照保留。

完整在线快照为 `deployment-verification.json`；四次模型实机测试为 `node-model-validation.json`；正反例关联结果为 `node-ppe-association-validation.json`；真实预览数据为 `live-overlay-sample.json`；任务绑定为 `task.json`。

## 首次部署时的现场验收安排

让一人在镜头前无遮挡位置先不戴安全帽、再戴安全帽，各停留约 15 秒。检查未戴帽事件进入 LInsight，事件快照确认为明确缺失人员，截图和录像可查看；戴帽阶段无新增违规事件，同时确认恢复和冷却去重。当前事件录像沿用平台全局设置：前 10 秒、后 20 秒，因此触发后应额外等待后录与上传完成。

首次部署收尾时，现场尚未提供这组对照过程；以上 12:27 快照不代表后续一直没有事件。后续实际结果见下节。正式生产验收仍需代表性固定视频集、漏报误报统计和业务认可的指标门槛。

## 继续验收：真实告警与录像时间轴修复

- 首轮 Run 连续运行约 5.5 小时后仍健康，分析约 0.419 FPS；累计产生真实未戴帽事件 **219、220**，均通过 `CREATED → RECOVERED → CLOSED` 完成 Runtime 状态流转。
- 事件 220 的现场回放清楚显示一名未戴安全帽的人员，检测快照绑定 `track-41`，人员置信度 0.5854，明确未戴帽置信度 0.9097。事件 219 为 `track-37`，明确未戴帽置信度 0.6350。
- 两条事件均有 READY 截图和 H.264 录像；已逐一读取文件并核对平台记录的文件大小及 SHA256，四份媒体全部匹配。详情与完整性证据分别为 `event-219.json`、`event-220.json`、`historical-media-integrity.json`，不保存临时媒体访问地址。
- 浏览器及 ffprobe 共同确认旧录像存在缺陷：两段均只有 14 帧，按固定 5 FPS 编码为 2.8 秒。Runtime 的真实帧间隔约 2.4 秒，不能直接把帧数按配置帧率换算成录像时间。
- 修复仅在既有 Runtime 取证模块：用 FFmpeg concat 的逐帧时间间隔保留真实采样时间，配置 FPS 只控制编码输出频率；将最后一帧的保持时间限定为一个输出间隔，并保留预录窗口边界前的最近一帧。没有更换推理、视频协议或业务状态机。
- 回归增加真实 FFmpeg/ffprobe 校验：不规则低频采样覆盖 30.3 秒，加一个输出帧后录像约 30.5 秒，误差不超过 0.2 秒。全部 **154 项 Runtime 测试通过**，取证模块 Ruff 检查通过。
- 历史录像保留原件，不篡改已上传的事件证据；修复用于新生成的录像。

## 录像修复后的部署与实机验证结果（18:12 历史记录）

- 平台源码升级 **23** 已成功，状态 `SUCCEEDED / COMPLETED / 100%`，目标与节点实际版本一致：**`source-61d11147a953`**。原任务 **2** 经平台停止、升级、重新启动，配置、模型绑定和规则版本沿用已验证值。
- 该轮 Run：**`0cbfdaa3-c431-4761-85eb-fae2e9d5c054`**，启动命令 `9db856d2-f56f-40f4-962a-9efa75308cd7`；18:12:41 心跳为 `RUNNING`，无错误码，分析约 **0.391 FPS**。本轮新 Run 的事件计数从零开始，任务历史中仍保留前一 Run 的 2 条真实告警。
- 控制面健康状态 `UP`；浏览器真实预览 `paused=false / readyState=4 / error=null`，640×480，播放时间持续前进，Overlay 通道已连接。
- 节点安装后的 `ai_runtime/app/event/evidence.py` SHA256 与本地验证代码一致：`1ec39c888a9f2b85efb7c5c33b83d5db03238560a9c53ae680edf187056b9d1d`。
- 使用当前 Run 写出的 **15 帧真实摄像头采样**在节点独立诊断目录验证编码器，采样跨度 **31.963 秒**，生成 **32.2 秒** H.264 / 640×480 / 5 FPS / 161 帧录像。差值符合末帧保持及输出帧量化范围。此检查验证新编码器，不创建或上传业务告警；记录包含每张采样帧和录像的 SHA256。
- 编码验证记录：`node-codec-timing-verification.json`。完整最终在线快照：`deployment-final-verification.json`；升级与重新启动记录：`evidence-fix-deployment.json`。
- 节点收尾可用内存约 **694 MiB**，可用磁盘约 **1642 MiB**。为通过升级预检，将较旧快照 21 压缩并经 tar 内容比对后保存为 root 可读归档，清理 pip 下载缓存及 APT 可重建索引缓存；当前环境、初始快照和最近回滚快照保留。

功能验证覆盖真实识别、告警入库、截图和录像上传、浏览器回放、恢复/关闭以及本轮录像时间轴修复。真人戴帽视频对照、代表性现场事件精度/召回及误报漏报统计尚未完成；公开戴帽图片实机测试和两条真实正例不能替代正式生产精度验收，因此没有把 Pipeline 标记为 PASS。

## 最新状态：识别展示与性能优化

后续已按用户反馈完成摄像头能力展示、PPE 业务标签、采样画面与框同步及 CPU 线程优化。平台源码部署 **24** 成功，当前节点版本 **source-f8dd2c0f0105**，当前 Run **93fd0c23-357e-40ee-a39a-73f47d3d2d13**，任务保持 RUNNING。分析约 **0.62 FPS**，处理约 **1.53 秒**。完整过程与证据见 [安全帽识别展示与性能优化](HELMET_PREVIEW_OPTIMIZATION_20260906.md)。
