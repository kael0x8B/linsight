# 盒子 TCP 实时事件订阅协议 V3

盒子作为 TCP 服务器，业务客户端连接后鉴权、订阅，只接收**订阅确认之后新产生的事件**。断线、客户端尚未启动或处理失败期间的事件不会通过该 TCP 接口补发；协议不再有 `cursor`、历史续读或客户端 ACK。客户端如需避免业务记录重复，仍应以 `sourceEventId` 做幂等键。V3 与原 V2 游标协议不兼容，服务端和客户端须一起升级。

事件 TCP 默认监听 `48902`。事件图片不再嵌入 Base64，事件中提供盒子 HTTP 服务默认 `48901` 端口上的**限时签名图片 URL**；业务客户端必须能够访问这两个端口。HTTP 图片地址可在签发后 1 小时内访问，无需工作台登录 Cookie；URL 本身即访问凭据，密钥轮换或停用订阅后立即失效。图片受网关历史保留期约束，过期或已清理时返回 404。原生 TCP 和默认 HTTP 均为明文传输，现场应使用受控网络或 TLS 代理。

## 启用

1. 升级 Runtime、网关工作台、平台页面和 Java 客户端。TCP 订阅与图片 HTTP 服务都需要启用；默认绑定 `0.0.0.0:48902` 和 `0.0.0.0:48901`。可用 `LINSIGHT_RUNTIME_GATEWAY_EVENT_TCP_PORT`、`LINSIGHT_RUNTIME_GATEWAY_CONSOLE_PORT` 调整端口。
2. 在「事件接口」生成订阅密钥并启用。密钥仅在生成时显示。密钥轮换或启用状态变化会断开当前 TCP 连接。
3. 客户端连接盒子的 TCP 端口，完成下面的 challenge / auth / subscribe 握手。`taskIds` 和 `eventTypes` 分别是任务 ID、事件类型过滤；空数组表示全部。

旧 HTTP 接收地址、路由和投递记录仍留在原 SQLite 表中用于迁移核对，但不会继续执行 HTTP 投递。旧 V2 TCP 历史表仍用于事件内部查询和截图保留，不再向订阅客户端开放历史续读。

## 连接与 HMAC 鉴权

每行一个 UTF-8 JSON 对象，以 `\n` 结束。客户端命令最大 4096 字节，事件帧不含图片正文。连接后盒子先发送：

```json
{"type":"challenge","version":"3.0","nonce":"<48 个小写十六进制字符>"}
```

计算 `auth.hmac` 的步骤：

1. 将工作台生成的**完整订阅密钥**按 UTF-8 编码，作为 HMAC 密钥。
2. 将 `challenge.nonce` 的**字符串原文**按 UTF-8 编码，作为 HMAC 消息。不要将 nonce 的十六进制字符解码成二进制，也不要加入 JSON 引号、整个报文或行尾换行符。
3. 计算 `HMAC-SHA256(keyBytes, nonceBytes)`；把 32 字节摘要编码为 **64 个小写十六进制字符**，放进 `auth.hmac`。直接计算 `SHA-256(key + nonce)` 是错误的。

Java：

```java
byte[] keyBytes = subscriberKey.getBytes(StandardCharsets.UTF_8);
byte[] nonceBytes = challengeNonce.getBytes(StandardCharsets.UTF_8);
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(keyBytes, "HmacSHA256"));
String hmacHex = HexFormat.of().formatHex(mac.doFinal(nonceBytes));
```

演示密钥 `demo-subscription-key` 与演示 nonce `0123456789abcdef0123456789abcdef0123456789abcdef` 计算出 `a6051899ea17459b7a20e8a5f40f4d99833da8ada0ed4168cd93b7bc32936664`。这只是计算示例；真实连接必须使用盒子给出的密钥和当前连接收到的 nonce。

客户端发送一行：

```json
{"type":"auth","hmac":"<64 个小写十六进制字符>"}
```

收到盒子的 `{"type":"authenticated"}` 后，客户端再发送订阅：

```json
{"type":"subscribe","taskIds":[],"eventTypes":[]}
```

盒子回复 `{"type":"subscribed"}`。**从这次订阅确认起**，新产生且匹配过滤条件的事件会被发送；重连后仍只收新事件。订阅成功后立即发送首个 `{"type":"heartbeat"}`，之后约每 30 秒发送一次；客户端无需回复。事件仍约每 0.5 秒检查一次，心跳间隔不会增加事件延迟。一个连接的过滤条件固定，修改过滤条件需重新连接。最多 16 个并发客户端；慢客户端写入超时会断开。

鉴权或协议失败时盒子发送 `{"type":"error","code":"..."}` 后断开。错误码包括 `DISABLED`、`UNAUTHORIZED`、`BAD_REQUEST`、`CONFIG_CHANGED`、`SNAPSHOT_UNAVAILABLE`、`IMAGE_HTTP_UNAVAILABLE`。`SNAPSHOT_UNAVAILABLE` 会附带 `sourceEventId`；不再有 `CURSOR_EXPIRED`。客户端应及时下载图片；TCP 写入成功不代表客户端已保存事件或图片。

## 事件字段：逐项中文说明

下面是带注释的 **JSONC 示意**（`//` 注释不可作为实际 JSON 发送）。可为空的字段用 `null` 表示；算法识别结果随算法变化。

```jsonc
{
  "type": "ai-video.event.created", // 消息类型：新建识别事件
  "version": "3.0",                  // 协议版本；V2 客户端不能直接读取
  "sourceEventId": "<UUID>",         // 事件唯一 ID；客户端幂等去重键
  "deliverySource": "GATEWAY",      // 来源：盒子本地事件
  "occurredAt": "2026-09-24T02:15:30.123+00:00", // 事件发生时间，带时区
  "data": {
    "sourceEventId": "<UUID>",       // 与顶层相同的事件 ID
    "eventType": "AREA_INTRUSION", // 事件类型，以下以区域入侵为例
    "severity": "MAJOR",           // 事件严重程度；取规则产生的原值
    "occurredAt": "2026-09-24T02:15:30.123+00:00", // 事件发生时间
    "taskId": 101,                 // 识别任务 ID
    "taskName": "禁入区域识别",       // 识别任务显示名称；旧事件可能为空串
    "taskRunId": "<UUID>",         // 本次任务运行 ID
    "algorithmId": 301,            // 识别算法 ID
    "algorithmName": "区域入侵",     // 识别算法显示名称；旧事件可能为空串
    "modelVersionId": 401,         // 推理模型版本 ID
    "pipelineVersionId": 501,      // 算法 Pipeline 版本 ID
    "ruleId": 601,                 // 触发事件的规则 ID
    "ruleVersionId": 701,          // 规则版本 ID
    "cameraId": 201,               // 发生事件的摄像头 ID
    "cameraName": "东侧摄像头",      // 摄像头显示名称；旧事件可能为空串
    "location": {                  // 任务配置中的位置对象，未配置时为 {}
      "locationCode": "ZONE-01",  // 位置编码，若任务配置提供
      "locationName": "作业一区"    // 位置名称，若任务配置提供
    },
    "result": {                    // 算法原始识别结果；结构随算法变化
      "class": "person",          // 识别目标类别；本例为人员
      "confidence": 0.95,          // 目标检测置信度，范围 0 到 1
      "bbox": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}, // 归一化坐标框
      "trackId": "person-1",      // 算法目标跟踪 ID，可能为空
      "attributes": {}             // 此事件没有扩展识别属性；其他算法可提供自己的键
    },
    "activityId": "<活动 ID>",     // 规则活动 ID，用于关联同一识别活动
    "dedupKey": "<去重键>",         // 规则产生的去重键
    "trackId": "person-1",       // 事件级跟踪 ID，可能为空
    "firstSeenAt": "2026-09-24T02:15:29.123+00:00", // 首次观察时间，可能为空
    "lastSeenAt": "2026-09-24T02:15:30.123+00:00",  // 最近观察时间，可能为空
    "durationMs": 1000,            // 确认持续时间，单位毫秒
    "maxConfidence": 0.95,         // 事件确认阶段的最高目标检测置信度
    "snapshot": {                  // 事件截图；不再包含 base64
      "contentType": "image/jpeg", // 图片媒体类型
      "url": "http://<当前TCP连接使用的盒子IP>:48901/event-images/<事件UUID>?expires=<秒级时间戳>&signature=<签名>", // HTTP 下载地址，IP 不是写死值
      "sha256": "<64 个小写十六进制字符>", // HTTP 返回的完整 JPEG 字节 SHA-256
      "expiresAt": "2026-09-24T03:15:30.000+00:00" // 图片地址失效时间
    }
  }
}
```

### `data.result` 与 `attributes` 的关系

通用事件**没有**顶层 `plateNumber`，也没有要求所有算法输出车牌号。`data.eventType` 是业务事件类型；`data.result.class` 是本次事件的识别目标类别；`data.result.attributes` 是**该算法附加在目标上的键值对象**，可为空 `{}`，不是固定的全局字段集。它来自事件生成时的 `objectSnapshot`，值类型为字符串、数字、布尔值或 `null`。每个键都是可选的，未产生该信息时会**缺失**，接收方不能把缺失当成 `false` 或空字符串。内置或后续安装的算法包可增加自己的键；未知键应原样保留。通用识别结果先看 `class`、`confidence`、`bbox`，算法特有内容再看 `attributes`。

| 字段路径 | 含义 |
| --- | --- |
| `data.result.class` | 目标类别，例如 `person`、`license_plate`、`fall`；它不是事件类型。 |
| `data.result.confidence` | 当前目标检测置信度，范围 `[0,1]`；车牌 OCR 置信度另见 `attributes.ocrConfidence`。 |
| `data.result.bbox.x/y/width/height` | 原始画面中的归一化坐标框，范围 `[0,1]`。 |
| `data.result.trackId` | 算法目标跟踪 ID，可能为空；与事件级 `data.trackId` 分开读取。 |
| `data.result.attributes` | 当前目标的可选扩展属性，按下表和算法类别解释。 |

当前内置流水线中，通用或显示相关的 `data.result.attributes` 键如下；它们不是每个事件都必有：

| 属性键 | 类型 | 含义 |
| --- | --- | --- |
| `classId` | 整数 | 检测模型输出的类别索引；业务类别仍看 `result.class`。 |
| `eventCandidate` | 布尔 | 当前目标是否可进入规则候选；最终是否产生事件由规则确认。 |
| `displayLabel` | 字符串 | 叠框显示文字；**不是**车牌等结构化识别值的权威字段。 |
| `displayConfidence` | 数字或 `null` | 叠框展示的置信度；可能不同于检测置信度。 |
| `displayState` | 字符串 | 展示状态，例如 `alert`、`normal`、`unknown`、`neutral`。 |
| `visibleByDefault` | 布尔 | 默认是否绘制此目标的叠框。 |
| `displayBoxX/Y/Width/Height` | 数字 | 展示用归一化坐标框；可能与事件 `bbox` 不同。 |
| `displayGeometryContinuity` | 布尔 | 展示层沿用明确的目标几何位置，主要用于车牌框。 |

### 车牌 `attributes`：业务字段和诊断字段

只有车牌算法产生的事件才可能带有车牌属性。例如 `data.result.class = "license_plate"` 时，`data.result.attributes` 可能为 `{"plateNumber":"京A12345","plateText":"京A12345","ocrStatus":"CONFIRMED"}`。`plateNumber` 是**车牌算法的专有属性**，不是通用事件字段；只有多帧 OCR 确认后才会出现。`plateText` 是本帧原始 OCR 候选，可能未确认或不符合车牌格式。车牌业务应先判断 `ocrStatus == "CONFIRMED"` 且 `plateNumber` 为非空字符串。

| 属性键 | 类型 | 含义 |
| --- | --- | --- |
| `plateNumber` | 字符串 | 多帧投票后确认的车牌号码，业务取值字段。 |
| `plateText` | 字符串 | 当前帧 OCR 候选文字，不可直接当作确认车牌。 |
| `ocrStatus` | 字符串 | OCR 状态：`CONFIRMED` 已确认；`PENDING` 待确认；`LOW_CONFIDENCE`、`LOW_CHAR_CONFIDENCE`、`MISSING_CONFIDENCE`、`INVALID_CONFIDENCE`、`UNSUPPORTED_FORMAT`、`UNAVAILABLE` 表示未通过对应检查。 |
| `ocrConfidence` | 数字 | 当前帧 OCR 平均字符置信度，范围 `[0,1]`。 |
| `ocrMinCharConfidence` | 数字 | 当前帧置信度最低的字符分数，范围 `[0,1]`，用于防止单字误识。 |
| `plateConfidence` | 数字 | 确认车牌的有效投票平均置信度，范围 `[0,1]`；与检测框的 `result.confidence` 不同。 |
| `ocrVoteCount` / `ocrVoteFrames` / `ocrVoteAgreement` | 整数 / 整数 / 数字 | 获胜候选的票数、窗口内帧数、一致比例。 |
| `plateColor` / `plateColorConfidence` | 字符串 / 数字 | 车牌颜色及颜色模型置信度；内置颜色值为 `BLACK`、`BLUE`、`GREEN`、`WHITE`、`YELLOW`。 |
| `plateType` | 字符串 | 上游模型提供的车牌类型；当前内置 OCR 未保证输出。 |
| `vehicleTrackId` | 字符串 | 与该车牌关联的车辆目标跟踪 ID。 |
| `plateLayout` / `ocrLayout` | 字符串 | 车牌排版（`SINGLE` / `DOUBLE`）及 OCR 版式（`STANDARD` / `YELLOW_SIDEBAR`）。 |
| `ocrCharset` | 字符串 | OCR 字符集标识，例如 `CHINESE_MAINLAND`。 |
| `ocrNumberRegionLeft` | 数字 | OCR 号码区域在裁剪图中左侧偏移的归一化比例。 |
| `corner1X/Y`～`corner4X/Y` | 数字 | 车牌四角在原始画面中的归一化坐标，用于透视矫正。 |
| `rectificationSource` | 字符串 | 四角/矫正来源，例如 `YOLO_PLATE_QUADRILATERAL`、`YUNET_QUADRILATERAL`。 |
| `plateInputRegion` / `plateProposalParent` | 字符串 | 车牌检测输入区域及颜色候选区域的父区域，例如 `FULL_FRAME`、`RULE_ROI`、`COLOR_PROPOSAL`。 |
| `plateDetectorThreshold` | 数字 | 颜色候选车牌检测时使用的置信度阈值。 |
| `plateCropStatus` | 字符串 | 裁剪方式或失败原因：`PERSPECTIVE`、`BOUNDING_BOX`、`INVALID`。 |
| `plateCropWidth` / `plateCropHeight` | 整数 | 用于 OCR 的车牌裁剪图像素宽高。 |
| `plateCropMargin` / `plateCropRetried` | 数字 / 布尔 | 裁剪边距比例、是否放宽区域再次 OCR。 |

### 其他内置算法的 `attributes`

| 算法/场景 | 属性键 | 含义 |
| --- | --- | --- |
| 安全帽、反光衣 | `helmet` / `vest` | 状态 `present`（已佩戴）、`absent`（未佩戴）、`unknown`（无法确认）。 |
| PPE 关联 | `ppeConfirmedPerson`、`ppeConfidence`、`ppeSourceClass` | 已与人员目标关联、PPE 证据置信度、证据类别。 |
| PPE 证据框 | `ppeBoxX/Y/Width/Height` | PPE 证据的归一化坐标框，不等于人员框。 |
| 吸烟、打电话、跌倒等行为 | `behaviorPersonAssociated`、`smokingEvidence`、`temporalConfirmationOwner` | 是否关联到人员、吸烟证据类型、时序确认归属；`RULE` 表示由规则确认。 |
| 打架 | `requiresReview` | 该事件需人工复核。 |
| 人数统计/数量规则 | `observedCount`、`countScope`、`observedAtMillis` | 观测人数、统计范围（如 `CAMERA_ROI`）、观测时间戳（毫秒）。 |
| 数量规则 | `minimumCount`、`thresholdCount`、`comparison` | 规则最小/阈值人数与比较方式。 |
| 指定人员离岗 | `assignedPersonId`、`assignedPersonName`、`presenceState` | 指定人员 ID、姓名、在岗状态 `present` / `absent` / `unknown`。 |
| 人脸识别 | `identityId`、`identityCompared`、`liveness` | 比对出的身份 ID、是否执行身份比对、活体检查状态；`NOT_VERIFIED` 表示未核验。 |
| 通用文字识别 | `text`、`ocrConfidence` | OCR 文本和识别置信度，不等于车牌确认字段。 |

这些是当前内置实现中的已知键；自定义算法包可输出其他属性。接入方应按 `data.eventType`、`data.algorithmId` 和 `data.result.class` 选择解析规则，不应把任何一个 `attributes` 键当作所有事件的必填字段。

## 图片下载与客户端处理

服务端在每个 TCP 连接上取得该连接使用的盒子本地 IP（socket local address），再配上当前图片 HTTP 端口（默认 `48901`）生成完整地址。客户端连接盒子的另一块网卡 IP 时，新事件 URL 会跟着变。客户端必须能从自身网络访问该地址；经 NAT 或代理接入时，盒子看到的本地 IP 可能不是客户端可达的公网地址，这种部署需另行提供可达的代理地址。IP 在图片 URL 签发后变化，旧 URL 也可能失效。

客户端收到事件后，对 `data.snapshot.url` 发起 HTTP GET。局域网盒子地址应从客户端**直连**；若客户端电脑启用了系统或环境代理，应将盒子 IP 加入代理绕过名单，否则 TCP 事件可到达而图片下载可能超时。该 URL 上的 `signature` 是**访问授权签名**，不需要工作台 Cookie 或额外 Header；成功响应为 `image/jpeg`。`data.snapshot.sha256` 是**原始 JPEG 文件字节的 SHA-256 摘要**，用于检查下载到的是否为完整且对应的那张图片，不是密钥、密码、加密结果，也不是 URL 授权签名。客户端应计算 `SHA-256(HTTP 响应体全部字节)`，转成 64 个小写十六进制字符，与 `data.snapshot.sha256` 完全比较；不一致就不要将图片当作有效事件证据。签名 URL 不应写入长期公开页面；保留期内的截图仍可能因设备清理而不可用。网关图片服务必须在客户端可达的 HTTP 地址监听。

可运行的 Java 17 + Netty 客户端示例见 [gateway-event-netty-client](../examples/gateway-event-netty-client/README.md)。它会自动完成鉴权、实时订阅、图片下载与校验，并按 `sourceEventId` 保存事件。网关状态通过 `event-stream.status` 查询，返回启用状态、TCP 端口、图片 HTTP 端口和在线客户端数，不返回密钥。
