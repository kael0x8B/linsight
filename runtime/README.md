# LInsight Runtime / Edge Agent

本目录承载独立计算面，不连接控制面 MySQL。当前纵向基线提供：

- Edge Agent 使用一次性 bootstrap token 注册，长期凭据仅保存在权限为 `0600` 的本地文件。
- 心跳携带单调递增 sequence、Agent 时间、CPU/内存/磁盘资源快照与 Runtime 健康状态。
- AI Runtime 通过 FFprobe 完成 DNS、TCP、鉴权/取流、视频流与关键帧分阶段检测。
- AI Runtime 为单路浏览器预览创建 HLS 会话；同一 `cameraId` 的多个会话共享一个 FFmpeg Worker，最后一个会话释放后停止拉流。
- 预览 Worker 在断流后进入 `RECONNECTING` 并退避重试，临时清单和分片在空闲回收或进程退出时清理。
- Edge Agent 拉取耐久模型命令，使用短时签名 URL 下载并校验 SHA256，再调用本机 Runtime。
- Runtime 提供按 `(modelVersionId, device)` 复用的 `ModelPool` 和受控适配器注册表，按制品
  格式路由 ONNX、TorchScript、可信预置 PyTorch checkpoint 和 ZIP 模型包；多模型 ZIP 必须
  配置明确流水线，不按文件顺序猜测主模型。
- Edge Agent 执行 `START_TASK` / `STOP_TASK` 耐久命令，并周期上报任务运行状态与短周期指标。
- 同一摄像头的并行任务共享一个 FFmpeg 拉流/解码拥有者；每个任务使用容量为 1 的有界队列，最后一个任务停止后释放流。
- 事件补传使用 SQLite WAL、逐条失败隔离和持久化指数退避；Edge 升级使用签名包、原子
  `current/previous` 指针与可验证回滚。
- Runtime 提供受 `X-Runtime-Key` 保护的 `/v1/observability/snapshot`，统一导出进程、任务、
  共享流、模型池和离线投递指标；离线队列统计覆盖退避中的全部记录，而不是仅统计当前到期批次。
- API 和日志响应不返回 RTSP 凭据、完整码流路径或 FFprobe 原始错误。
- Edge Agent 使用节点凭据主动建立反向预览 WebSocket；控制面按节点发送预览 RPC，Agent 只允许映射到本机 Runtime 的白名单动作。媒体使用二进制帧，Runtime 无需开放局域网监听端口。

运行前必须显式提供环境变量，仓库不内置真实节点令牌、摄像头或生产参数：

```bash
export LINSIGHT_RUNTIME_API_KEY='replace-with-local-secret'
python -m uvicorn ai_runtime.app.main:create_app --factory --app-dir runtime --host 127.0.0.1 --port 48900
```

可选预览参数使用 `LINSIGHT_RUNTIME_` 前缀，包括 `FFMPEG_BINARY`、`PREVIEW_ROOT`、`PREVIEW_STARTUP_SECONDS`、`PREVIEW_IDLE_SECONDS`、`PREVIEW_HLS_SEGMENT_SECONDS` 和 `PREVIEW_HLS_LIST_SIZE`。Java 本地配置需将 `LINSIGHT_RUNTIME_ENABLED=true`。Edge Agent 使用 `LINSIGHT_AGENT_RUNTIME_URL` 与 `LINSIGHT_AGENT_RUNTIME_API_KEY` 访问本机 Runtime，并从 `LINSIGHT_AGENT_CONTROL_PLANE_URL` 推导 `ws://`/`wss://` 反向通道。正式环境必须使用 HTTPS/WSS；明文 WS 默认仅允许回环或私网地址，也可用 `LINSIGHT_AGENT_PREVIEW_TUNNEL_ALLOW_INSECURE` 显式控制。管理端始终通过 Java 代理获取 HLS，不直接访问 Runtime。

模型执行还可配置 `LINSIGHT_RUNTIME_DATA_ROOT` 和 `LINSIGHT_RUNTIME_MODEL_POOL_SIZE`（生产默认 4 槽位）。任务配置与启动会按本节点运行中任务及共享模型去重预检槽位，并以已校验模型制品的 2 倍、最低 64 MiB 估算每个唯一模型的内存预算。默认至少保留系统内存的 5% 或 512 MiB，可用 `LINSIGHT_RUNTIME_MODEL_MEMORY_SAFETY_RATIO`、`LINSIGHT_RUNTIME_MODEL_MEMORY_MIN_RESERVE_MIB` 调整。预检只读，不加载/淘汰模型或改变任务状态；不通过时返回冲突任务和模型。任务抽帧可配置 `LINSIGHT_RUNTIME_TASK_CAPTURE_FPS` 和 `LINSIGHT_RUNTIME_TASK_STARTUP_SECONDS`。Runtime 只接受数据根目录内的模型/图片绝对路径。旧部署使用的 `LINSIGHT_RUNTIME_RUNTIME_DATA_ROOT` 仍兼容，但新部署必须使用文档化名称。Agent 必须配置相同挂载目录 `LINSIGHT_AGENT_RUNTIME_DATA_ROOT`、Runtime 地址 `LINSIGHT_AGENT_RUNTIME_URL` 和 `LINSIGHT_AGENT_RUNTIME_API_KEY`；任务状态上报间隔可用 `LINSIGHT_AGENT_TASK_REPORT_INTERVAL_SECONDS` 调整。部署器通过 `LINSIGHT_RUNTIME_PLATFORM_URL` 把初始平台地址交给本地管理页；登录 `48901` 后可在“平台连接设置”保存设备侧覆盖值，Agent 自动重建中心连接而不停止 Runtime 任务。

ONNX CPU 使用 `LINSIGHT_RUNTIME_ONNX_INTRA_OP_THREADS` 控制每个会话的计算线程数（默认 2，范围 1–32），会话 inter-op 为 1，关闭 intra/inter-op worker spinning，给视频解码、WebRTC 和 Agent 留出 CPU。RK3566 双模型 PPE 场景已实测；其他硬件应基于实际路数与模型测量后调整，不能仅提高任务 sampleFps 就假定分析帧率提高。模型输入尺寸、权重、阈值和规则不随线程配置变化。

任务 JPEG 抽帧使用固定量化质量，`LINSIGHT_RUNTIME_TASK_CAPTURE_JPEG_QUALITY` 默认 2（范围 2–31，值越小保留细节越多）。必须避免连续 MJPEG 输出的默认码率控制逐渐压低分析画质；摄像头预览清晰不代表模型输入清晰。调整后应检查实际分析 JPEG 和识别结果，同时关注节点 CPU、媒体大小和传输开销。

CPU 节点只运行 ONNX 时安装基础包即可；需要 TorchScript 或 Ultralytics PT 时安装
`linsight-runtime[pytorch]`。普通 `.pt` 不等于 TorchScript，仅包含 `state_dict` 的权重还必须
提供模型族网络定义或先离线转换。

现场采集使用仓库根目录的 `scripts/capture-runtime-observability.py`。密钥只从环境变量读取，
不会进入命令参数或结果文件；采集结果包含逐次快照及汇总的运行任务数、输入/分析 FPS、共享流数、
丢帧、重连、推理 P95、补传队列、证据积压、媒体完整性、CPU 与内存。示例：

```bash
export LINSIGHT_RUNTIME_API_KEY='由密钥系统注入的节点 Runtime 密钥'
python3 scripts/capture-runtime-observability.py \
  --runtime-url http://127.0.0.1:48900 \
  --control-plane-health-url https://control.example.com/actuator/health \
  --duration-seconds 60 --interval-seconds 10 \
  --environment-name '生产验收环境名称' \
  --hardware '目标边缘节点完整规格' \
  --software-version '不可变发布 tag 或 commit SHA' \
  --run-id 'field-run-001' \
  --output evidence/raw/observability-runtime-series.json
```

Edge Agent 首次注册还需提供 `LINSIGHT_AGENT_BOOTSTRAP_TOKEN`。成功注册后应立即从环境中移除该一次性令牌；长期凭据写入 `LINSIGHT_AGENT_CREDENTIAL_FILE` 指定的位置。

Edge Agent 在线升级必须配置 `LINSIGHT_AGENT_UPGRADE_ROOT` 和由密钥系统注入的
`LINSIGHT_AGENT_UPGRADE_SIGNING_KEY`（至少 32 字节）。控制面“边缘节点”页面上传的
`.tar.gz`/`.tgz` 包会在节点侧再次校验 SHA256 与 HMAC-SHA256 签名，然后原子切换
`current`/`previous`；未配置签名密钥的 Agent 会明确拒绝升级和回滚命令。

当前 FFprobe/FFmpeg 子进程不会记录命令行，但带认证的 RTSP URL 在进程存活期间可能被同机高权限用户观察。生产节点应限制本机进程可见性；后续 StreamHub 长连接可使用进程内 LibAV/PyAV 适配器进一步缩小暴露面。Overlay 契约见 `docs/PREVIEW_AND_OVERLAY_PROTOCOL_V1.md`，模型执行契约见 `docs/MODEL_EXECUTION_PROTOCOL_V1.md`，算法 Pipeline 与任务生命周期契约见 `docs/ALGORITHM_PIPELINE_TASK_PROTOCOL_V1.md`。

## 自治与本地管理

Runtime 持久化加密的执行配置并自行恢复模型和任务；Edge Agent 不再是重启恢复的前置依赖。原有 `ai_runtime.app.main:create_app` 启动时自动在同一 Python 进程内提供 48901 本地管理入口，通过进程内 ASGI 调用共享 Runtime 配置。无需单独启动网页进程或安装 systemd 服务。平台通过反向通道 `gateway.rpc` 使用同一管理接口。详细步骤和兼容性见 [双入口说明](../docs/GATEWAY_DUAL_ENTRY.md)。

盒子事件接口采用 TCP 服务端订阅，默认监听 `0.0.0.0:48902`、订阅开关默认关闭。可通过 `LINSIGHT_RUNTIME_GATEWAY_EVENT_TCP_HOST` / `LINSIGHT_RUNTIME_GATEWAY_EVENT_TCP_PORT` 修改监听；鉴权、实时订阅、30 秒心跳和事件字段见 [盒子 TCP 事件订阅协议](../docs/GATEWAY_EVENT_DELIVERY.md)。
