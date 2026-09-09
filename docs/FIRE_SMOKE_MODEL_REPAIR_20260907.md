# 烟雾火焰模型部署失败修复记录（2026-09-07）

## 结果与操作入口

现有逻辑模型「火焰烟雾联合检测模型」（71019）已发布新版本 `yolov8n-dfire-13017fe-onnx-20260907`（127），并部署到节点 1（192.168.2.17）。部署 18 为 READY，模型执行状态 READY。平台单图测试 26、27 均 SUCCEEDED。

在模型管理打开该模型，刷新版本列表，选择版本 127 查看部署和测试结果。后续创建现场验证任务应选择此版本，不再重试损坏的版本 24。既有运行任务与规则未改动，没有自动启动烟火实时任务。

## 根因

旧版本 24（`yolov8s-fire-smoke-4adc`）的 ONNX 只有 8,388,608 字节，SHA-256 为 `aad73a66e59cc397495d3a216f484e24736580f588f77d7e667b95c7737dcca5`。本地源文件、MinIO 登记哈希、节点模型文件与上游 LFS 哈希一致。

Protobuf 顶层 graph 字段声明 44,649,862 字节，但文件中只剩 8,388,584 字节。文件内容已经截断，因此 ONNX Runtime 报 INVALID_PROTOBUF。调整置信度、摄像头码流或重新部署同一文件均不能修复。

旧源：<https://huggingface.co/aryantyagiase/yolov8-fire-smoke-detection>，固定修订 `4adc31e5869136b85a4bcd0e91ebc5f9fdd3c2ce`。原 PT 下载内容也未通过 ZIP 完整性验证，未用于执行。

旧版本及失败部署 17 保留用于追溯；没有覆盖不可变模型版本。

## 替代资产与执行契约

- 来源：<https://huggingface.co/rabahdev/fire-smoke-yolov8n>
- 固定修订：`13017fe8af477c25f5298d168e2dfede4b000753`
- 原 PT：6,229,802 字节；SHA-256 `b91633799ceb052c814b4f8b77a37efc9a40f002d528df97d74463585fa4f28f`，与上游 LFS 一致，ZIP 完整性检查通过。
- 声明许可：AGPL-3.0，上传平台时保留许可信息。
- 在隔离容器内用项目已有版本 Ultralytics 8.4.142、Torch 2.2.0 导出 ONNX，不修改节点依赖或引入新执行后端。
- ONNX SHA-256：`3f6ece0156263e5b9a3c66f6717eb082c6c0f44267df158955f976372bd3c5a7`。
- 输入 `[1,3,640,640]`，RGB/FLOAT32/NCHW，缩放 1/255，STRETCH；输出 `[1,6,8400]`，opset 12；关闭 dynamic、simplify 和导出 NMS。
- 原始类别顺序 `smoke, fire`，平台规范名称 `smoke, flame`，fire 仅做名称映射。**模型不具有独立 dense_smoke 类别**，不能据此宣称浓烟分类已验收。

## 验证证据与限制

1. `onnx.checker.check_model(full_check=True)` 通过，ONNX Runtime CPU 完成真实前向执行。
2. 本机使用现有 Runtime ModelPool/GenericOnnxAdapter 测试，烟火样例检出目标，办公室图片未检出。
3. 通过平台正式上传、发布、部署和单图测试 API 操作；节点部署成功，未直接写模型业务表。
4. 节点测试 26：5 个 smoke、3 个 flame，置信度阈值 0.5；预处理 459 ms、推理 1295 ms、后处理 27 ms。
5. 节点测试 27：办公室 3840×2160 图片，0 个烟火目标；预处理 314 ms、推理 1254 ms、后处理 14 ms。

阳性输入来自 [D-Fire 作者展示图](https://github.com/gaia-solutions-on-demand/DFireDataset/blob/master/figures/dfire_examples.png)，包含原有标注框。它和单张办公室图只证明部署与推理链路可用，不是独立准确率评估。当前为 CPU ONNX 执行，约 1.3 秒/次推理，不代表 NPU 加速、实时同步、现场误报漏报或连续事件验收通过。算法验收门禁未改为 PASS。

原始安全脱敏回执、类别契约、文件哈希和导出设置位于 `artifacts/fire-model-repair-20260907/`。

## 防止重复导入损坏资产

`scripts/sync-builtin-model-assets.py` 新增 ONNX 顶层 Protobuf 完整性校验，在缓存命中和新下载后均执行；即使 SHA 与上游一致，也拒绝截断文件。原失败文件保留以便诊断。该检查仅验证顶层封装，不能替代完整 ONNX 校验与实机测试。

对应 6 项回归测试通过：`runtime/.venv/bin/pytest -q scripts/tests/test_model_asset_integrity.py`。

内置 V1 目录仍保存旧来源的历史配置；再次运行同步遇到该损坏文件会明确失败，不会重新标为可用。不要绕过校验或把新模型内容写入旧版本号。当前修复的新版本通过平台管理，迁移目录来源时应另建目录版本并保留这份溯源记录。
