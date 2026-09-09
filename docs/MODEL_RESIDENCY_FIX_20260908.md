# 识别任务启动失败：模型驻留修复

## 现场问题

2026-09-08，节点 `rk3566-field-001` 上的安全帽任务 2、反光衣任务 6 期望状态均为 RUNNING，实际为 FAILED，错误为 `MODEL_COMMAND_FAILED / one or more model versions are not loaded`。升级后的 Agent 日志记录预热了 13 个模型，而 Runtime 默认缓存仅有 4 个槽位。旧实现按顺序加载全部注册模型，LRU 会淘汰先加载的任务依赖，启动任务却只检查模型是否已在内存中。

诊断证据：`artifacts/task-start-diagnosis-20260908/evidence.json`。这解释了已部署模型仍无法启动的问题；现场原生推理和真实流恢复仍须在升级后验证。

## 修改

- Runtime 从本地注册表按需加载任务模型，验证路径范围和 SHA256；单图测试、人脸调用也支持冷缓存加载。
- 完整模型集合在加载前一次性预留，避免加载第二个依赖时淘汰第一个。运行任务、单次原生推理持有模型占用，只允许淘汰闲置模型。
- 多任务共享模型累计占用，重复启动不增加占用。启动失败、运行失败、停止和取消均释放占用；取消线程等待时须等原生加载/推理结束再释放，避免关闭仍被使用的会话。
- Agent 启动只读取本地注册信息，不再预热所有历史模型。
- 容量不足和文件缺失分别返回 `MODEL_CAPACITY_EXCEEDED`、`MODEL_UNAVAILABLE`；Agent 将这两类已脱敏的具体原因上报平台，未知错误继续使用通用提示。
- 保留默认容量 4，未修改任务业务配置、节点身份或摄像头配置。

## 验证

运行 `runtime/.venv/bin/pytest runtime/tests`，245 项通过（1 条现有 Starlette/httpx 弃用警告）；相关源码与测试通过 Ruff 检查。最终闲置 ONNX 对象释放调整后，模型池及驻留回归再次通过。输出保存在 `artifacts/model-residency-fix-20260908/`。

新增回归覆盖 13 个注册模型/4 个缓存槽位下同时启动安全帽与反光衣依赖、完整集合原子预留、共享模型、容量不足时保留其他运行任务、停止后自动重试、启动与推理失败释放、缺失/损坏文件、原生加载和推理取消、冷缓存真实 ONNX 推理、批量加载中途失败，以及 Agent 错误上报。自动化使用本地 ONNX 与合成输入，不能替代现场 RKNN 硬件和摄像头验收。

## 现场部署与验收

2026-09-08 12:34，部署 40 成功，现场节点已升级为 `source-696beef5138c`（原版 `source-9d2adf967364`），节点心跳正常。现场 `pool.py` 和 Agent 命令执行器 SHA256 与本地源码一致。

已启动安全帽任务 2、反光衣任务 6，均为 RUNNING、错误为空、推理后端为 RKNPU。12:35 对 Runtime 执行一次服务重启，两任务无需重新下发启动命令即自动恢复。同一运行 ID 下约 41 秒内，安全帽分析帧数从 29 增至 208，反光衣从 20 增至 150；最终采样分别为 3.943 FPS、3.168 FPS。节点仍注册 14 个模型，Agent 日志明确显示 `loading=on-demand`。任务 7、8 保持 STOPPED。

本次验收确认真实摄像头取帧、RKNN 推理持续运行及重启恢复，不表示已完成告警准确率或长期稳定性验收。证据见 `artifacts/model-residency-fix-20260908/field-after-restart-1.json`、`field-after-restart-2.json` 和 `field-runtime-verification.txt`。

首次部署 38 因网关外网依赖下载缓慢，约 15 分钟后远程命令超时，旧服务未切换。随后准备了 49 个匹配当前 pyproject 的 aarch64/Python 3.12 离线 wheel。部署 39 被超时遗留的部署 38 安装进程占用锁阻止；已通过进程命令与进程组核实后仅终止失败部署 38 的残留进程，确认旧 Runtime/Agent 正常，再通过标准平台流程完成部署 40。未修改数据库部署状态。

离线包准备使用现有脚本及系统 CA：`PIP_CERT=/etc/ssl/cert.pem python3.13 scripts/prepare-node-wheelhouse.py --arch aarch64 --python-version 3.12`，未关闭 TLS 校验。49 个依赖文件全部经过 SHA256 校验，总计约 95.6 MB；后续相同依赖版本的部署可自动复用。校验见 `artifacts/model-residency-fix-20260908/wheelhouse-verification.json`。部署前针对当前源码补跑的 49 项相关测试通过。

如需回滚，使用现有节点部署回滚流程；回滚旧版会重新带回缓存问题。
