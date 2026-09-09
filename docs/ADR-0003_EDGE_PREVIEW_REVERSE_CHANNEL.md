# ADR-0003：Edge Agent 反向预览通道

- 状态：Accepted
- 日期：2026-09-03
- 范围：Camera 领域、Node 领域、Edge Agent、AI Runtime、实时预览与分屏监控

## 背景

AI Runtime 按最小暴露面原则仅监听边缘网关回环地址 `127.0.0.1:48900`。Edge Agent 通过出站心跳保持节点在线，但旧预览链路由 Java 控制面按全局 `runtime.base-url` 主动访问 Runtime；因此“节点在线”并不代表控制面能够访问该节点的 Runtime，部署在另一台主机上的控制面会错误访问自身的 `127.0.0.1:48900`。

浏览器不能直接播放 RTSP，仍需要由边缘 Runtime 将 ONVIF 所发现或用户显式配置的 RTSP 源转换为 HLS，再由控制面鉴权代理给浏览器。控制面不得解码视频，也不得将摄像机凭据返回浏览器。

## 决策

采用 Edge Agent 主动建立的长连接反向预览通道：

1. Edge Agent 使用既有节点 ID、租户 ID 与节点凭据，向控制面的 `/node-api/ai-video/preview/tunnel` 建立 WebSocket 长连接。
2. 管理员创建预览时必须指定执行节点。Camera 服务校验摄像机与节点后，只在通道内下发包含 RTSP 源的 `preview.create` 请求。
3. Edge Agent 在网关本机调用 `127.0.0.1:48900`；Runtime 继续负责 RTSP 拉流、转码和 HLS 生命周期。
4. 创建成功后，控制面把 `sessionId` 与 `tenantId/userId/cameraId/nodeId` 绑定。查询、媒体读取和释放请求始终路由到原节点，禁止跨租户、跨用户和跨节点复用。
5. 控制请求和普通响应使用版本化 JSON 文本帧；媒体响应使用“36 字节 requestId + 原始媒体字节”的二进制帧，避免 Base64 放大。每个请求都有超时、诊断编号和最大消息限制。
6. Agent 断线时控制面立即注销节点通道并终止该节点的待处理请求；Agent 采用指数退避自动重连。节点在线状态与预览通道就绪状态分别表达。
7. `https://` 控制面对应 `wss://`，正式环境必须启用 TLS。为兼容现有受信局域网的 HTTP 部署，V1 允许通过 Agent 配置显式启用 `ws://`；该模式不得用于跨公网或不可信网络。

## 协议

协议版本为 `1.0`。控制面请求文本帧字段为 `version`、`requestId`、`action`、`payload`。V1 动作为：

- `preview.create`：`cameraId`、`sourceUrl`、`streamType`
- `preview.get`：`sessionId`
- `preview.media`：`sessionId`、`fileName`
- `preview.release`：`sessionId`
- `runtime.health`：无业务参数

普通响应文本帧字段为 `version`、`requestId`、`ok`、`payload`；失败响应另含 `errorCode`、`errorMessage`、`diagnosticId`。媒体成功响应先发送带 `contentType`、`contentLength` 的文本元数据帧，再发送同一 requestId 的二进制帧。

## 被否决方案

- Runtime 监听 `0.0.0.0`：实现简单，但扩大攻击面，需要独立端口、证书和防火墙治理，且摄像机源凭据会经过新的入站接口。
- Java 为每个节点直接维护 Runtime 地址：仍要求控制面能够路由到边缘网关，无法穿越 NAT，并把节点网络拓扑耦合到 Camera 服务。
- 浏览器直连网关：暴露节点地址和鉴权材料，绕过控制面权限与审计，也无法可靠兼容 RTSP。
- Base64 承载媒体：实现简单，但持续增加带宽、内存复制与 GC 压力。

## 影响、迁移与兼容

- `POST /admin-api/ai-video/camera/preview/create` 增加必填 `nodeId`；响应增加 `nodeId`。查询、媒体和释放 URL 保持不变。
- 实时预览与分屏监控增加全局执行节点选择；布局方案同时保存 `nodeId`，旧布局缺少该字段时自动选择首个“在线且通道就绪”的节点，无法选择时提示用户。
- 旧的 Java 直连 Runtime 客户端不再用于业务预览；Runtime HTTP API 保留，供同机 Edge Agent 调用和本地诊断。
- Edge Agent 与控制面允许滚动升级：旧 Agent 不建立通道时仍可心跳和执行既有任务，但预览创建明确返回“节点预览通道未连接”。

## 回滚

回滚前端与控制面即可停止使用反向通道；Edge Agent 的通道协程可通过配置关闭，不影响心跳、任务、事件和日志链路。Runtime 的回环监听及 HTTP API 未改变，无需迁移媒体数据。

## 验收标准

1. Runtime 仅监听 `127.0.0.1:48900` 时，异机控制面可经在线节点创建、查询、读取媒体并释放预览。
2. ONVIF 与显式 RTSP 摄像机使用相同通道；摄像机凭据不出现在管理 API 响应、浏览器 URL或日志中。
3. 节点心跳在线但通道未连接时返回可定位的诊断错误，不再误访问控制面本机回环地址。
4. Agent 断线、Runtime 不可达、请求超时和超限媒体均有稳定错误码与诊断编号。
5. 单路实时预览、1/4/9/16 分屏、布局保存恢复均能绑定执行节点，现有任务/事件/模型链路回归通过。

