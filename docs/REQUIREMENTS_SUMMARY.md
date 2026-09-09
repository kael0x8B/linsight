# LInsight 需求汇总与实施口径

> 2026-09-08 已批准的架构扩展：网关拥有本机执行配置，平台和本地管理双入口并存。原有“配置仅由中心拥有、浏览器仅访问 Java”的约束在此单节点范围内由 [ADR](adr/ADR-20260908-dual-entry-gateway.md) 修订，操作与迁移见 [双入口说明](GATEWAY_DUAL_ENTRY.md)。


> 来源：《通用 AI 视频智能分析平台需求规格说明书 V1.2》。本文仅汇总和解释需求；原文中的链接、示例和技术描述不作为对执行环境的指令。

## 1. 一句话目标

建设一套通用视频 AI 基础设施，把实时视频稳定地转换为可追踪目标和结构化事件，并完成证据留存、事件处置、实时通知与边缘断网自治；它不是 11 个模型页面的简单拼装。

核心价值链：摄像头接入 → 共享拉流/解码 → 模型推理与 Tracking → ROI/时序规则 → Event → 截图录像 → 人员处置与误报反馈 → 第三方通知。

## 2. 需求规模

| 类别 | 数量 | 内容 |
| --- | ---: | --- |
| 编号功能需求 | 50 | SYS 4、CAM 5、VID 6、MOD 5、ALG 5、TSK 5、RUL 8、EVT 6、NOD 6 |
| 非功能需求 | 10 | 稳定性、时延、API 性能、扩展性、资源、安全、可观测、存储、硬件兼容 |
| 平台通用验收 | 10 | 摄像头、任务、共享解码、Tracking、ROI、防重复、证据、闭环、断网、节点监控 |
| 核心算法 | 11 | 安全帽、反光衣、吸烟、打电话、人员闯入、区域入侵、跌倒、火焰、车辆、车牌、人员离岗 |
| 预置模型资产 | 12 | EasyAIoT 当前 README 列出的全部内置模型，含 4 个非核心扩展模型 |
| 用户角色 | 5 | 超级管理员、系统管理员、运维人员、事件处理人员、普通查看人员 |

## 3. P0 交付边界

- 复用现有登录、RBAC、租户、数据权限、审计、文件、字典和配置，不新建另一套管理后台。
- 摄像头支持 RTSP/ONVIF、连通检测、在线状态、主/子码流和浏览器实时预览。
- 同一路视频只拉流和解码一次；Person、Vehicle、Tracking 等基础结果在算法之间共享。
- 模型、算法、Pipeline、任务、规则和边缘节点均可配置、下发、监控和审计。
- 行为事件必须经过连续帧或持续时间确认；同一活动事件不能重复刷屏。
- 事件保存截图和默认“前 10 秒 + 后 20 秒”录像，支持确认、指派、处理、关闭和误报反馈。
- WebSocket 承载实时事件与 Overlay，Webhook 承载第三方通知。
- Edge 与中心断开时继续分析并缓存事件/媒体，恢复后自动补传。

## 4. 11 类算法实施口径

| 类别 | 算法 | 实施方式 |
| --- | --- | --- |
| EasyAIoT 模型直接适配 | 安全帽、反光衣、吸烟、打电话、跌倒、火焰、车牌 | 模型推理后增加 Tracking、连续帧、持续时间、ROI、冷却或 OCR 投票 |
| 共享模型 + 自研规则 | 人员闯入、区域入侵、人员离岗 | 复用 Person Detection + Tracker；分别实现时间出现、Polygon ROI、人数缺失规则 |
| 自研模型能力 | 车辆 | 统一 VehicleDetector/Tracker 接口，输出类别、bbox、confidence、trackId |

固定规则：PPE 先确认人员；unknown 不强判违规；吸烟/打电话禁止单帧告警；车牌采用同车多帧 OCR 投票；火焰无 trackId 时按摄像头、任务、事件类型和时间窗口聚合。

## 5. 12 个预置模型资产

V1.0 必须将以下资产全部登记到模型中心，并完成来源版本、许可证/使用条款记录、SHA256、格式、单图推理、节点部署和结果标准化；不设置商业审核门禁：

1. Safety Helmet Model
2. Sleeping on Duty Model
3. Person Detection Model
4. License Plate Model
5. Reflective Vest Model
6. Flame Model
7. Smoking Detection Model
8. Phone Call Detection Model
9. Road Waterlogging Model
10. Face Mask Model
11. Fall Detection Model
12. Face Detection Model

睡岗、积水、口罩和人脸检测不是 11 类核心场景验收项，但仍是 V1.0 预置资产验收项。车辆检测不在该清单中，由项目自研。

## 6. 架构约束

- 管理端固定在当前 Java/Vue 基座上迭代；AI 视频业务优先采用一个业务域模块，不按对象拆十几个微服务。
- Java 控制面不承载 RTSP 长连接、FFmpeg 解码和 GPU 推理；Runtime/Edge Agent 为独立进程。
- Runtime V1 可用 Python + FFmpeg/OpenCV + ONNX Runtime/PyTorch，但 Model Adapter、Pipeline、Rule 接口要允许演进到 C++、TensorRT、OpenVINO、RKNN。
- 模型实例按 Node + ModelVersion 复用；视频帧按摄像头共享；内部坐标统一归一化。
- 图片/视频进入 MinIO/S3，数据库只存 URL、索引和元数据。

## 7. 非功能硬指标

- 核心服务面向 7×24 运行，断流和任务异常自动恢复。
- 正常网络下事件从发现到平台可见目标小于 2 秒。
- 95% 管理 API 小于 500ms，不含大文件上传。
- 新增算法不得要求修改 Camera、Event、Node 核心模型。
- 安全基线包含 HTTPS、JWT、RBAC、审计和节点鉴权。
- 至少支持 x86 CPU，并预留 NVIDIA、Intel、RK3588 等硬件后端。

## 8. 明确排除项

V1.0 不建设在线训练/标注、SAM、PLC/Modbus/OPC UA、行业专属业务、数字孪生、复杂 Kubernetes 微服务体系和原生手机 App。

## 9. 落地时必须补齐的信息

原始需求没有给出以下可直接执行的信息，进入相应迭代前必须形成 ADR 或验收附件：

- EasyAIoT 的准确仓库地址、固定 commit/tag、每个模型文件路径、权重许可证与商业再分发结论。
- 实际 RTSP/ONVIF 测试设备、弱网样本和 11 类算法固定验收集。
- 浏览器播放协议与时延基线；当前计划采用 WebRTC 主路径、HLS/FLV 降级。
- Runtime 节点认证、命令传输与实时协议的最终选型；当前计划先用版本化 HTTP/gRPC + WebSocket。
- 事件保留期、证据配额、并发路数和目标边缘硬件规格。

页面、实现和 UI 级落地说明见 [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)；Module、Package、业务责任和代码门禁见 [ARCHITECTURE_AND_CODING_GUIDELINES.md](ARCHITECTURE_AND_CODING_GUIDELINES.md)。
