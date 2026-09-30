# 边缘节点部署与依赖说明

## 部署入口与成功条件

通过平台“边缘节点”的初始部署或在线升级入口操作。已有节点沿用原节点身份，部署前完成预检，部署详情提供持久化 SSH 日志。完整日志中的 `LINSIGHT_ERROR` 用于定位失败原因。

系统依赖、Python 环境和导入检查均在停止旧服务前完成；切换时保留快照和回滚看门狗。部署成功必须同时满足目标版本一致、新鲜心跳和 `runtimeStatus=UP`。网关网页还需满足 `48901/gateway-health` 的 `owner=runtime` 及首页可访问，不能仅凭进程启动判断成功。

## 准备离线依赖

在能稳定访问 PyPI 的构建机或控制面主机，从项目根目录执行：

```bash
uv run --with pip --no-project python scripts/prepare-node-wheelhouse.py --arch aarch64 --python-version 3.12
```

也可用已安装 pip 的受支持 Python 直接运行脚本。其他 CPU 架构或 Python 小版本需要单独准备匹配的制品。

`runtime/deployment-wheels/` 按 `pyproject.toml SHA256 / CPU 架构 / Python 小版本` 缓存依赖及逐文件 SHA256。依赖契约变化后须重新生成。控制面校验并随源码打包，节点通过 `PIP_NO_INDEX=1` 离线安装；清单错误或文件被篡改时拒绝打包，不静默回退。未准备匹配 wheelhouse 时，预检会提示在线安装需求。

wheel 集合进入部署包 SHA256，依赖变化会改变目标版本。制品须随 Runtime 发布目录部署到控制面，不能因为这些二进制缓存未纳入 Git 就遗漏。

Ubuntu 22.04 等节点若只有 Python 3.10，启用“自动安装”后会在 `/opt/linsight/python/3.12.14` 安装独立解释器，系统的 `/usr/bin/python3` 保持不变。安装包固定为 `python-build-standalone` 的 20260924 发行版，并校验 SHA256；支持 ARM64 与 x86_64。节点可访问 GitHub 时自动下载。离线现场可提前把对应的 `cpython-3.12.14+20260924-<架构>-unknown-linux-gnu-install_only.tar.gz` 放进控制面 Runtime 源目录的 `deployment-python/`；打包时会校验并随部署包上传。若既无离线包又无法下载，部署在服务切换前失败，日志会指出下载错误。

## 系统 Python、venv 与锁定包

安装器先选择已有的 Python 3.12/3.13；没有时按上节独立安装 Python 3.12.14。随后检查 Python venv/pip、FFmpeg、curl 和 CA 的实际能力，可用时跳过 APT。确有缺失时只补齐对应依赖；所有安装方案先模拟求解，并拒绝移除包、降级、修改厂商 hold 或升级无关系统组件。关闭“自动安装”时，目标节点必须已有受支持的 Python。

缺少 venv 时，优先匹配现有解释器的完整版本；必要时只考虑同一 Python 小版本的配套候选版本，固定已校验版本后安装，再进行能力验证。不会自动改写软件源、APT pin、解除 hold 或执行整机升级。

标准 venv/pip 不可用时，安装器可复用 `runtime/ai_runtime/app/core/environment.py`：从已校验的 Runtime 包创建不带 pip 的隔离环境，再用随包、固定 SHA256 的 pip wheel 离线引导。引导不写入系统 Python，也不解除 hold；前提是现有受支持解释器仍能执行标准库 venv 的无 pip 创建流程。

pip 引导可离线不代表全部 Runtime 和模型依赖已离线就绪，仍需准备相应 wheelhouse。若 Python 本身损坏、配套版本不可用或安全模拟失败，应根据完整日志修复环境后重试，不绕过安装保护。

## 源码与网关控制台制品

`LINSIGHT_NODE_DEPLOYMENT_RUNTIME_SOURCE` 可显式指定控制面使用的 Runtime 源目录；项目标准启动脚本会设置绝对路径。独立部署时须同步完整 Runtime 源码、bootstrap wheel、离线依赖和网关网页资源。只更新前端不会更新节点安装脚本或 Python 依赖。

网关网页不再以展开后的 JS/CSS 文件纳入源码。首次部署和每次前端变更后，在项目根目录执行：

```bash
make gateway-console
```

构建会在 `runtime/gateway-console/` 生成 `manifest.json`、内容寻址的 `tar.gz` 以及本地 `current/`
副本。控制面打包前校验制品 SHA256；节点解压 Runtime 包后再次校验制品、归档边界和逐文件 SHA256，
然后原子安装 `current/`。缺少 manifest、引用的制品不存在或摘要不匹配都会在停止旧服务前失败。
独立部署控制面时必须把 manifest 和它引用的 `tar.gz` 放到 Runtime 源目录的 `gateway-console/`，
无需携带本地 `current/` 展开目录。

网关网页构建与入口迁移见 [网关双入口说明](GATEWAY_DUAL_ENTRY.md)。前端或依赖脚本更新后需重新生成对应制品并启动控制面，再从平台重试部署；标准本地启动命令为 `make backend`。

## Rockchip 分析取帧分辨率

Runtime 根据已识别的 RKNN 运行目标自动选择硬解分析帧上限：RK3588 / RK3588S 为
3840×2160，其他芯片或未确认型号保持 1920×1080。输入小于上限时不放大，子码流仍使用其原始
分辨率。新盒子通过同一部署包获得此默认行为，不需要逐台修改采集配置。

MPP/RGA 按 `LINSIGHT_RUNTIME_TASK_CAPTURE_FPS` 采样（默认 4 FPS）。H.264 预览直接转发摄像头编码包；H.265 预览在 Runtime 内软件解码并限幅编码为 H.264，默认最高 1280×720、12 FPS，部署前须按并发摄像头数验证节点 CPU、内存和识别帧率。
车牌检测适配器缩放至模型固定的 640×640 输入，定位坐标映射回保留的原图后裁剪车牌，再送入 OCR。
车辆检测复用同一张已解码原图，避免额外解码 4K JPEG。扩大分析帧分辨率不会自动改善模型或改变
置信度门槛，现场仍需分别核验整牌正确率、延迟和内存。

现场有明确资源预算时，可在 Runtime 环境中显式配置
`LINSIGHT_RUNTIME_ROCKCHIP_CAPTURE_MAX_WIDTH` 和
`LINSIGHT_RUNTIME_ROCKCHIP_CAPTURE_MAX_HEIGHT` 覆盖自动上限。未配置表示自动，不能填空字符串。
验收应同时检查采集进程尺寸、识别结果的 `sourceWidth/sourceHeight`、实际车牌裁剪尺寸和采样帧率，
不能仅凭浏览器预览清晰度判断 AI 使用了 4K。

## GPU / NPU 资源上报

Edge Agent 从 Rockchip 内核只读接口采集加速器负载：GPU 使用 devfreq 的 `load`，RKNPU 优先使用
`/sys/kernel/debug/rknpu/load`，并兼容单核、多核及 devfreq 回退格式。心跳分别发送 `gpuUsage` 和
`npuUsage`；平台卡片在两者同时存在时显示较高的即时负载，只有内核没有暴露或 Agent 无法读取时才显示
“未上报”。Rockchip 使用统一内存，因此不伪造独立显存数值。

在线重部署会安装 `linsight-accelerator-metrics-permissions.service`，只把 RKNPU 的负载文件授予 Agent
运行用户读取，并在每次开机后恢复该权限；不会授予 Agent 绕过整机文件权限的能力。若系统未启用
`CONFIG_ROCKCHIP_RKNPU_DEBUG_FS` 且没有可读的 NPU devfreq `load`，应保留未上报状态并检查内核配置，
不能用推理帧率代替硬件使用率。

## 磁盘不足自动处置

在线部署会安装 `linsight-disk-pressure-cleanup.timer`，开机五分钟后开始巡检，此后每 15 分钟检查一次
根分区。默认在 80% 触发常规回收，90% 进入紧急回收；阈值位于
`/etc/linsight/disk-pressure.env`。在线升级开始前也会先执行一次安全回收，并要求至少保留 1.5 GiB
可用空间，再创建新环境和完整回滚快照。

自动回收严格使用固定白名单：pip 安装缓存、遗留的部署上传/新环境目录、过期完整部署快照、非当前且
非上一版本的签名 Agent 制品，以及超过七天或 256 MiB 上限的 systemd 日志。升级快照始终保留
`source-previous` 指向的上一可回退版本和另一份最新恢复快照；90% 以上才额外清理可重新下载的 APT
缓存。

脚本不会扫描或删除 `/var/lib/linsight/runtime-data/events`、`delivery.sqlite3`、未 ACK 媒体、在用模型、
设备密钥或当前/上一运行版本。若白名单回收后仍高于 80%，状态记为 `STILL_HIGH` 并继续告警，不扩大
删除范围；应扩容或人工核查未知占用。每次处置回执写入
`/var/lib/linsight/disk-pressure/last-run.env`，Edge Agent 将处置前后占用、回收字节数和动作摘要随心跳
上报，平台网关卡片与详情页会显示结果。

## 故障与回退

先区分 SSH 连接、系统依赖、pip 安装、模型准备和服务切换阶段，读取对应部署日志。PyPI 不稳定时在构建机准备匹配离线依赖，不在现场反复执行全量系统升级。

恢复时沿用部署快照和既有回滚流程，保留节点身份、设备配置密钥和运行数据。发布、签名升级及回滚步骤见 [发布手册](V1_RELEASE_RUNBOOK.md)，日常故障处置见 [运维 SOP](OPERATIONS_SOP.md)。
