# 图片识别：可复用算法验证集

入口：节点详情 / 网关本地的识别算法操作 → **图片识别 → 算法验证集**。
沿用 P21 双入口、Java 节点鉴权与反向通道、Runtime 单图推理、Vue/Vben 表单和表格。

## 使用

1. 新建或选择当前网关的验证集，批量上传现场 JPG、PNG、WebP 静态图片。
2. 逐图编辑期望类别、数量、最低置信度、可选车牌文字及备注。新上传图片默认期望零个目标；应先核对期望再运行。
3. 选择本机任务/Pipeline 版本、各模型角色的已部署模型版本，或同一算法的已安装算法包版本。
4. 运行后查看通过、失败、无法判定、执行错误、待运行状态；点击查看可叠框。历史运行独立于后来修改的验证集。
5. 导出自包含 HTML 报告，含图片、叠框、逐图期望与结果、备注、耗时、诊断编号、模型 SHA256、算法包版本、任务版本和参数。报告可离线打开或通过浏览器打印。

匹配条件：置信度 ≥ 阈值；类别留空表示所有类别；车牌文字留空表示不校验文字，否则按 plateText / plateNumber 精确匹配。匹配数量等于期望数量判为通过。数量 0 表示不应出现匹配目标。本版不评估框的位置或 IoU，不推导 mAP。算法 observationValid=false 判为无法判定；推理/资源/文件错误独立记为执行错误，不能当成零目标通过。单图不代替连续帧、时长或真实现场的视频验收，不执行规则、不产生告警事件、不修改运行任务。

## 状态、限制与可恢复性

- 每张 ≤ 4 MB、1600 万像素；每集最多 50 张，每网关最多 50 集，每集保留最多 100 次运行；图片总配额 512 MB。
- 图片逐张保存，非法文件明确提示；已成功上传的部分保留。网关验证集与本机用户身份共用该设备的管理授权，不跨网关自动同步。
- 修改使用 expectedRevision 和 requestId；运行固定任务修订号、模型 ID/SHA256、算法包、参数、图片和期望快照。角色、已部署模型和算法包参数由 Runtime 再次验证。
- 一次只识别一张，沿用原图片识别 90 秒超时/资源限制。浏览器关闭或暂停后不再提交后续图片；已提交的当前图片完成后保存，待运行图片可在历史中继续。
- Runtime 重启将正在识别的图片记为执行错误，保留其他结果与待运行图片。错误图片可新建一轮重新验证。模型卸载或同 ID 制品变更会产生执行错误，不能冒用历史版本。
- 网络响应丢失时刷新列表与版本/历史，读取设备上的持久结果；同一运行同一图片重试不重复执行已完成推理。
- 移除样本不删除历史图片；删除整个验证集有二次确认，同时删除运行历史及不再被其他集/历史引用的图片。达到运行上限时先导出，再新建验证集。
- 单张结果超过 256 KB 显式返回执行错误；列表不携带全部目标。原图按 384 KB 分块读取，适配既有平台反向通道 JSON 限制。

## 数据、接口与权限

业务所有者为 task 下的图片验证用例，复用 ADR-20260908 的设备自治边界。
Java 保留节点租户校验、`ai-video:node:query` + `ai-video:model:test` 双权限；浏览器不能通过只读 query 触发验证。
本地入口复用网关会话及同源保护。API 请求/响应日志不记录图片内容，Runtime 变更日志仅记录集合/运行 ID、请求 ID 和操作类型。

平台 action 接口：`POST /admin-api/ai-video/node/gateway/image-validation`。
本地：原 `/gateway-api/rpc` → `/v1/gateway/rpc`。
动作：`validation.list/options/get/save/sample-save/sample-delete/image/delete/runs/run-create/run-get/run-item/result`。
契约 schemaVersion 为 `1.0`，白名单参数禁止浏览器提交任务配置、源地址或制品路径。

首次启动在既有 `gateway/configuration.sqlite3` 中创建 `image_validation`、`image_validation_receipt` 及 `(kind,parent_id)` 索引。
记录复用设备密钥加密；图片放 `gateway/validation/<sha256>`，文件权限 0600，目录 0700。
不新建数据库、服务、MySQL 表、Maven Module，也不迁移中心资产所有权。

## 发布、回滚与验证

先备份完整 runtime-data/gateway（数据库、密钥、验证图片需一起备份），再部署 Java、前端和 Runtime/网关控制台。
能力标识 `task.image-validation.v1`；旧网关显示升级提示，原单图功能继续可用。
这是本地增量建表，空库和已有库启动均执行 IF NOT EXISTS；不扫描或改写已有任务，规模取决于验证记录。
回滚保留上述新表和图片即可，旧版本不读取这些表。不得只恢复数据库而漏掉图片或密钥。

自动测试：

- Runtime：`tests/test_image_validation.py`（真实 ONNX、快照、重复请求、并发修订、版本变更、重启恢复、图片清理、鉴权与匹配规则）及现有单图/网关自治回归。
- Java：`NodeGatewayValidationTest`、`NodeGatewayImageTest`（权限声明、动作白名单、上传上限、网关结果）。
- Vue：`tests/node-image-validation.test.ts`（报告转义、叠框、分块和取消）及原单图组件测试；vue-tsc、lint。
- 浏览器：`tests/e2e/image-validation.mjs` 使用 18903 隔离 Runtime 测试实例及真实 ONNX 合约模型，覆盖批量上传、编辑期望、通过/失败、叠框、下载报告。测试样图及合约模型不代表现场算法准确率。

现场验收仍需要用户的真实图片、目标模型/算法版本和期望结果；本次工程测试不作现场准确率结论。

浏览器测试启动（隔离数据只写系统临时目录）：

```sh
PYTHONPATH=runtime:runtime/tests runtime/.venv/bin/python runtime/tests/serve_image_validation.py
# 另一个终端，管理端开发服务保持在 5666
cd frontend
node tests/e2e/image-validation.mjs
```

浏览器测试输出位于 `output/image-validation/`，包括结果截图和导出的示例报告。
