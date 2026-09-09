# ADR-0001：多格式模型执行与可信 PT 边界

- 状态：Accepted
- 日期：2026-09-02

## 背景

内置资产同时包含 ONNX、TorchScript、普通 PyTorch checkpoint 和 ZIP 模型包。原执行链把
`.pt` 按扩展名误认为 TorchScript，且单图测试只列出 Person 的已发布 ONNX 版本。这既隐藏了
已有资产，也会在运行时使用错误加载器。

## 决策

1. 制品格式是命令契约的一部分，由控制面沿 Edge Agent 原样传递给 Runtime；`.pt/.pth`
   归类为 `PYTORCH`，`.jit/.torchscript` 才归类为 `TORCHSCRIPT`。
2. Runtime 使用格式路由器：ONNX Runtime、TorchScript、Ultralytics PyTorch checkpoint、
   ZIP 安全解包。RKNN 与 TensorRT 继续作为目录格式存在，但没有对应硬件后端时不得下发。
3. PyTorch checkpoint 可能触发 pickle 代码执行，只允许来源为 `PRESET` 且 SHA256 已校验的
   制品。自定义 PT 默认拒绝，建议先在隔离转换环境导出 ONNX/TorchScript。
4. ZIP 必须防路径穿越、符号链接和解压炸弹，并校验 bundle manifest 中的成员哈希。单个可执行
   成员可直接路由；多个成员必须有明确的组合适配器，不能依赖文件顺序猜测主模型。
5. 模型 code 到适配器的映射仍由控制面维护，推理和后处理只存在于 Python Runtime。管理端展示
   所有模型与版本，但只有已发布且具备执行格式/适配器的版本能下发。

## 影响

- 优点：一个页面可验证全部内置模型；格式错误可在装载阶段准确诊断；ONNX、PT 与简单 ZIP
  不再需要不同控制面流程。
- 代价：PyTorch/Ultralytics 作为可选 Runtime 依赖会显著增大节点镜像；RK3566 生产部署仍应
  优先转换为 ONNX/RKNN。
- 未覆盖：DAMO-YOLO 的普通 `state_dict` 缺少可执行网络定义；PPOCR、仪表、YOLO-World、
  InsightFace 等多阶段模型包需要逐族实现预处理、流水线和后处理后才能形成真实业务输出。
