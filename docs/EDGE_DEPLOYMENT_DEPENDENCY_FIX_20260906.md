# 边缘部署失败修复与现场验证（2026-09-06）

## 已确认的根因

现场节点：`rk3566-field-001`（192.168.2.17，Ubuntu 24.04 / aarch64）。部署 #18 停在系统依赖阶段，尚未切换服务。

- `curl`、`libcurl4t64` 都是 `hold ok installed`，已安装版本 `8.5.0-2ubuntu10.6`，软件源候选版本 `8.5.0-2ubuntu10.13`。
- 旧脚本只把 `install ok installed` 算作已安装，因此错误地将厂商锁定的可用包当作缺失包。
- 随后执行整组 `apt-get install`，尝试更新 curl，但其严格依赖版本与被锁定的 libcurl 冲突。只读 APT 模拟已在现场复现：`curl : Depends: libcurl4t64 (= 8.5.0-2ubuntu10.13) but 8.5.0-2ubuntu10.6 is to be installed`。
- `-qq` 隐藏具体求解过程；SSH 异常摘要截取开头 500 字，使页面出现进度标记而非实际原因。
- Python 3.12.3、对应 venv 和 FFmpeg 均已可用。不是 SSH 认证故障，也不是 Python 必须整体升级。

## 修复行为

1. 系统依赖通过真实能力检查：创建独立 venv 并验证 pip，检查 FFmpeg、curl 和 CA。全部可用时不访问 APT。
2. 确有缺失时仅安装对应项，venv 使用实际 Python 小版本包，不同时请求通用元包。APT 有锁等待、网络超时与有限重试；先模拟求解，再安装。禁止移除包、解除厂商 hold 或整机系统升级。
3. 保留完整 APT / pip 输出，以 `LINSIGHT_ERROR` 给出明确失败摘要。SSH 合并 stderr/stdout，避免错误与进度乱序。
4. 所有依赖准备与导入检查都在停止旧服务之前完成；切换仍保留快照和回滚看门狗。成功必须同时满足目标版本、新鲜心跳及 `runtimeStatus=UP`。
5. 现场完整 venv 创建实测约 19.7 秒；预检不再重复安装 pip，轻量隔离环境 / ensurepip 检查实测约 0.74 秒。安装阶段保留完整验证。
6. 节点菜单缩短为“操作记录 / 在线升级 / 部署回滚 / 上传升级包 / Agent 回滚”；风险说明仍在确认流程中。
7. 部署记录恢复卡片布局，仅展示最新 50 条；列表不拉 SSH 正文，点击详情再加载。活动记录才轮询，关闭/返回使过期请求失效。
8. 现场 #19 越过 APT 后，PyPI 多次断开连接并返回截断 JSON 索引，重试仍复现。已主动终止其安装进程组（未进入服务切换），保留失败记录与日志，改用离线 wheel 部署。
9. 新增构建端离线依赖准备脚本，按 `pyproject.toml SHA256 / 架构 / Python 小版本` 缓存不可变依赖及逐文件 SHA256。控制面校验后随源码打包；网关用 `PIP_NO_INDEX=1` 安装，包含构建依赖，不再访问 PyPI。清单错误或文件被篡改时拒绝打包，不静默回退。未准备相应平台包的环境仍支持在线安装，预检明确提示。

### 发布时准备离线依赖

```bash
uv run --with pip --no-project python scripts/prepare-node-wheelhouse.py --arch aarch64 --python-version 3.12
```

需在能稳定访问 PyPI 的构建/控制面主机执行；也可用已安装 pip 的 Python 3.12+ 直接执行。当前目标的 47 个 wheel 共约 91 MiB，已准备好，后续同依赖契约的源码升级自动复用。支持为 x86_64 或 Python 3.13 单独准备；依赖契约变化必须重新准备，不能复用旧目录。wheel 集合进入部署包 SHA256，所以依赖变化同样会改变目标版本。制品应随 Runtime 发布目录一起部署到控制面，不依赖 Git 跟踪二进制缓存。

## 验证

- 真实网关修复脚本 `check` 模式通过，输出 `Python venv/pip、FFmpeg、curl、CA 均可用，跳过 APT`，未修改系统包。
- 隔离容器 5 项故障注入通过：可用 hold 包跳过 APT、只补指定小版本 venv、依赖冲突不安装且保留详细原因、禁止自动安装时无变更退出、软件源失败停止安装。
- Java 150 项测试及 Maven reactor 构建通过；包含 wheel 目标匹配、损坏/路径穿越拒绝、制品入包与版本影响。前端类型检查、生产构建、4 项表单生命周期测试通过。
- 真实 Chrome / Vben、隔离业务响应回归通过：卡片 50 条及请求上限、详情 SSH 日志、新日志增量拉取、历史页不重复刷新。
- 现场真实在线升级验收结果见下方后续记录；不以 Mock 或构建成功代替升级成功。

## 现场成功验收

- 记录 **#20**：2026-09-06 11:45:12 开始，11:53:00 完成，`SUCCEEDED / COMPLETED / 100%`。
- 保留节点 ID `1` 与编码 `rk3566-field-001`；版本从 `0.1.0` 升级为 **`source-25b923f4846d`**。目标版本、实际版本与本轮新鲜健康心跳一致。
- SSH 持久化日志 `COMPLETE`，10,317 字符；包含“跳过 APT”“使用随包离线依赖，不访问 PyPI”“No broken requirements found”及提交回滚快照的确认。
- 升级前 Runtime 虽然进程存在，但监听队列堵塞，健康请求超时。升级后 Runtime 与 Agent 均 active，`/v1/health` 返回 `UP`，后续心跳持续上报 `runtimeStatus=UP`。
- 完整原部署快照保留于 `/var/lib/linsight-deployments/20`，健康确认后提交；`source-previous` 指向该快照。没有执行主机关机、重启或删除节点。
- 收尾重启最新版控制面后再次预检通过：当前版本一致、venv 可用、离线依赖就绪、可回滚版本 `0.1.0`，可用磁盘 2,760 MiB。11:55:29 的后续心跳仍为 `Runtime=UP`；厂商 curl/libcurl 版本与 hold 状态保持不变。
- 菜单、最新 50 条卡片记录、真实 SSH 详情再次经 Chrome 验证；截图在 `artifacts/node-menu-live-20260906.png`、`node-history-live-20260906.png`、`node-detail-live-20260906.png`。
- 收尾进一步为导入检查、每次 HTTP 健康检查增加超时，并将启动等待改为明确的探测日志；Java 150 项测试及构建再次通过。此项是等待边界收紧，不改变已验收的 Runtime/Agent 包和目标版本。

本轮真实验收覆盖该 Ubuntu 24.04 / ARM64 / Python 3.12 节点；其他平台需准备对应 wheel 制品。完整硬件回滚未额外触发，回滚脚本的故障恢复、重复执行及互斥在隔离容器中验证通过。

## 2026-09-09：Python / venv 版本冲突自动处理

新节点 `rk3566-edge-01` 的部署 #41（192.168.2.25）失败于系统依赖阶段：
`python3.12-venv` 要求 `3.12.3-1ubuntu0.16`，求解器却选择 Python `3.12.3-1ubuntu0.8`。
这不是模型依赖报错，也不能仅凭 APT 的通用 held-broken 提示判断某个包被手动锁定。

`deployment-dependencies.sh` 现在在刷新索引后按以下顺序求解：

1. 检查 dpkg 是否有未完成配置；完整读取 hold 列表，包含传递依赖与带架构后缀的包。
2. 若缺少 venv，确认实际 `python3` 解释器归对应发行版包所有，读取已安装的完整版本。
3. 优先从现有软件源寻找相同版本的 venv，并确认 APT pin 为正；有可行方案则不升级解释器。
4. 同版本不可用或求解不安全时，仅考虑当前 Python 小版本的配套候选版本：解释器、minimal、
   stdlib、venv 和已经安装的共享库。所有候选版本必须一致且可从当前源下载；不降级、不切换 Python 小版本。
5. 每个方案先使用与执行相同的 `--no-install-recommends` 条件模拟。逐项检查安装动作，
   拒绝删除包、降级、修改任何 hold 包或变更缺失项/Python 配套包之外的已安装组件。
6. 按已校验模拟结果固定每个待安装包的版本后执行；之后重新创建 venv、验证 pip 和 FFmpeg 等能力。
   APT 返回成功不能代替能力验证，失败时不会进入后续服务切换。

不会自动改写软件源或 APT pin、解除 hold、选择被非正优先级禁止的版本、执行全系统升级或整机依赖修复。
缺少配套版本时，错误明确指出具体包及软件源/pin 不一致，并输出完整锁定列表和相关版本策略供排查。
特定版本选择与模拟安装的语义依据 [Ubuntu apt-get 手册](https://manpages.ubuntu.com/manpages/noble/man8/apt-get.8.html)。

隔离容器测试命令（不访问网络，不操作现场节点）：

```bash
docker run --rm --network none -e LINSIGHT_ISOLATED_DEPENDENCY_TEST=1 \
  -v "$PWD/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/resources/node/deployment-dependencies.sh:/dependencies.sh:ro" \
  -v "$PWD/scripts/tests/node-deployment-dependencies.sh:/tests.sh:ro" \
  python:3.12-slim-bookworm bash /tests.sh
```

15 项隔离故障注入通过，覆盖已有能力跳过、匹配旧版 venv、同小版本配套升级与 FFmpeg 合并安装、
源/pin 不一致、移除/降级/无关包变更拒绝、无效模拟版本、传递依赖 hold、非发行版 Python、网络失败、禁用安装及安装后能力验证。
这些是脚本行为回归，不代替 #41 节点的真实部署验收。本次未对现场节点执行安装或重启。
发布时需让控制面加载新的脚本资源，再从节点部署入口重试；无需先手动补装 Python/venv。

## 2026-09-09：部署 #44 的锁定 Python / ensurepip 缺失修复

#44 的完整日志确认：现有 Python `3.12.3-1ubuntu0.8` 可以运行，但没有 ensurepip；
当前源已无同版本 venv，升级到 `.16` 又会修改 5 个 hold 的 Python 包。
前面的 APT 安全检查正确阻止了升级，但尚不能完成该节点的安装。

现增加平台随包的应用环境引导，初装与后续模型依赖准备共用
`runtime/ai_runtime/app/core/environment.py`：

1. 控制面随 Runtime 源码携带官方 `pip-25.3-py3-none-any.whl`，固定 SHA256 和来源、许可说明。
   即使没有完整离线 wheelhouse，也必须携带这个小型引导制品。
2. 先校验完整 Runtime ZIP 的 SHA256 并解压至 staging，再检查依赖，保证引导代码和制品已经就绪。
3. 标准 venv/pip 不可用时，使用 `venv.EnvBuilder(with_pip=False)` 创建临时隔离环境，
   校验并从随包 wheel 离线安装 pip，实测成功后不再把 `python3.12-venv` 交给 APT。
4. APT 只处理剩余缺失的 FFmpeg/curl/CA；模拟检查、hold/降级/删除/无关升级保护保持不变。
5. 同一引导器创建 `/opt/linsight/venv.new`；模型依赖 profile 也使用它，包括失败后的部分环境重试。
   引导过程屏蔽外部 Python/pip 配置，不访问索引、不写入系统 Python、不解除任何 hold。

这是**复用原系统解释器、隔离应用包**，不是另装一套系统 Python。
其前提是现有受支持的 Python 能执行标准库 venv 的无 pip 创建流程；Python 本身不可用或损坏不在本次修复范围内。
完整 Runtime 和模型依赖仍按既有离线 wheelhouse / 在线下载流程安装，不能把 pip 引导离线等同于所有模型均可离线部署。
实现依据：[Python venv 的 without-pip 语义](https://docs.python.org/3.12/library/venv.html)。

真实 Python 的断网容器回归（容器内移走 ensurepip，APT 为故障注入桩，不操作现场节点）：

```bash
docker run --rm --network none -e LINSIGHT_ISOLATED_DEPENDENCY_TEST=1 \
  -v "$PWD/runtime:/runtime:ro" \
  -v "$PWD/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/resources/node/deployment-dependencies.sh:/dependencies.sh:ro" \
  -v "$PWD/scripts/tests/node-deployment-bootstrap.sh:/tests.sh:ro" \
  python:3.12-slim-bookworm bash /tests.sh
```

覆盖禁用系统依赖安装、5 个 Python hold 下仅安装 FFmpeg、应用/嵌套模型环境 pip 实测、
重复检查跳过 APT、引导器缺失停止及非 Python hold 保护。另有哈希损坏、缺失制品、
禁止系统目录写入、外部 pip 配置隔离和部分环境重试测试。

发布需同时更新后端和 Runtime 源目录（包括 bootstrap wheel）；本地标准 `make backend` 会编译并启动控制面。
随后通过节点部署入口重试。不能只刷新前端，也不要手动 unhold 或修改系统 Python。
本节工程测试不代表 #44 节点现场部署成功；本次未重启控制面或在节点安装服务。

本次验证结果：15 项原 APT 故障注入 + 6 项断网真实 Python 引导场景通过；
Python 环境/模型/网关测试 23 项、升级/激活/回滚相关测试 11 项通过，Ruff 与 Bash 语法检查通过。
Java 节点相关测试 71 项通过，JDK 17 的 `linsight-server -am package` 成功。
实际构建的 Runtime wheel 已检查包含 `environment.py` 和固定版本 pip wheel。
