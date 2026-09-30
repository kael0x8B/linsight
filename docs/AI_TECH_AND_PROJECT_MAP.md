# LInsight AI 技术与项目架构学习地图

> 面向项目负责人和刚开始学习本项目的开发者。核对日期：2026-09-23。
> 根据当前工作区源码、依赖声明、部署脚本及架构决策整理，包含尚未提交的代码。本文说明“代码如何组成和工作”，不代表所有模型已安装到现场盒子，也不代表所有算法已通过效果验收。

阅读导航：**第 1–3 节看整体，第 4–5 节学 AI，第 6–10 节查目录，第 11–12 节看运行和部署，第 14 节按顺序读代码。**

## 1. 先用一分钟看懂项目

**LInsight 是一套视频 AI 分析系统：平台负责管理，盒子负责分析摄像头画面，再把识别事件和证据交给平台或业务系统。**

```text
LInsight
├── 中心平台：管理多台盒子、多路摄像头和人员权限
│   ├── Vue 前端：用户看见和操作的网页
│   ├── Java 后端：管理配置、模型、算法、任务、事件、节点
│   └── MySQL / Redis / MinIO：存业务数据、缓存和文件
│
├── 边缘盒子：放在摄像头附近的计算设备，也叫边缘节点/网关
│   ├── AI Runtime：读取视频、执行模型、判断规则、保存证据
│   ├── Edge Agent：连接平台、接收命令、上报状态、补传事件
│   ├── 本地管理网页：直接访问盒子也能配置和查看
│   └── 本地模型文件 + SQLite + 截图/录像：支持离线运行
│
├── 摄像头：通过 RTSP 提供视频
└── 外部业务系统：按配置接收平台 Webhook 或盒子事件接口
```

可以先记住四句话：

1. **前端负责“看和操作”。**
2. **Java 负责“管理和下发”。**
3. **Python Runtime 负责“看视频和算结果”。**
4. **Edge Agent 负责“让盒子和平台保持联系”。**

这里的“盒子”是部署位置。Runtime、Agent 是运行在盒子上的程序，也可以放在符合依赖要求的服务器上运行。

## 2. 平台到盒子：实际运行布局

### 2.1 哪些程序放在哪里

```text
中心服务器 / 开发电脑
├── 管理网页静态资源                     开发时默认 :5666
├── linsight-server                     Java API，开发默认 :48888
│   ├── system：用户、角色、租户、权限
│   ├── infra：文件等基础设施
│   └── ai-video：AI 视频业务
├── MySQL                               中心业务数据库
├── Redis                               会话、缓存、协调状态
└── MinIO                               模型、截图、录像等对象文件
             │
             │ HTTP(S)：注册、心跳、命令、结果和事件上报
             │ WebSocket：Agent 主动建立反向通道，承载预览/网关 RPC
             ▼
边缘盒子，例如具备 RK3566 的 Linux ARM64 设备
├── Edge Agent 进程
│   ├── 主动连接平台，不直接访问平台 MySQL
│   ├── 下载并校验模型、接收任务和升级命令
│   └── 调用本机 Runtime、上传状态和本地积压事件
│             │ 本机 HTTP API
│             ▼
├── AI Runtime 进程
│   ├── 127.0.0.1:48900                 内部接口
│   ├── 0.0.0.0:48901                   本地管理网页和登录接口
│   ├── 视频处理 + 模型推理 + 规则 + 证据
│   └── 按需要启动模型/算法工作子进程
├── CPU / 可用的 Rockchip NPU
└── 本地磁盘：模型、配置、SQLite、截图、录像、升级文件
             ▲
             │ RTSP 视频
             │
          摄像头
```

端口是当前默认值，可由部署配置调整。48901 和 48900 由同一 Runtime 进程提供不同入口；本地网页不需要再部署一套 Java、MySQL 或独立 Node.js 服务。

### 2.2 三条链路分别理解

| 链路 | 走向 | 内容 |
| --- | --- | --- |
| 管理链路 | 浏览器 → Java → Agent → Runtime | 配置、启停、模型部署、设备管理 |
| 视频链路 | 摄像头 → 盒子 → 浏览器 | 实时预览使用 WebRTC；信令经平台/Agent 转发，Java 不代理逐帧实时媒体 |
| 结果链路 | Runtime → 本地保存 → Agent → 平台 | 检测结果、事件、截图、录像、运行指标；检测框再与播放帧对齐 |

本地访问时，浏览器直接访问盒子 48901，使用设备独立登录。平台工作台和本地网页操作的是**同一台盒子的实际执行配置**，版本校验用于防止两边互相覆盖。

平台管理中心资产和跨节点编排；盒子保存本机执行配置。模型和配置已准备好的任务，可在中心断开后继续运行，并由 Runtime 在重启后恢复。中心断网自治并不等于摄像头断流后仍能识别。

本地独立创建的任务可以从平台网关工作台查看，但不会自动变成中心任务目录和中心事件库中的记录。

## 3. 先分清：模型、算法、规则、任务

这是理解本项目最重要的一组概念。

| 概念 | 通俗解释 | 本项目例子 |
| --- | --- | --- |
| 模型 Model | 学习好的识别能力，通常是一份权重文件 | 人员检测模型、安全帽模型、车牌 OCR 模型 |
| 模型版本 ModelVersion | 一份确定的模型文件及执行说明 | 文件 SHA256、输入尺寸、类别表、格式、预处理方式 |
| 算法 Algorithm | 如何使用、组合和解释模型结果 | 将人员框与安全帽框关联，判断每个人的佩戴状态 |
| Pipeline | 多个处理步骤的连接关系 | 车辆检测 → 车牌检测 → 裁剪矫正 → OCR |
| 算法包 | 可单独发布的算法代码和参数说明 | `algorithm.json` + `processor.py`，模型权重独立管理 |
| 规则 Rule | 什么条件成立才形成事件 | 在指定区域，最近 M 帧有 N 帧命中，持续一定时间，设置冷却间隔 |
| 任务 Task | 把能力绑定到具体摄像头和盒子 | 1 号摄像头 + 安全帽算法 + 模型版本 + 规则 + A 盒子 |
| 事件 Event | 经确认后可留证、上报、处置的业务结果 | 某时间、某摄像头发现未戴安全帽，附截图和录像 |

```text
一个“安全帽识别任务”
├── 摄像头：从哪里获取画面
├── 节点：在哪台盒子计算
├── 模型：用哪个人员模型、哪个安全帽模型
├── 算法：如何把帽子和人关联
├── 规则：在哪个区域、连续确认多久、多久可以再次告警
└── 输出：识别框、人员状态、确认事件及证据
```

**画面上出现识别框，不等于已经产生事件。** 模型输出候选结果，算法解释含义，规则进一步确认。未看清的状态可以是 `unknown`，不能直接当成违规。

## 4. AI 相关技术：用了什么，为什么用

### 4.1 模型与推理技术

| 技术 | 一句话理解 | 当前项目中的用途与位置 |
| --- | --- | --- |
| 计算机视觉 / 深度学习 | 从图像中识别人、物体和行为 | 项目的 AI 主体，执行代码集中在 `runtime/ai_runtime/app/` |
| YOLO 系列目标检测 | 一次推理找出目标类别和位置 | 已有通用 COCO、人员、PPE、跌倒、车牌等模型接入；具体类别以所绑定权重为准 |
| 图像分类 | 对整图或裁剪区域判断类别 | 接打电话使用人员裁剪图；疑似打架包对相邻人员组合区域做分类 |
| ONNX | 模型交换与部署文件格式 | 通用推理路径；`.onnx` 是模型文件，不是服务 |
| ONNX Runtime | 读取 ONNX 并计算结果的引擎 | Python 基础依赖，主要 CPU 执行路径；见 `model/person.py`、`model/generic.py` |
| PyTorch / TorchScript | 另一套模型加载与执行方式 | 可选 `pytorch` 依赖；`model/backends.py` 支持 TorchScript 和受控 PT 路径 |
| Ultralytics | YOLO 模型工具库 | 可选依赖，用于可信的 Ultralytics checkpoint；普通 `.pt` 不一定是 TorchScript |
| RKNN / RKNN Toolkit Lite2 | 在 Rockchip NPU 上运行模型 | `model/rknn.py`；盒子端条件依赖为 Lite2 2.3.2，受硬件、系统和 Python 版本限制 |
| RKNN Toolkit2 | 把模型转换成盒子能执行的 RKNN | 构建机脚本 `scripts/convert-rknn-model.py`，配套 `deploy/rknn-conversion/` |
| FP16 / INT8 | 模型数值精度与压缩方式 | 转换脚本提供相应路径；INT8 涉及校准，能否兼顾速度和效果需要实际测量 |
| NumPy / Pillow | 张量计算与图片处理 | 数组计算、缩放、裁剪、颜色转换、图片读写、坐标和后处理 |

CPU 是通用计算处理器，NPU 是面向神经网络的加速单元。**NPU 加速推理和硬件视频解码是两件事**：一个算模型，一个把压缩视频变成可用画面。

当前核心 Runtime 没有把 CUDA/TensorRT 配置为默认执行主链路。不能因为设备有 GPU，就认为代码会自动使用 GPU。

### 4.2 看懂一帧图像如何成为结果

```text
摄像头视频
  → 解码出图片
  → 抽帧：按任务需要选取部分帧
  → 预处理：裁剪、缩放、RGB/BGR 转换、归一化、转换张量排列
  → 推理：ONNX Runtime / RKNN / 可选 PyTorch 执行模型
  → 后处理：解释输出、过滤低分结果、去除重复框、恢复源图坐标
  → 跟踪和算法解释
  → 规则连续确认
  → 事件、截图、录像、界面展示
```

| 名词 | 在项目里解决什么问题 |
| --- | --- |
| confidence（置信度） | 模型对某个结果的分数，用阈值过滤；它不是现场准确率 |
| bbox（检测框） | 目标在画面中的位置，统一使用 0–1 归一化坐标 |
| NMS（非极大值抑制） | 同一个目标出现多个重叠预测框时，保留更合适的框 |
| IoU（交并比） | 衡量两个框重叠程度，用于去重与跨帧匹配 |
| trackId（跟踪 ID） | 在连续帧中尽量认出“还是刚才那个目标” |
| ROI（关注区域） | 用户在画面上画出的区域，只对相关范围判断规则 |
| N/M 帧确认 | 最近 M 次观测中，至少 N 次满足条件才确认 |
| cooldown（冷却） | 避免同一情况持续发生时频繁重复通知 |

项目当前跟踪器是 `capability/tracker.py` 中的 **IoUTracker**，另有针对特定运动类别的运动/文字辅助关联。不要把它理解为已经接入了 ByteTrack、DeepSORT 或跨摄像头身份跟踪。

### 4.3 车牌识别与人脸比对

```text
车牌识别
├── 检测车辆 / 定位车牌（依配置选择模型）
├── 获取车牌四角、裁剪和透视矫正
├── OCR 模型：把图片变成字符序列
├── CTC 解码：合并重复字符、去掉空白标记
├── 多帧投票与跟踪：同一目标连续观察，提高稳定性
└── 确认车牌事件，并进行短时间去重

人脸比对
├── YuNet：找到人脸和关键点
├── 人脸对齐与质量检查
├── SFace：提取 128 维特征向量
├── 归一化特征与已授权人员特征比较相似度
└── 按阈值、ROI 和时序条件输出匹配结果
```

车牌代码在 `model/plate.py`、`task/plate_pipeline.py` 和 `capability/postprocess.py`；旧适配路径中还保留 YuNet 车牌检测及 LPRNet OCR。人脸代码在 `model/face_pair.py`、`task/face_verification.py` 和 `algorithm_packages/face/`。

人员库保存参考人员资料，特征提取把参考照片变成可比较的数字向量。这里的身份比对本身不等于活体检测，也不自动执行门禁设备控制。

### 4.4 视频与实时显示技术

| 技术 | 作用 | 当前代码 |
| --- | --- | --- |
| RTSP | 摄像头提供实时码流的协议 | `stream/probe.py`、`stream/shared.py` 等 |
| FFprobe / FFmpeg | 探测视频、媒体处理和兼容路径 | `stream/`、`event/evidence.py` |
| PyAV | 在 Python 中访问 FFmpeg/LibAV 能力 | `stream/shared.py`，处理包、帧和软件解码 |
| GStreamer + Rockchip MPP | 在适配的盒子上硬件解码 | `stream/rockchip.py`、`rockchip_gst_helper.py`，需设备环境支持 |
| WebRTC + aiortc | 将实时视频送到浏览器 | `stream/webrtc.py`，Python 的 aiortc 与浏览器 WebRTC 协作 |
| 共享视频流 | 同一摄像头的任务复用拉流/解码资源 | `stream/shared.py`、`task/manager.py` |
| Overlay | 在视频上独立绘制识别框、文字、区域 | Vue 播放/叠加组件；按 `streamId/sourcePts/frameKey` 对齐 |
| HLS | 较早的预览方案和显式回滚兼容路径 | 仍有代码，当前实时预览以 WebRTC 为主 |

视频播放帧率与 AI 分析帧率是两项指标。例如视频每秒播放 25 帧，任务可能只分析其中数帧；这不要求网页也变成几张图片轮播。

### 4.5 让 AI 持续工作的工程技术

| 技术 | 为什么需要 | 代码入口 |
| --- | --- | --- |
| FastAPI + Uvicorn | 提供 Python 服务接口及生命周期 | `ai_runtime/app/main.py`、`api/http.py` |
| Pydantic | 校验请求、模型配置和结果结构 | 各目录的 `contracts.py`、`model/manifest.py` |
| asyncio + 有界队列 | 同时处理视频、命令和结果，避免无限积压 | `stream/shared.py`、`task/manager.py` |
| ModelPool | 复用已加载模型，管理租约、容量和卸载 | `model/pool.py` |
| 声明式 Runtime Manifest | 明确模型输入、预处理、输出解码方式 | `model/manifest.py`、`model_assets/runtime-manifests-v1.json` |
| 算法包 SDK | 扩展业务算法，复用模型池和事件机制 | `capability/packages.py`、`package_runner.py`、`package_worker.py` |
| SQLite WAL | 在盒子本地保存配置、事件和待投递记录 | `gateway/store.py`、`event/store.py` |
| SHA256、版本与幂等键 | 确认文件一致，避免重复命令和旧配置覆盖 | 模型下载、算法包、Agent 命令、网关配置 |
| 重试、ACK、指数退避 | 网络断开后补传，确认成功后再处理本地记录 | `event/store.py`、`edge_agent/app/command/` |
| HTTPX / WebSocket / TCP | 服务通信、反向通道与盒子事件订阅 | Agent `client/`、`preview_tunnel.py`、Runtime `gateway/event_stream.py` |
| SSH + systemd | 初装、升级和守护盒子上的常驻进程 | Java `service/node/NodeDeploymentRunner.java` |
| psutil / 运行快照 | 获取 CPU、内存、磁盘和运行指标 | Agent `heartbeat/`、Runtime `observability/` |

算法包用子进程进行故障隔离；它并不是不可信代码的安全沙箱。一个 ZIP 模型包与一个 ZIP 算法包也不是同一种东西：前者装模型资产及执行说明，后者装算法代码和参数说明。

## 5. 现有算法是如何组合的

以下是代码中的实现方式，不是模型效果排名或现场验收结论。

| 场景 | 主要组成 | 学习入口 |
| --- | --- | --- |
| 安全帽 / 反光衣 | 人员检测 + PPE 检测 + 人体关联 + 连续确认 | `algorithm_packages/helmet/`、`vest/` |
| 区域入侵 | 人员检测 + 跟踪 + ROI + 时序规则 | `algorithm_packages/region/` |
| 异常停留 / 车辆违停 / 箱包滞留 | 目标检测 + 跟踪 + 停留/静止规则 | `person-dwell/`、`vehicle-parking/`、`bag-stationary/` |
| 区域人数超限 | 检测区域内人员 + 数量条件 + 确认规则 | `crowd-limit/` |
| 人员统计 | 统计 ROI 当前人数，含 0 人 | `people-counting/`；不是累计经过人数 |
| 人数型离岗 | 检测区域是否有足够人员 | `person-absence-count/`，保留的历史版本 |
| 指定人员离岗 | 人员检测 + 授权人脸特征比对 + 离岗规则 | `person-absence/`；其他人不能代替指定人员 |
| 人员库刷脸 | 人脸检测/特征模型 + 授权人员库 | `face/`；另有入口主动核验执行路径 |
| 接打电话 | 人员检测 → 人体裁剪 → 行为分类 → 连续确认 | `task/inference.py` |
| 禁带区域手机 | 检测 `cell_phone` + 区域规则 | `phone-presence/`；与“正在打电话”语义不同 |
| 疑似打架 | 相邻人员区域 + 行为分类模型 + 复核标记 | `fighting/`；相邻本身不是打架证据 |
| 跌倒 | 使用输出 `fall` 类别的模型 + 规则确认 | `fall/` |
| 动物 / 非机动车 / 禁行车辆 | 通用检测模型 + 指定类别过滤 + 区域规则 | `animal-intrusion/`、`nonmotor-intrusion/`、`vehicle-intrusion/` |
| 消防通道占用 | 人车物中指定类别 + 通道区域及规则 | `fire-lane/` |
| 车牌识别 | 车辆/车牌检测 + OCR + 多帧投票 | `task/plate_pipeline.py`、`algorithm_presets/` |

**一个模型可以被多个算法复用，一个算法也可以用多个模型。** 区域入侵、停留和人数统计并不意味着分别训练了三个独立神经网络。

`model/registry.py` 还列出了火焰、吸烟、睡岗、积水、口罩、姿态、通用 OCR 等适配契约名称。注册表出现名称，只说明系统声明了对应契约，不能据此判断权重已就绪或算法可直接验收。

## 6. 项目根目录：第一层地图

以下目录树只保留理解项目所需的主要分支；省略第三方依赖、缓存、重复测试和大量生成文件。

```text
linsight/
├── README.md                       项目总入口、启动方式
├── Makefile                        常用构建、启动、部署检查命令
├── .env.example                    环境变量模板
├── backend/                        Java 中心平台
├── frontend/                       Vue 平台网页 + 盒子网页的源码
├── runtime/                        Python AI Runtime + Edge Agent
├── deploy/                         Docker 依赖、监控、RKNN 转换环境
├── scripts/                        启动、打包、模型转换、验收脚本
├── docs/                           规范、协议、使用与运维文档
├── acceptance/                     验收配置模板、数据集说明
├── evidence/                       验收证据、现场附件
├── artifacts/                      报告、模型实验及生成产物
├── var/                            本机模型、日志和运行数据
└── .codex-tmp/                     开发临时文件和试验备份
```

前三个核心源码目录是 **backend、frontend、runtime**。`var/` 和 `runtime/var/` 可能存着真正运行的数据；它们不是看到名字就可以删除的缓存。

## 7. Java 后端：Module 与 Package 怎么分

### 7.1 Maven Module：按大职责分工程

```text
backend/
├── pom.xml
├── linsight-dependencies/           统一管理依赖版本
├── linsight-framework/              公共技术基座
│   ├── linsight-common/             通用结果、分页、异常等
│   ├── linsight-spring-boot-starter-web/
│   ├── linsight-spring-boot-starter-security/
│   ├── linsight-spring-boot-starter-mybatis/
│   ├── linsight-spring-boot-starter-redis/
│   ├── linsight-spring-boot-starter-websocket/
│   ├── linsight-spring-boot-starter-biz-tenant/
│   └── ...                         数据权限、日志、任务等 Starter
├── linsight-module-system/          用户、组织、租户、权限等
│   ├── linsight-module-system-api/
│   └── linsight-module-system-server/
├── linsight-module-infra/           文件和技术基础设施
│   ├── linsight-module-infra-api/
│   └── linsight-module-infra-server/
├── linsight-module-ai-video/        AI 视频控制面业务
│   ├── linsight-module-ai-video-api/
│   └── linsight-module-ai-video-server/
├── linsight-server/                 聚合启动入口，最终运行的中心服务
└── linsight-gateway/                保留的中心服务网关工程
```

**多个 Maven Module 不等于多个微服务。** 当前中心使用模块化单体：各业务实现聚合到 `linsight-server`。本地默认不需要启动 Gateway/Nacos。

特别容易混淆：`backend/linsight-gateway` 是中心服务网关工程；Python `ai_runtime/app/gateway` 是边缘盒子的本地管理能力，两者不是同一程序。

`*-api` 是供其他 Java 模块使用的稳定接口/DTO/常量，不是管理网页接口所在目录。当前 AI Video 的 `api` 子工程很小，主要是常量和包声明；实际 HTTP Controller 在 `*-server`。

### 7.2 AI 视频模块内部：先分技术层，再分业务域

源码前缀：`backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/`。

```text
com/linsight/module/aivideo/
├── config/                         模块配置
├── controller/
│   ├── admin/                      平台管理接口
│   │   └── 各业务域/vo/            入参和返回结构
│   └── node/                       盒子注册、上报和命令等接口
├── service/                        业务处理和流程编排
│   ├── camera/                     摄像头、分组、预览和能力摘要
│   ├── model/                      模型资产、版本、部署和测试
│   ├── algorithm/                  算法、Pipeline、算法包、人员库
│   ├── rule/                       ROI、规则与结构校验
│   ├── task/                       任务启停、运行状态、入口识别
│   ├── event/                      事件记录、证据和处置
│   ├── node/                       节点、SSH 部署、升级、网关工作台
│   ├── integration/                对外集成业务
│   └── settings/                   当前实现中的 AI 全局参数
├── dal/
│   ├── dataobject/                 表对应的 DO
│   ├── mysql/                      数据读写 Mapper
│   └── redis/                      缓存访问
├── convert/                        不同数据对象之间转换
├── enums/                          枚举、状态和错误码
├── integration/
│   ├── runtime/                    Runtime 客户端、节点反向通道
│   ├── ssh/                        SSH 接管和部署适配
│   └── webhook/                    外部 HTTP 投递适配
├── job/                            定时触发
├── mq/                             消息定义、生产与消费代码
└── framework/                      本模块安全、文件等支持
```

除 `service` 外，Controller、DO、Mapper 等层也按领域细分；上图未把每个领域重复展开。`mq/` 或公共 MQ Starter 的存在不表示本地开发必须再启动 Kafka/RabbitMQ。

读 Java 时沿下面的顺序查：

```text
网页请求
  → Controller：接收参数、检查权限
  → Service：业务校验、编排、状态变化
  → Mapper / DAL：数据库读写
  → MySQL

需要操作盒子时：Service → Integration / 节点命令 → Agent → Runtime
```

例如：`CameraController.java` → `CameraServiceImpl.java` → `CameraMapper.java` → 摄像头表。

数据库初始化在 `backend/sql/mysql/linsight.sql`；增量迁移在 `backend/sql/mysql/migrations/ai-video/`。Java 基座使用 Java 17、Spring Boot 3.5.x、MyBatis/MyBatis-Plus、Spring Security 和 Maven。

## 8. Vue 前端：平台页面与盒子页面在哪里

```text
frontend/
├── package.json / pnpm-workspace.yaml   pnpm 工作区
├── apps/web-antd/                       实际业务应用
│   ├── index.html                      平台网页入口
│   ├── gateway.html                    盒子独立网页入口
│   └── src/
│       ├── main.ts                     平台启动入口
│       ├── gateway/                    盒子网页启动与应用
│       │   ├── main.ts
│       │   ├── bootstrap.ts
│       │   └── gateway-app.vue
│       ├── api/ai-video/               TypeScript 类型和后端请求
│       │   ├── camera/ model/ algorithm/ rule/ task/
│       │   ├── event/ node/ node-log/
│       │   └── recognition-library/ settings/ webhook/
│       ├── views/ai-video/             页面
│       │   ├── camera/                 摄像头管理
│       │   ├── live/ wall/             实时预览、视频墙
│       │   ├── model/ model-test/      模型资产及测试
│       │   ├── algorithm/              算法与算法包
│       │   ├── algorithm-validation/   算法验证
│       │   ├── recognition-library/    人员/识别库
│       │   ├── rule/ task/ event/      规则、任务、事件
│       │   ├── node/ node-logs/        节点、网关工作台、日志
│       │   └── settings/ webhook/     全局参数、通知集成
│       ├── components/ai-video/        多页面共用的视频/ROI 等组件
│       ├── router/                     路由
│       ├── store/                      页面间共享状态
│       └── locales/                    中英文文案
├── packages/                           Vben 共享 UI、请求、状态、工具
├── internal/                           Vite、TypeScript、代码检查配置
└── tests/                              前端回归测试
```

技术组合是 **Vue 3 + TypeScript + Vben Admin + Ant Design Vue + VxeGrid + Pinia + Vite**，使用 pnpm/Turbo 管理工作区和构建。页面中的 `modules/` 是该页面私有组件，不是另一个后台服务。

盒子网页复用同一前端工程，构建后生成 `runtime/gateway-console/`，由 Python Runtime 提供静态资源。盒子运行时不需要安装整个前端开发工具链。

视频相关代码可以从这三个文件开始：

- `components/ai-video/camera-preview-player.vue`：预览入口。
- `components/ai-video/synchronized-recognition-video.vue`：画面与结果同步。
- `views/ai-video/live/modules/preview-overlay.vue`：绘制识别结果。

## 9. Python Runtime：真正计算 AI 的代码地图

```text
runtime/
├── pyproject.toml                   Python 依赖和测试配置
├── ai_runtime/app/                  AI 计算主体
│   ├── main.py                     创建应用、组装服务、管理生命周期
│   ├── api/http.py                 内部 HTTP API
│   ├── core/                       配置与依赖环境
│   ├── stream/                     视频输入与播放
│   │   ├── probe.py                视频连通性探测
│   │   ├── shared.py               共享媒体源、分发、解码
│   │   ├── frames.py               分析帧处理
│   │   ├── webrtc.py               WebRTC 会话
│   │   ├── rockchip.py             Rockchip 硬解适配
│   │   ├── rockchip_gst_helper.py   GStreamer 辅助进程
│   │   └── overlay.py / frame_stamp.py  识别结果与源帧时间标记
│   ├── model/                      模型执行层
│   │   ├── pool.py                 模型池与容量/租约管理
│   │   ├── deployed.py             本地已安装模型登记
│   │   ├── manifest.py             输入、输出、预处理声明
│   │   ├── registry.py             适配契约注册
│   │   ├── person.py / generic.py  ONNX 检测与通用输出处理
│   │   ├── backends.py             TorchScript、PT 等适配
│   │   ├── rknn.py                 Rockchip NPU 推理
│   │   ├── face_pair.py            人脸检测和特征提取
│   │   ├── plate.py                中文车牌检测和 OCR
│   │   └── isolated.py / worker.py 隔离模型执行
│   ├── capability/                 可复用能力与算法包运行
│   │   ├── tracker.py              IoU 跟踪
│   │   ├── postprocess.py          PPE、OCR 等结果处理
│   │   ├── packages.py             算法包契约和安装管理
│   │   └── package_runner.py / package_worker.py
│   ├── task/                       把输入、模型、算法、规则串起来
│   │   ├── manager.py              任务生命周期与逐帧循环
│   │   ├── inference.py            实时/单图共用推理逻辑
│   │   ├── plate_pipeline.py       车牌多模型编排
│   │   ├── face_verification.py    主动人脸核验
│   │   ├── entry_access.py / entry_station.py  入口识别流程
│   │   └── image_recognition.py / validation.py  图片测试和验证
│   ├── rule/                       区域与时序判断
│   │   ├── contracts.py            规则结构
│   │   └── engine.py               确认、恢复、数量、停留等规则
│   ├── event/                      事件和证据
│   │   ├── evidence.py             截图/录像缓冲与生成
│   │   └── store.py                SQLite、离线积压、重试、历史
│   ├── gateway/                    盒子自治和本地管理
│   │   ├── service.py              本机模型/任务/配置管理
│   │   ├── store.py                加密配置、版本、幂等记录
│   │   ├── api.py / console.py     网关接口和网页应用
│   │   ├── listener.py             本地网页监听生命周期
│   │   ├── console_artifact.py     网页制品校验和安装
│   │   ├── session.py              本地登录会话
│   │   ├── platform_connection.py  平台地址设置
│   │   ├── event_stream.py         盒子 TCP 事件订阅服务端
│   │   └── event_delivery.py       旧 HTTP 投递实现，仅供迁移核对
│   └── observability/              运行快照与指标
│
├── edge_agent/app/                  节点代理，见下一节
├── algorithm_packages/             业务算法包源码
├── algorithm_presets/              场景组合预设，如矿区车辆车牌
├── model_assets/                   模型来源、哈希、版本与执行清单
├── tests/                          Python 单测、回放和契约测试
├── deployment-wheels/              可生成的离线 Python 依赖制品
└── gateway-console/                可生成的盒子网页制品
    ├── manifest.json               制品及逐文件摘要
    ├── gateway-console-<摘要>.tar.gz
    └── current/                    校验后展开的网页资源
```

当前 `model_assets/` 主要是资产清单，不能把它等同于全部模型权重。实际权重由下载、部署、导入流程放入配置的数据目录。

注意这张图按实际源码画：证据在 `event/evidence.py`；不是把架构模板中的 `evidence/`、`client/` 等目录照搬成已存在目录。

### 9.1 一个算法包的文件结构

```text
runtime/algorithm_packages/helmet/
├── algorithm.json                  名称、版本、模型角色、参数 Schema、默认规则
├── processor.py                    业务处理：把模型结果解释成佩戴状态
└── README.md                       使用与结果说明
```

权重不塞进这个算法包。`sdk.infer(slot)` 使用任务绑定的模型；包的输出继续交给主程序完成跟踪、规则、证据和上报。升级算法包也不会自动替换正在运行任务所固定的版本。

## 10. Edge Agent：盒子与平台之间的联络程序

```text
runtime/edge_agent/app/
├── main.py                         注册与各后台循环的入口
├── core/
│   ├── config.py                   Agent 环境配置
│   └── identity.py                 节点身份和本地凭据
├── client/
│   ├── control_plane.py            调用 Java 平台
│   └── runtime.py                  调用本机 Runtime
├── heartbeat/resources.py          CPU、内存、磁盘等资源采集
├── artifact/download.py            下载文件、校验摘要
├── command/
│   ├── executor.py                 模型、任务等命令执行
│   ├── deployed_models.py          已部署模型相关状态
│   ├── lifecycle.py                生命周期操作
│   └── entry_*.py                  入口识别命令和证据处理
├── preview_tunnel.py               主动建立反向 WebSocket 通道
├── log_delivery/buffer.py          节点日志缓冲与投递
└── upgrade/
    ├── manager.py                  升级包管理
    ├── activation.py               激活/切换
    └── launcher.py                 升级启动支持
```

Runtime 与 Agent 是两种职责：前者计算，后者联络平台。当前离线事件持久化的核心在 Runtime `event/store.py`，不是假定 Agent 一定有一个 `offline/` 目录。

## 11. 一次真实识别的完整路径

以“平台部署安全帽任务”为例：

```text
1. 用户在 Vue 页面选择摄像头、盒子、算法、模型和规则
   ↓
2. Java 校验权限、配置、版本，保存中心编排信息
   ↓
3. 节点命令驱动 Agent 下载模型/算法包并校验 SHA256
   ↓
4. Agent 调用 Runtime；盒子保存实际执行配置
   ↓
5. Runtime 取得共享摄像头流，按任务采样画面
   ↓
6. ModelPool 执行人员模型与安全帽模型
   ↓
7. 算法关联人体和帽子，跟踪器维护目标标识
   ↓
8. RuleEngine 检查区域、N/M 帧、持续时间、冷却等条件
   ↓
9. 确认事件，生成截图/录像，先写本地耐久记录
   ↓
10. Agent 将平台任务的事件和证据同步中心；断网则重试补传
   ↓
11. Java 保存事件和证据元数据，网页显示并支持人工处置
```

另外还有独立的外发路径：

```text
Runtime 本地事件
├── Agent 上传 → 平台事件中心 → 平台 Webhook → 外部系统
└── 盒子 TCP 事件接口 ← 业务客户端连接并按任务/类型订阅
```

两条路径独立。客户端收到盒子 TCP 事件，不代表平台同步已经成功；平台 Webhook 和盒子订阅也可能让业务系统收到同一个源事件，需要按 `sourceEventId` 去重。2026-09-24 起旧 HTTP 直投已由 [TCP 订阅](GATEWAY_EVENT_DELIVERY.md) 取代。

## 12. 交付到服务器与盒子的到底是什么

### 12.1 中心平台的交付物

```text
中心交付
├── 前端构建后的 dist/               HTML、JS、CSS
├── linsight-server 服务 JAR         Java 聚合应用
├── 数据库初始化/增量 SQL
├── 运行配置
└── MySQL / Redis / MinIO 及各自持久化数据
```

`deploy/docker-compose.dev.yml` 当前启动的是开发用 MySQL、Redis、MinIO；不是整个生产平台和所有盒子的一键部署编排。

### 12.2 盒子的典型安装布局

下面是安装器使用的主要路径，不是源码目录；升级版本可能通过 release 指针切换。

```text
/opt/linsight/
├── runtime/                        Python 源码、算法资源、网关网页制品
└── venv/                           Python 运行环境及已安装依赖

/etc/linsight/                      节点运行配置

/var/lib/linsight/
├── runtime-data/                   模型、本机任务配置、事件、证据等
│   └── gateway/                    本地管理配置、密钥和连接信息等
├── preview/                        预览相关运行数据
├── edge-agent-credential.json       节点长期凭据
└── edge-agent/                     升级版本及切换状态等

/etc/systemd/system/
├── linsight-ai-runtime.service      守护 Runtime，连同本地网页
└── linsight-edge-agent.service      守护 Agent
```

这些路径以当前部署器为准，实际值还应查看节点配置。本地数据与程序分开，是为了升级程序时保留模型、任务和证据。

关键工程脚本：

| 脚本 | 用途 |
| --- | --- |
| `scripts/build-gateway-console.sh` | 构建并封装盒子网页 |
| `scripts/prepare-node-wheelhouse.py` | 准备匹配架构和 Python 版本的离线依赖 |
| `scripts/build-algorithm-packages.py` | 将算法源码打成可上传 ZIP |
| `scripts/sync-builtin-model-assets.py` | 同步内置模型资产 |
| `scripts/export-chinese-plate-models.py` | 导出指定预训练车牌模型 |
| `scripts/convert-rknn-model.py` | 转换 RKNN 模型 |
| `scripts/capture-runtime-observability.py` | 采集运行指标 |
| `scripts/algorithm-benchmark.py` / `edge-capacity-benchmark.py` | 算法与节点容量检查 |
| `scripts/offline-chaos-test.py` / `rollback-drill.py` | 断网与回滚验证 |

## 13. 哪些内容容易被误认为“已经用了”

| 容易混淆的内容 | 按当前代码理解 |
| --- | --- |
| 大语言模型、提示词、RAG、向量数据库 | 当前视频识别主链路围绕视觉模型与规则执行，未见这些作为核心 Runtime 依赖 |
| 在线训练平台 | 当前产品重心是模型接入、部署和推理；有导出/转换脚本及微调权重登记，不等于具备完整训练、标注平台 |
| gRPC | 架构模板提到过，当前 Runtime 服务和 Agent 客户端主实现是 HTTP/WebSocket，依赖未声明 gRPC |
| OpenCV | 部分模型来源带有 OpenCV 背景；当前核心 Runtime 主要直接使用 NumPy、Pillow、PyAV，没有把 `cv2` 作为核心直接调用依赖 |
| 所有框都靠深度学习跟踪 | 当前是项目的 IoUTracker；检测模型和跟踪算法是两个步骤 |
| 所有行为都靠视频时序神经网络 | 当前部分行为使用图像/裁剪分类，再由时序规则确认；具体模型输入要看 Manifest |
| 模型登记了就能现场使用 | 还需要真实文件、兼容的执行说明、设备环境和实际测试 |
| 单张图片测试成功就代表业务通过 | 只能证明本张图片的推理和展示；离岗、停留、多帧告警仍需视频验证 |
| 软件包支持 RKNN 就一定跑 NPU | 还需 RKNN 格式模型、匹配的设备/驱动/运行库和实际模型绑定 |
| 断网自治等于不需要本地持久数据 | 恢复依赖盒子上的模型、配置、数据库和加密密钥 |

本文按当前源码解释。旧 `runtime/README.md` 中仍有 HLS 主链路文字；实时预览应结合 V2 协议、WebRTC 代码和后续 ADR 阅读。原架构中“浏览器只访问 Java”的基线也已由网关双入口 ADR 修订。

## 14. 按什么顺序学，最容易看懂自己的项目

这是一条从现有代码入手的阅读路线，不需要先把所有框架学完。

| 顺序 | 先弄明白什么 | 看哪里 | 学完能回答什么 |
| --- | --- | --- | --- |
| 1 | 平台、Runtime、Agent 的分工 | 本文第 1–3 节 | 点击“启动”后由谁真正计算？ |
| 2 | 模型输入和标准输出 | `model/contracts.py`、`model/manifest.py` | 类别、框、置信度、预处理是什么？ |
| 3 | 单张图片推理 | `task/image_recognition.py`、`task/inference.py` | 图片如何交给模型并返回结果？ |
| 4 | 最简单的区域算法 | `algorithm_packages/region/processor.py` | 模型结果如何成为业务候选？ |
| 5 | 跟踪和规则 | `capability/tracker.py`、`rule/engine.py` | 为什么连续观察才能告警？ |
| 6 | 视频任务循环 | `task/manager.py`、`stream/shared.py` | 为什么多任务能共用一台摄像头？ |
| 7 | 命令从平台到盒子 | Java `service/task/`、Agent `command/executor.py` | 任务如何被下发和执行？ |
| 8 | 断网和重启 | `event/store.py`、`gateway/store.py` | 配置和事件为什么不会只留在内存？ |
| 9 | 专项能力 | `plate.py`、`face_pair.py`、`rknn.py` | 车牌、人脸、NPU 各增加了什么？ |

最适合的第一个练习是：在已有测试环境里，用已部署的任务做一次“图片识别”，找到返回的 `class`、`confidence`、`bbox`，再沿 `image_recognition.py → inference.py → pool.py → 模型 Adapter` 看一遍。之后再阅读实时视频和规则，理解负担会小很多。

## 15. 源码与文档索引

本文目录树均以仓库根目录为基准。下面是核对和进一步阅读的主要入口：

- [架构与分层规范](ARCHITECTURE_AND_CODING_GUIDELINES.md)
- [网关独立运行与平台双入口](GATEWAY_DUAL_ENTRY.md)
- [双入口架构决策](adr/ADR-20260908-dual-entry-gateway.md)
- [WebRTC 与 Overlay V2](PREVIEW_AND_OVERLAY_PROTOCOL_V2.md)
- [RKNN 加速与画面同步决策](ADR-0007_RKNN_ACCELERATION_AND_PREVIEW_ALIGNMENT.md)
- [模型执行契约](MODEL_EXECUTION_PROTOCOL_V1.md)
- [算法包说明](algorithm-packages/README.md)
- [盒子通用事件接口](GATEWAY_EVENT_DELIVERY.md)
- [边缘节点部署手册](EDGE_DEPLOYMENT_GUIDE.md)
- [Python 依赖声明](../runtime/pyproject.toml)
- [Runtime 入口](../runtime/ai_runtime/app/main.py)
- [模型池](../runtime/ai_runtime/app/model/pool.py)
- [任务执行](../runtime/ai_runtime/app/task/manager.py)
- [Agent 入口](../runtime/edge_agent/app/main.py)
- [前端工程依赖](../frontend/apps/web-antd/package.json)
- [Java 依赖版本](../backend/linsight-dependencies/pom.xml)
