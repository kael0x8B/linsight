# ADR-0004：固定子码流的 WebRTC 实时预览

- 状态：Accepted
- 日期：2026-09-04
- 范围：Camera、Node、Edge Agent、AI Runtime、实时预览与分屏监控
- 替代：ADR-0003 中 HLS 作为浏览器主预览数据面的部分；反向信令通道决策保持有效

## 背景

现场主码流为 3840×2160、25 fps。边缘网关对其做 HLS 转码时单路 FFmpeg 长期占用约 232% CPU，1 秒分片为 1.7–2.8 MB，而经反向通道下载一个分片需要 1.4–1.8 秒，播放窗口持续被追赶并触发重连。子码流约 640×480/853×480、25 fps，带宽和处理开销显著更低，适合作为浏览器实时监控输入。

浏览器不能直接播放 RTSP。实时预览还要求低延迟，继续以 Java 控制面代理 HLS 分片会让持续媒体流穿过控制面，无法满足目标。

## 决策

1. 实时预览和视频墙只使用摄像机 `SUB` RTSP 地址，管理端不再提供主/子码流切换。即使调用旧 HLS 创建接口并传入 `MAIN`，服务端也固定解析 `SUB`。
2. 浏览器创建仅接收视频的 WebRTC Offer，经已认证的 Java 管理 API 和 Edge Agent 反向通道送到网关本机 Runtime。RTSP URL 和摄像机凭据仍只存在于控制面到受信节点的请求中，不返回浏览器。
3. Runtime 使用 aiortc 建立 PeerConnection，优先以 `decode=false` 转发摄像机 H.264 子码流包，不做 4K 软件转码。同一摄像机的多个预览会话通过 MediaRelay 共享一条 RTSP 拉流；最后一个订阅释放时关闭源。
4. 信令使用现有 WSS/WS 反向通道；媒体使用浏览器与边缘 Runtime 之间的 ICE、DTLS-SRTP。V1.1 交付面向受信同一局域网，使用 host candidate。跨网段、NAT 或公网部署必须增加 STUN/TURN 与相应端口、证书和访问控制后方可启用。
5. Offer 与 Answer 均采用 non-trickle ICE：双方收集完成后一次性通过控制面交换 SDP。响应可包含 ICE 地址，但不得包含 RTSP URL、摄像机用户名密码、节点凭据或 Runtime Key。
6. 旧 HLS Runtime/API 实现暂时保留为代码级回滚路径，前端不再请求 HLS manifest 或分片。不得在 WebRTC 失败时无提示自动降级 HLS。

## 安全边界变化

ADR-0003 否决了“浏览器直连网关”的泛化方案。本决策只允许浏览器直连 Runtime 为 WebRTC 会话动态创建的加密 UDP 媒体端点，不开放 Runtime HTTP、RTSP、节点凭据或摄像机凭据。生产环境必须使用 HTTPS/WSS，并通过防火墙限制 ICE/TURN 媒体端口和来源。浏览器与边缘节点不可直达时，会话应明确失败，不能放宽 Runtime 的 `127.0.0.1:48900` HTTP 监听。

## 协议

反向通道新增白名单动作：

- `webrtc.offer`：`cameraId`、`sourceUrl`、`offerSdp`、`offerType=offer`
- `webrtc.get`：`sessionId`
- `webrtc.release`：`sessionId`

管理端新增 `POST /admin-api/ai-video/camera/preview/webrtc/offer`。会话响应的 `protocol=WEBRTC`，创建响应含 `answerSdp` 与 `answerType=answer`；后续状态查询不重复返回 SDP。原查询和释放接口继续按服务端记录的会话协议路由。

## 被否决方案

- 继续优化主码流 HLS：无法消除 4K 转码和分片代理瓶颈，延迟仍以秒计。
- 浏览器直接获得 RTSP URL：浏览器不原生支持且会泄漏摄像机凭据。
- Java 控制面终止 WebRTC 媒体：增加中心带宽与解码/转发负载，破坏边缘媒体处理边界。
- 本阶段强制 TURN：能覆盖 NAT，但需要独立容量、证书、端口和运维设计，不应伪装为已交付能力。

## 回滚

前端可回滚到旧 HLS player 和 `/preview/create`、`/preview/media`；Runtime 与反向通道保留旧 HLS 动作。回滚不恢复主码流选择，旧创建接口仍固定使用子码流。

## 验收标准

1. 单路实时预览和 1/4/9/16 分屏只创建 `SUB` 会话，页面无主码流入口。
2. 浏览器 PeerConnection 达到 `connected`，视频持续前进，Network 中无 m3u8/ts 请求。
3. ONVIF 与 RTSP 摄像机走同一 WebRTC 数据面，API 和日志中不出现摄像机凭据。
4. 同一摄像机多格预览只保留一条 RTSP 源；格子清空、布局切换和页面离开会释放 PeerConnection。
5. ICE 不可达、源非 H.264、Runtime 不可达和会话超时均返回诊断编号，不静默降级。
