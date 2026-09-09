# LInsight Webhook 投递协议 V1

## 1. 适用范围

本协议描述 AI 事件从中心控制面投递到租户配置的 Webhook 端点的安全、幂等与重试语义。
端点只允许公网 `https://` 地址、443 端口，不允许 userinfo、回环、链路本地或私网地址。

## 2. 请求

控制面以 `POST` 发送事件 outbox 中保存的原始 JSON envelope，`Content-Type` 为
`application/json`。请求至少包含以下头：

| Header | 含义 |
| --- | --- |
| `X-LInsight-Timestamp` | 发送时 Unix 秒时间戳 |
| `X-LInsight-Nonce` | 本次尝试的随机 UUID；每次重试都会变化 |
| `X-LInsight-Signature` | `v1=<hex HMAC-SHA256>` |
| `X-LInsight-Event-Id` | 业务幂等键；真实事件为 `event:<eventId>`，重试保持不变 |

事件载荷沿用实时协议 envelope：`type`、`version`、`messageId`、`occurredAt`、`data`。
端点的事件类型和严重级别过滤均为空时表示全部订阅。管理端“测试”使用明确标记
`data.simulated=true` 的模拟事件，不代表真实告警。

## 3. 签名校验

待签名字节串必须使用收到的原始请求体，不得先解析再格式化：

```text
signing_input = timestamp + "." + nonce + "." + raw_request_body
signature = hex(HMAC-SHA256(webhook_secret, UTF-8(signing_input)))
header = "v1=" + signature
```

接收端应使用常量时间比较，并建议拒绝超过 5 分钟的时间戳、在相同窗口内重复的 nonce。
业务处理必须按 `X-LInsight-Event-Id` 幂等；只有业务已持久化后才返回 2xx。

## 4. 成功、重试与死信

- 任意 2xx 响应视为成功，其他状态、网络错误或超时视为失败。
- 第一次失败后按 `5 * 2^(attempt-1)` 秒退避，最大 3600 秒；最大尝试次数由端点配置，最多 10 次。
- 达到最大次数后进入 `DEAD`。只有具备 `ai-video:webhook:replay` 权限的用户可手工重放。
- 同一租户、端点和 `messageId` 只有一条投递记录；outbox 重试不会重复创建业务投递。
- 响应正文先做敏感信息脱敏，再截断到 2000 字符。签名密钥加密存储，仅创建时返回一次。

## 5. 全局通知开关

P24 的 `notificationsEnabled=false` 会在事件进入 Webhook 队列前阻断新增投递；已存在的投递
仍按其状态继续处理。需要完全停止外发时，应同时停用具体 Webhook 端点。
