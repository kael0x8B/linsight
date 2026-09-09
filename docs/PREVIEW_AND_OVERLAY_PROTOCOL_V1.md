# 单路预览与 Overlay 协议 V1

本文固化 Story 4/P06/P07 以及后续 Task/Inference 接入后的控制面、Runtime、Edge Agent 与浏览器契约。Java 负责鉴权、租户、节点路由和会话所有权；部署在边缘网关的 AI Runtime 负责唯一拉流、FFmpeg 转码、断流重连、HLS 文件与推理帧；Edge Agent 主动建立反向预览通道并转发最新推理帧；浏览器只访问 `/admin-api/**`，不接触 RTSP 地址、节点凭据或 Runtime 密钥。

摄像头的 `protocol=ONVIF|RTSP` 表示接入与能力类型，不改变预览数据面的输入协议：两类摄像头均使用已配置的主/子 RTSP 码流创建预览。ONVIF 可在未来提供 PTZ、预置点和对讲控制通道；标准 RTSP 只保证视频播放。控制服务未接入前，管理端必须明确显示不可用状态，不得把控制按钮伪装成已生效。

## 预览会话

管理端接口：

- `POST /admin-api/ai-video/camera/preview/create`：传入 `cameraId`、`nodeId` 和 `streamType=MAIN|SUB`。
- `GET /admin-api/ai-video/camera/preview/get?sessionId=...`：刷新会话和重连状态。
- `GET /admin-api/ai-video/camera/preview/media/{sessionId}/{fileName}`：代理 HLS 清单和分片。
- `DELETE /admin-api/ai-video/camera/preview/delete?sessionId=...`：幂等释放订阅。

所有接口要求 `ai-video:camera:preview` 权限，并将临时会话绑定到当前租户、用户、摄像头和执行节点。媒体文件只允许 `index.m3u8` 和 `segment-NNNNNN.ts`。控制面只在向已认证节点通道下发创建请求时解密和组装 RTSP URL，不写日志、不返回浏览器。

## Edge Agent 反向预览通道

Runtime 继续只监听网关回环地址。Edge Agent 使用 `tenant-id`、`X-Node-Id` 和 `X-Node-Credential` 主动连接 `/node-api/ai-video/preview/tunnel`；心跳在线与通道就绪是两个独立状态。控制面只向会话所绑定节点发送 `preview.create/get/media/release`，Agent 仅把白名单动作映射到本机 Runtime。

通道协议版本为 `1.0`。控制请求与普通响应使用 JSON 文本帧；HLS 媒体先返回 `media-meta` 文本帧，再发送“36 字节 requestId + 原始媒体”的二进制帧。单帧默认上限 8 MiB，请求默认 12 秒超时。Agent 断线后控制面注销连接并使待处理请求快速失败；Agent 指数退避重连。生产部署必须使用 HTTPS/WSS，HTTP/WS 仅允许受信私网兼容部署。完整架构决策见 `ADR-0003_EDGE_PREVIEW_REVERSE_CHANNEL.md`。

Runtime 以 `(cameraId, streamType)` 为键创建 FFmpeg Worker；同一摄像头的同一码流被多个浏览器会话共享，MAIN 与 SUB 可同时存在且互不覆盖。最后一个会话释放或空闲超时后停止对应码流进程并删除临时 HLS 文件。断流后 Worker 进入 `RECONNECTING` 并按有上限的退避策略重新拉流。

## Overlay envelope

WebSocket 外层消息类型为 `ai-video-preview-overlay`，其 `content` 是以下版本化 envelope：

```json
{
  "type": "preview.overlay.frame",
  "version": "1.0",
  "messageId": "message-uuid",
  "occurredAt": "2026-09-01T08:00:00Z",
  "traceId": "trace-id",
  "data": {
    "sessionId": "preview-session-id",
    "cameraId": 7,
    "frameId": "frame-42",
    "timestamp": "2026-09-01T08:00:00Z",
    "sourceWidth": 1920,
    "sourceHeight": 1080,
    "objects": [
      {
        "trackId": "track-9",
        "class": "person",
        "confidence": 0.93,
        "bbox": { "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4 },
        "attributes": { "helmet": "unknown" }
      }
    ]
  }
}
```

`bbox` 使用 `[0,1]` 归一化的 `x/y/width/height`，且边界不得超出原帧。前端按 `sourceWidth/sourceHeight`、容器尺寸和 letterbox 偏移在独立 Canvas 上绘制，不把框烧录进视频。未知字段应忽略；删除字段或改变语义必须升级 `version`。

## Runtime 与节点上报

- Runtime 在每次真实推理完成后生成 `taskId/runId/cameraId/frameId/timestamp/sourceWidth/sourceHeight/objects`。
- `GET /v1/overlays/pending` 仅允许带 Runtime Key 的本机 Edge Agent 调用。每个任务最多保留一个最新帧；新帧覆盖旧帧，读取后即移除，禁止弱网期间形成无界积压。
- Edge Agent 通过独立的短周期循环调用 `POST /node-api/ai-video/camera/overlay/report`。该接口使用节点凭据和租户上下文，不接受 Admin Token。
- 控制面只在目标摄像头存在活动预览会话时校验任务。`nodeId/taskId/runId/cameraId` 必须与当前 RUNNING 任务一致，否则拒绝过期或越权上报。
- 控制面将 envelope 逐会话绑定 `sessionId`，并且只发送给创建该会话的租户和管理员用户，不能全租户广播或跨用户泄漏。

Overlay 是允许丢帧的实时展示数据，不是事件证据。事件、截图和录像仍经持久化离线队列、幂等上报和对象存储链路交付，不能用 Overlay 代替验收证据。

## 视频墙与布局方案

P07 的每个已加载格子独立创建并释放上述预览 session；同一摄像头在 Runtime 侧仍共享唯一 Worker。某一格创建或播放失败只影响该格，页面离开、清空格子或切换布局时必须释放旧 session。16 分屏默认请求 `SUB`，其他分屏允许选择主/子码流。

布局方案按租户和登录用户隔离，最多提供 15 个固定保存位置。数据表保存 `schemaVersion=1.1`、`nodeId`、`splitCount=1|4|9|16` 以及按格子顺序排列且可含 `null` 的 `cameraIds`，不保存播放地址、凭据或 Runtime session。激活方案用于下次进入视频墙自动恢复；旧版 1.0 方案缺少 `nodeId` 时由前端选择当前可用节点。

管理端接口：

- `GET /admin-api/ai-video/camera/wall-layout/list`：列出当前用户方案。
- `POST /admin-api/ai-video/camera/wall-layout/create`：保存到空位置。
- `PUT /admin-api/ai-video/camera/wall-layout/update`：覆盖已有位置。
- `PUT /admin-api/ai-video/camera/wall-layout/activate?id=...`：设置唯一激活方案。
- `DELETE /admin-api/ai-video/camera/wall-layout/delete?id=...`：删除方案。

以上接口与播放接口共用 `ai-video:camera:preview` 权限；后端再次校验方案所属用户和租户。


## 2026-09-09 摄像头多算法图层扩展

- 平台按租户、摄像头和已授权预览会话转发各节点的结果；来源节点、任务、run 校验仍在转发前执行。Overlay 可附带 `nodeId`、`frameKey`。
- `frameKey` 是原始 H.264 VCL NAL（类型 1/5，逐个长度前缀）SHA256 的前 16 字节、32 位小写十六进制。排除 SPS/PPS/SEI 包装；只用于同一编码帧的跨节点关联，不能关联不同子码流或重新编码的视频。
- 现有私有 SEI payload 的 40 字节保持兼容；支持扩展为 56 字节，末尾 16 字节为 frameKey。旧数据仍在相同 streamId 内按 sourcePts 对齐。跨 streamId 必须在当前视频 SourceClock 中精确匹配 frameKey；重复且歧义的内容标识不参与跨流映射，不比较主机墙钟来猜测同帧。
- Runtime `preview.frames` 在既有预览会话中返回该摄像头本盒子全部启用任务的最新元数据；不为每个算法创建视频/解码器，不返回 JPEG。旧节点不支持时界面提示升级，视频仍播放。
- 各图层独立历史、run 失效和显隐；任务原始 ROI/告警规则不被显示设置修改。识别框带算法名称及图层色，入口刷脸区域可随入口图层隐藏。
- 平台 `camera/display-preference/get`、`camera/display-preference/update` 使用 `ai-video:camera:preview` 权限，按当前租户/用户/cameraId 隔离。hiddenLayers 仅接受 task-{id}/entry-{id}，最多 128 项。迁移：`V202609091500__camera_display_preferences.sql`。Edge 本地浏览器独立保存，不写平台偏好。
