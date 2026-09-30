# 识别同源 WebRTC 预览与 Overlay 协议 V2

本文在 `PREVIEW_AND_OVERLAY_PROTOCOL_V1.md` 基础上把浏览器视频数据面升级为 WebRTC；Overlay envelope 继续使用 V1 的 `preview.overlay.frame/1.0`。

## 主／子码流选择

识别任务参数 `streamType=SUB|MAIN` 选择已保存的摄像头子／主 RTSP 地址；未设置的历史任务继续使用 `SUB`。启动前检查所选地址，同一网关与摄像头的并行任务必须使用同一类型。平台网关编辑页切换码流时，由服务端解析带凭据的地址并下发，浏览器不接收 RTSP 密码。切换已启用任务会短暂重启识别。

实时预览、视频墙与 HLS 兼容入口在存在运行任务时跟随该任务的码流，以保持视频和 Overlay 的同一帧时间线；没有运行任务时，WebRTC 默认 `SUB`，HLS 使用请求的 `streamType`。摄像头主、子码流均须配置为 H.264。Runtime 对 H.264 编码包直传预览，识别复用同一源流按需解码；非 H.264 码流明确报错，不进行软件转码。

## WebRTC 会话

- `POST /admin-api/ai-video/camera/preview/webrtc/offer`
  - 请求：`cameraId`、`nodeId`、`offerSdp`、`offerType=offer`
  - 响应：`sessionId`、`cameraId`、`nodeId`、`protocol=WEBRTC`、`state`、`subscriberCount`、`diagnosticId`、`answerSdp`、`answerType=answer`、`overlayMessageType`
- `GET /admin-api/ai-video/camera/preview/get?sessionId=...`：查询 `CONNECTING|READY|FAILED|CLOSED`，不重复返回 SDP。
- `DELETE /admin-api/ai-video/camera/preview/delete?sessionId=...`：按当前租户、用户和节点幂等释放。

Runtime 本机接口对应 `/v1/webrtc/sessions/offer` 和 `/v1/webrtc/sessions/{sessionId}`。Edge Agent 只允许 `webrtc.offer/get/release` 三个动作。SDP 最大 1,000,000 字符；描述类型只允许 `offer`。浏览器只创建 `recvonly` video transceiver，Runtime Answer 只发送 H.264 视频，不提供音频或控制通道。

## 生命周期与共享

Runtime 以 `cameraId` 为键共享所选码流的 CameraMediaHub：H.264 编码包供预览订阅，有分析任务时只增加一个共享解码器。每个浏览器拥有独立 PeerConnection 和 session；查询会刷新空闲时间，但已连接的 PeerConnection 以 ICE/DTLS 状态作为权威存活信号，不因浏览器后台节流导致查询延迟而被回收。非连接会话空闲超时会被回收；最后一个预览与分析订阅都释放后停止 RTSP 源。连接建立前状态为 `CONNECTING`，DTLS/ICE 成功后为 `READY`，失败为 `FAILED`。

视频墙中某格失败只重建该格；切换布局、清空格子和离开页面必须释放旧 session。Overlay 仍按 sessionId 路由并在独立 Canvas 绘制。

控制面返回 `1020000123`（会话不存在或已过期）或明确的 `FAILED/CLOSED` 时，播放器重建会话，即使旧 PeerConnection 仍在收到 RTP；正常媒体帧不能取消这种重建，否则会失去 Overlay 路由。普通查询超时且媒体正常时保留当前播放。后台轮询与幂等释放由播放器处理错误，不重复弹出全局错误提示。

## 网络边界

控制面信令必须经过鉴权的 HTTPS/WSS（受信私网兼容部署可显式使用 HTTP/WS）。媒体为浏览器到边缘 Runtime 的 DTLS-SRTP。当前 host ICE 仅保证双方网络可达时工作；跨 NAT/公网需要后续配置 TURN，不得通过开放 Runtime HTTP 端口替代。

## 识别画面与摄像头能力（2026-09-06）

保持 WebRTC 和 `preview.overlay.frame/1.0` 主协议。Overlay `data` 增加向后兼容字段：

| 字段 | 语义 |
| --- | --- |
| `taskId` / `runId` | 已通过节点、租户、摄像头与当前运行校验的任务标识；浏览器只接收所选任务当前 run 的递增时间戳 |
| `imageBase64` | 可选 JPEG Base64，和本条对象列表来自同一个推理输入；原 JPEG 最大 256 KiB，编码最大 349528 字符，超限不发送图片 |
| `timestamp` | 共享解码器收到该 JPEG 的时间，随有界队列一起传递；不是推理完成或消息到达时间，也不声称等于摄像机曝光时间；Runtime 上报为 ISO-8601，现有控制面 WebSocket JSON 序列化为 epoch 毫秒，前端兼容两种入口 |

低帧率 CPU 分析无法给每一帧低延迟视频提供同时刻的识别结果。P06 主区域保留实时 WebRTC 视频，侧边“识别画面”显示本次采样 JPEG 与对应 Canvas 框；图片加载完成才绘制对应 frameId 的框。显示采样年龄，超出 `max(15s, 3 / sampleFps)` 后清空结果；任务切换、run 切换、停止、离线时不再接受旧结果。缺少图片、加载失败、无运行任务和等待结果均有明确状态。JPEG 只用于当前预览，不写业务事件或持久证据，也不记录进请求日志。通用 WebSocket 发送器仅记录消息类型与长度，不在成功、失败或无接收者日志中记录消息正文；逐消息成功日志使用 DEBUG，避免高频图片写入日志。

安全帽场景继续保留内部 Person 检测和 PPE 关联契约。展示根据 `ppeConfirmedPerson` / `helmet` / `ppeConfidence` 输出“未戴安全帽”“已戴安全帽”“安全帽待确认”；默认只画明确未戴帽目标，可开启正常与待确认目标。unknown 不产生违规告警，也不以人员置信度冒充安全帽置信度。其他实时叠加调用方最多保留 750ms 的检测框，避免无限保留旧框。

安全帽关联保留模型实际输出的头部区域：`attributes.ppeBoxX / ppeBoxY / ppeBoxWidth / ppeBoxHeight` 是相对原始分析帧的归一化坐标，和 `ppeSourceClass / ppeConfidence` 来自同一被匹配 PPE 检测。对象原有 `bbox` 继续表示人员区域，用于跟踪、ROI 和事件规则，语义不变。P06 对明确已戴/未戴帽结论优先绘制该 PPE 区域；未知目标、旧节点缺失字段或坐标不合法时保留人员框。不会按人体框固定比例猜出头部位置。四个新增 attributes 标量向后兼容，控制面沿用既有透传；事件对象快照也保留这些字段。

`GET /admin-api/ai-video/camera/page` 和 `/get` 新增 `recognitionCapabilities[]`。由 Camera 查询服务批量组合 Task、Algorithm、Node 的安全投影，沿用摄像头查询权限和租户隔离，不做前端逐行请求。内容包括算法名称、任务、节点、验证模式、期望/实际状态、有效状态、任务心跳、分析 FPS 和处理耗时。运行态任务超过 60 秒无心跳显示 `STALE`，节点停用/离线/心跳过期显示 `OFFLINE`；已停止任务保持停止。能力来自实际任务绑定，不将模型类别或完整算法目录当作摄像头已部署能力。

实时页每 10 秒刷新所选摄像头能力。播放器按 cameraId/nodeId 的原始值监听，能力元数据刷新不重建 WebRTC 会话；Overlay 通道断开后每 3 秒重试，页面卸载释放连接与定时器。视频 FPS 来自浏览器实际解码帧计数增量，和任务分析 FPS 分开展示。


## 2026-09-07 客户识别展示与证据一致性

- 实时页和视频墙通过 WebSocket `onMessage` 逐条路由结果，避免只观察最后一条消息值时，多会话连续推送丢掉当前会话的结果。
- 实时页和视频墙默认以配套 JPEG + Overlay 作为主识别画面，可切换 WebRTC 实时视频。能力选择限制 nodeId/taskId/runId，并拒绝时间倒退的结果。
- `RecognitionFrame` 只在当前图像完成加载后绘制它对应的坐标；结果过期、缺图、能力停止有独立提示。帧时间表示 Runtime 收到解码帧的时间，不等同摄像机 OSD 时间或完整端到端延时。
- 历史事件截图使用原始归一化目标坐标；安全帽采用实际 PPE 头部坐标及 PPE 置信度。历史模式不适用实时帧过期逻辑。录像无逐帧目标轨迹时只提供原始过程画面，不伪造静态框。
- EventMedia 查询新增 `originalContentAvailable`。旧文件同一路径对应不同 SHA256 时不能作为原告警截图标框；比较对象路径时排除签名查询参数。新媒体以 SHA256 前缀命名，防止相同事件文件名覆盖。
- 录像打包改为有界后台队列、单编码进程，TaskRunner 不等待编码完成才继续分析；退出时先排空证据队列再关闭本地持久化存储。同一活动已告警的目标在短暂漏检后不能重复触发相同 sourceEventId。

## 2026-09-07 连续视频同步（ADR-0007）

本节取代上文实时页/视频墙以 JPEG 作为主识别画面的临时方式。历史事件继续使用同帧 JPEG 证据。

- Overlay 新增可选 `streamId`（UUID）与 `sourcePts`（90 kHz、0 至 2^53−1）。它们来自共享 H.264 解码源，
  不是模型完成时间。源重新连接生成新 UUID；Task Run 另行校验，两个隔离条件都必须满足。
- 原 `timestamp` 是 Runtime 收到输入包/解码 JPEG 的墙钟时间，供事件和兼容显示使用；同步不依赖摄像机、
  节点和浏览器时钟相等。
- Runtime 在转发 H.264 中附加 user_data_unregistered SEI，UUID 为
  `b60519ab-079c-4e19-9428-f40aef3c91ec`，载荷为该 UUID 的 16 字节、stream UUID 的 16 字节和大端 uint64 PTS。
  使用标准 emulation prevention；每个编码帧保留原图像内容，不烧录检测框。
- 浏览器 encoded transform 读取 SEI 与真实 RTP timestamp 的对应关系并原样转发；
  requestVideoFrameCallback 的 RTP timestamp 选取同源 PTS。两条时间轴不通过到达时间或随机 RTP 偏移猜测关联。
- AI 模式使用浏览器原生 video 连续播放，Canvas 只绘制目标框。接收端 encoded transform 使用有界
  默认 500 ms 编码帧缓冲，最多 128 帧，保持帧顺序；过载或重连丢弃旧预测链并从关键帧恢复，卸载关闭缓冲。
  2026-09-22 起，视频底部“同步缓冲”可手动设置 0–1800 ms，立即作用于当前接收流，不重建播放会话。
  数值在当前浏览器按租户/账号保存，实时预览、视频墙及平台网关预览共享；网关本地入口独立保存。
  新预览和重连均恢复用户值，没有保存值时使用 500 ms；同源结果到达延迟和识别间隔仅用于诊断，
  不再自动增大用户设定的缓冲。降低缓冲可能减少可匹配的识别框，未匹配帧继续播放且不叠加过期结果。
  不把重复消息作为新采样，也不把新增加的缓冲重复计入识别耗时。
  正常缓冲按源 PTS 的间隔安排释放；启动首帧迟到后按后续包的到达情况前移整条排队时间轴，
  按原顺序释放已过期帧，避免启动偏移使实际等待永久超过用户设置。帧的实际排队时长可能随网络抖动或解码背压变化。
  源时钟缓存最多 300 条，结果最多 40 条。底部 FPS 来自 rVFC `presentedFrames` 的增量，区别于接收/解码 FPS；
  缓冲耗时是该帧在接收变换中实际等待的时间。正常播放不逐帧复制 VideoFrame 或重绘视频像素。
  截图时才复制本次 rVFC 的视频帧，等待对应 Canvas 图层更新后合成；设置 0 ms 可释放同步等待。
- 按视频 PTS 选择结果。孤立观察仅允许在相距 100 ms 内展示，不向未来外推。
  间隔最多 1000 ms、相同 Camera/Run/Track/类别和显示状态的两次真实观察之间，允许按当前视频 PTS 线性估算位置；
  部位框必须两端都有真实坐标，不能从人员身体推造头部框。部位相对身体发生跳变、两端缺失、身份/状态变化或超过跨度时不插值。
  跟踪估算的展示时间等于视频 PTS，最近真实锚点距离可达 500 ms；它不等于一次新的模型识别，也不能把这个
  距离伪报成 0 ms 的模型精度。实测分别报告单锚点距离、跟踪跨度与有效结果覆盖率。
  连续观察证明目标静止时，可短时保留原位置以覆盖漏检/待确认，最长 600 ms，始终从原始观察计时；
  运动目标按预计位移误差收紧保留时间，快速移动只允许 100 ms，不能冻结旧头框造成拖尾。
  新的身体位置明显移动、新确认状态、新身份、停止或重连会终止相应保留。保留结果带 `overlayHeld/overlayAgeMs`，界面显示“识别框短时保持”。
  插值只改变预览位置，不改变事件、告警确认计数、模型置信度或不可变证据。
- 无对应结果时继续播放视频并提示状态。旧节点缺同步字段或浏览器缺 encoded transform/rVFC
  时不声称识别已同步；原视频模式仍可观看。
- 能力卡增加来自当前任务指标的 `executionBackend`，分别显示 NPU 加速、CPU 分析或混合执行；
  硬件探测和模型加载状态不能替代实际运行后端。
- 同一个 H.264 解码帧产生共享 RGB 图像供多个 Manifest 模型复用，避免重复解码 JPEG；证据 JPEG
  由该 RGB 图像编码，因此同帧同坐标，但 JPEG 压缩像素不与原 RGB 逐字节相等。确定性 H.264 回放测试
  检查 RGB 模型输入与对应视频帧逐像素一致，并单独检查 JPEG 压缩误差。
- WebSocket 心跳回复与识别推送共用 `ConcurrentWebSocketSessionDecorator` 的发送锁；缓冲上限为
  1 MiB，发送超时仍为 5 秒。并发测试覆盖 150 KiB 识别消息与心跳交错、关闭后迟到的心跳，避免
  `TEXT_PARTIAL_WRITING` 造成识别连接反复断开；错误日志只记录会话编号、长度和异常类型。

- Agent 的 Overlay 轮询周期扣除本次上传耗时，避免每次 HTTP 完成后再固定等待；仅保留各任务最新结果，
  不积累旧帧。预览拥有者按状态轮询续租，90 秒未访问的旧会话停止投递，避免浏览器刷新后重复推送不断增加。

- 已有 `streamId/sourcePts` 的连续视频链路，每次分析均发送目标元数据，同帧诊断 JPEG 最多每 2 秒一张；
  未附图的消息不得配上一条旧 JPEG 冒充本帧。没有视频时间轴的旧采样链路继续逐次携带同帧图。
  历史事件与视频证据采集不受这项预览传输节流影响。

- 编码视频转发不等待分析解码。唯一分析解码器使用最多 30 包的队列，过载后丢弃旧预测链并从关键帧恢复；
  追赶队列时仍解码中间参考帧，但只对最新可用帧转换 RGB/JPEG，避免为旧画面反复消耗处理时间。
  任务/源代际在解码前后校验，旧异步结果不能贴上重连后的时间轴。释放时等待正在使用原生解码器的线程完成。
  慢解码的确定性测试覆盖连续视频仍按原帧率到达，不以增加无界缓存掩盖滞后。
- 停止任务时同步释放分析订阅并保存剩余事件证据，其他预览拥有者继续保有视频源；Agent 的该请求预算
  为 150 秒。控制面失败重试创建可投递的新命令，正在执行的停止命令复用其真实编号；可修复旧版本
  将未持久化编号写入任务导致的“停止中”状态，不能通过直接改数据库把任务伪装为停止。

待实机复测的采样修正：解码仍保留完整参考链，额外允许队列尾部最多 3 包、等待不超过 80 ms 的画面参与
既定采样，避免只有队列完全清空才转换图片导致成批输入时分析间隔过大。部署 34 尚未包含此修正；
节点离线期间仅完成了真实 H.264 突发输入与旧帧舍弃测试，不能把本地测试作为实机性能结果。

客户画面标签只显示识别结论与置信度，内部 Track 编号保留在原始结果与诊断记录中。

编码帧保持原身份和顺序、允许延迟或丢弃的约束见
[W3C WebRTC Encoded Transform](https://www.w3.org/TR/webrtc-encoded-transform/#stream-processing)。
接收流关闭反映为预览重连状态，浏览器不支持变换时不得宣称图框同步。
