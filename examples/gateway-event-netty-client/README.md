# 盒子 TCP 实时事件 Netty 客户端示例

此示例对应[盒子事件订阅协议 V3](../../docs/GATEWAY_EVENT_DELIVERY.md)。客户端连接盒子 TCP 端口，完成 HMAC-SHA256 鉴权并订阅实时事件，按事件中的限时 HTTP 地址下载 JPEG、校验 SHA-256，然后用 `sourceEventId` 保存图片和事件 JSON。协议没有游标：**客户端离线期间的事件不会补发**。

## 鉴权与订阅顺序

盒子先发送 `challenge`；客户端以订阅密钥的 UTF-8 字节为 HMAC 密钥、以 nonce **字符串原文**的 UTF-8 字节为消息，计算 HMAC-SHA256，并把摘要转为 64 个小写十六进制字符发送 `auth`。不要先把 nonce 当作十六进制数据解码。收到 `authenticated` 后再发送 `subscribe`：

```text
{"type":"challenge","version":"3.0","nonce":"…"}
{"type":"auth","hmac":"<64 个小写十六进制字符>"}
{"type":"authenticated"}
{"type":"subscribe","taskIds":[],"eventTypes":[]}
{"type":"subscribed"}
```

上面每个 JSON 对象是**独立的一行**，以 `\n` 结尾；空数组表示全部任务或全部事件类型。本示例已经自动完成握手。计算代码在 [GatewayEventClient.java](src/main/java/com/linsight/examples/gateway/GatewayEventClient.java) 的 `onChallenge`。

## 构建和运行

需要 JDK 17、Maven 3.9+。这是独立 Maven 工程。

```bash
cd examples/gateway-event-netty-client
mvn package
java -jar target/gateway-event-netty-client-1.0.0.jar
```

`GatewayEventClient.main` 开头的 `defaultHost` / `defaultPort` 是此示例连接 TCP 的默认地址，目前填的是测试盒子 `192.168.2.14:48902`；可传 IP 参数或用 `GATEWAY_HOST` / `GATEWAY_PORT` 覆盖。**这不是服务端图片 URL 的固定 IP。** 服务端按本次 TCP 连接使用的盒子本地 IP 生成 `data.snapshot.url`，图片 HTTP 默认端口为 `48901`。客户端须能访问事件给出的完整 URL；如通过 NAT/代理访问，需保证该地址从客户端可达。

程序优先读取 `GATEWAY_EVENT_KEY`，未设置时使用 `main` 开头的 `subscriberKey`；两者都为空则在终端提示输入订阅密钥（不回显）。在没有交互式终端的 IDE 中，可在本地填写 `subscriberKey` 或设置环境变量。不要将填写了真实密钥的源码提交到仓库。

可选环境变量：

| 变量 | 默认 | 用途 |
| --- | --- | --- |
| `GATEWAY_HOST` | `main` 中的 `defaultHost` | 盒子 TCP 地址 |
| `GATEWAY_PORT` | `48902` | 盒子 TCP 端口 |
| `GATEWAY_TASK_IDS` | 空 | 逗号分隔任务 ID；空表示全部 |
| `GATEWAY_EVENT_TYPES` | 空 | 逗号分隔事件类型；空表示全部 |
| `GATEWAY_OUTPUT_DIR` | `./gateway-events` | JPEG 与事件 JSON 输出目录 |
| `GATEWAY_MAX_EVENTS` | `0` | 收到指定数量事件后退出；0 表示持续运行 |
| `GATEWAY_TLS` | `false` | 通过带有效证书的 TLS 代理连接 TCP；盒子原生端口为明文 |

例如只收车牌识别事件，接到一条后退出：

```bash
GATEWAY_EVENT_TYPES=VEHICLE_PLATE_RECOGNIZED \
GATEWAY_MAX_EVENTS=1 java -jar target/gateway-event-netty-client-1.0.0.jar
```

客户端会打印实际订阅的 `taskIds`、`eventTypes`，收到首个心跳及之后约每 30 秒打印一次连接存活提示。盒子每 30 秒发送一次心跳，客户端 75 秒未收到任何消息才判定连接超时。`subscribed` 和心跳仅说明连接正常；协议只推送订阅确认后新产生、且同时匹配两个过滤条件的事件。界面上的任务名称可能含摄像机编号，不能用名称中的数字代替事件里的 `data.taskId`；事件类型也必须使用 `data.eventType` 的原始值。排查收不到事件时，先把两个过滤条件都留空，再在盒子「本地事件」查看是否出现订阅后的新记录。

收到事件后，示例在控制台打印**格式化后的事件 JSON**，再下载、校验并保存图片和 JSON 文件，最后打印两个文件的完整路径。控制台只隐藏 `data.snapshot.url` 的限时签名查询参数；保存的 JSON 文件保留可在有效期内使用的完整图片 URL，并增加本地图片 `fileName`。图片 HTTP 客户端显式直连盒子，不使用电脑上的系统代理；在使用系统代理的电脑上，局域网图片 URL 经代理可能超时。若控制台已打印事件 JSON，但没有出现“事件已保存”，检查随后报出的下载或校验错误。

## 事件字段与业务接入

- `GatewayEvent` 包含事件类型、发生时间、任务 ID、算法 ID、摄像头 ID、识别结果、图片 URL 和下载校验后的 JPEG。完整字段见[协议文档中的逐项中文注释](../../docs/GATEWAY_EVENT_DELIVERY.md#事件字段逐项中文说明)。
- 通用识别结果读取 `event.result().path("class")`、`confidence`、`bbox`；`data.result.attributes` 是算法附加的可选键值对象，可能为空 `{}`，没有适用于所有事件的固定属性清单。各键的中文定义见[协议字段表](../../docs/GATEWAY_EVENT_DELIVERY.md#dataresult-与-attributes-的关系)。
- **仅车牌算法事件**才读取 `event.result().path("attributes").path("plateNumber").asText("")`，对应 `data.result.attributes.plateNumber`。`plateText` 只是 OCR 候选文字，可能尚未确认；其他算法事件不要求这两个字段。
- `data.snapshot.sha256` 是**图片内容摘要**：客户端对 HTTP 返回的 JPEG 全部字节计算 SHA-256，并与它比较，校验图片是否完整且对应事件。它不是订阅鉴权用的 `auth.hmac`，也不是图片 URL 的 `signature`。示例的 `GatewayEvent.parse` 已自动完成该校验。
- `FileEventSink` 是文件示例处理器；业务系统可实现 `EventSink` 并替换注入。以 `sourceEventId` 做幂等键。图片 URL 1 小时后失效，收到事件就应下载并保存需要长期保留的图片。
- 网络断开后客户端会重新连接并订阅**新的实时事件**；停机、断线、下载失败期间的事件不会由 TCP 接口补发。需要可靠历史处理时，应另行使用网关事件历史或平台事件链路。
