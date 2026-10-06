# 盒子应用升级与既有设备迁移

## 范围与工作方式

本功能升级 Runtime、Edge Agent、盒子管理网页、独立 Python 3.12 和随包 wheel。
发布物为 Ed25519 签名的 `.lup` 文件，全程离线安装。系统镜像、内核、NPU 驱动、
FFmpeg/MPP/RGA/GStreamer 系统组件不包含在应用包中；它们仍需对应设备的系统维护方案。

程序及依赖安装到 `/opt/linsight/releases/<版本>-<摘要前12位>`，独立安装器位于
`/opt/linsight-updater`，通过 `current` / `previous` 指针选择版本。每次先验签、
检查机型/架构/glibc/空间、安装依赖及执行 import 检查，再等待明确的安装操作。
准备阶段旧服务继续运行；切换阶段会中断识别、预览和本地页面连接。

健康检查核对进程的真实版本、本机 Runtime、管理网页、原任务的启停状态及配置版本；
原本正在处理帧的任务还必须处理新帧。检查失败自动恢复旧程序和依赖。任务日志先落盘，
安装器重启会先恢复旧指针再启动业务服务。中心平台断线不会使已经提交的本机升级失效。

配置、模型、身份、密钥和事件保持在原数据目录，不执行数据库快照恢复。首版仅支持
**数据格式向后兼容**的应用版本。发布者必须完成兼容性回归后才能签发升级包。

## 从平台生成升级包（常用入口）

入口：**边缘计算 → 边缘节点 → 盒子升级包 → 生成升级包**，需要 `ai-video:node:upgrade` 权限。
填写版本和更新说明后提交。平台使用统一发布配置自动完成程序、网页、依赖打包和签名校验，
记录“排队中 → 构建中 → 保存制品 → 已完成 / 失败”；关闭页面不影响任务。
完成后可下载 `.lup`，详情中另可下载首次迁移工具和发布公钥，并核对包、引导工具和程序摘要。
生成包后，按照下文“日常升级入口”安装；生成动作本身不会连接或升级任何盒子。
RK3566 / RK3568 / RK3588 共用一份 ARM64 应用包，适用设备记录在签名清单中。盒子安装前
检查架构、型号、glibc、空间和数据结构版本，不满足要求时拒绝安装。模型文件沿用设备已有版本。

### 平台部署人员的一次性准备

1. 先执行 `V202610062300__node_application_release.sql` 数据库迁移，再发布后端及前端。
2. 在服务器部署受信的 `scripts/build-box-release.py` 及完整 `runtime/` 程序制品。
   构建器的 Python 环境需要 `cryptography` 和网页制品校验代码的依赖。
   每次修改程序后，应将经测试的 Runtime、Edge Agent、盒子网页制品一起发布到该目录；
   前端改动先生成 `runtime/gateway-console`，依赖改动先更新对应架构的固定 wheelhouse。
   构建期间该发布目录应保持只读、稳定，建议按发布版本部署目录，再变更平台配置。
3. 按 [`application-release.example.yaml`](../deploy/application-release/application-release.example.yaml)
   准备一份 ARM64 发布配置，包含支持设备列表、glibc 下限、固定 Python 摘要、离线依赖目录和 Ed25519 密钥。
   这些是平台部署职责，不由生成升级包的用户填写；浏览器不能提交命令、路径、私钥或任意 Git 地址。
   私钥仅允许构建服务账号读取（如 `0600`），独立保存备份；不要使用模拟器密钥发布现场包。
4. 基础设施文件存储必须配置为**私有 S3/MinIO**。内部 `endpoint` 必须从服务器可达，
   `domain` 必须从用户浏览器可达。大文件通过现有 S3 客户端流式写入内部 endpoint；
   下载前核验租户和权限，生成 60 秒有效链接。建议为该平台使用独立私有桶与最小权限账号。
   默认使用主文件存储；也可设置 `node-application-release.storage-config-id` 为已有私有文件配置的 ID，
   为升级包单独选择存储及下载域名。指定 ID 无效时构建失败，不回退到其他存储。
5. 将配置的 `enabled` 改为 `true`，通过 `SPRING_CONFIG_ADDITIONAL_LOCATION` 加载并重启平台。
   多实例必须共享相同构建配置和制品；每实例同时运行 1 个任务，任务先以 MySQL 队列持久保存。
   临时目录至少保留 2 GiB 可用空间；单包上限 2 GiB，构建限时 20 分钟。

### 统一应用包与旧配置兼容

当前程序和依赖共用一套 ARM64 制品，示例只配置一个 `profiles.arm64`，其 `devices` 为
`[rk3566, rk3568, rk3588]`。同一个包包含一份 Runtime、Agent、管理网页、Python 和离线依赖，
型号列表用于安装时检查；它不代表每个型号有一份不同源码，也不升级系统驱动或替换设备已有模型。
不同型号的实际系统和 NPU/视频驱动仍须验收，不能仅降低 `min-glibc` 声明来兼容旧系统。

- 网页通过 `/configuration` 读取默认包的只读名称、架构、适用设备和就绪状态，创建请求只需版本、
  更新说明和幂等编号。数据格式固定为当前受支持的 schema 1；发布者仍负责保持业务数据向后兼容，
  安装器拒绝不支持的 schema。取消用户勾选并不意味着自动证明任意代码修改都兼容。
- 服务器 `default-profile: arm64` 指定新任务的默认配置；已有单配置部署可自动沿用，多个配置而未指定
  默认项时不猜测。旧 `profiles`、创建请求里的 `profileId` / `backwardCompatible` 保留兼容，
  历史包继续下载，失败重试使用原任务配置；保留旧配置可避免改默认包后无法重试历史任务。
- 本机 `local` profile 自动加载仓库根目录的忽略文件 `var/application-release-local.yaml`，
  在仓库根目录、`backend/` 或 `backend/linsight-server/` 启动均可；部署人员调整后重启后端生效。
  正式服务器使用 `SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/linsight/application-release.yaml`。
- 本机默认统一包使用测试密钥，额外包含 `generic` 以验证 Linux 模拟盒子；页面明确标为本机测试。
  生产模板不包含 `generic`，正式发布使用已受信分发的正式公钥和经过目标设备验收的制品。

### 发布约束和故障处理

- 同一租户、发布配置、版本只有一条发布记录；重复提交相同请求不会重复构建，成功版本不能覆盖。
- 构建器核对 Python 与 wheel 摘要、网页制品，产包后使用设备相同的校验器重新验签和逐文件校验；
  引导工具从这份已校验包提取源码生成，避免并发修改源码导致两者不一致。
- 失败任务可以重试，保留版本、说明和原构建配置，增加尝试次数；配置变更时需恢复原配置或使用新版本。
- 构建结果与制品存储均完成才会显示成功。每 10 秒续租，租约为 120 秒，独立调度器维护租约。
  进程中断后，过期任务标记失败；排队任务继续执行。过期工作线程不能发布结果。
- 制品按 `node-releases/<租户>/<任务>/<尝试>/<随机制品组 ID>` 保存，避免共用桶的不同数据库任务编号相同而覆盖文件。
  失败尝试可能在私有桶内留下未引用对象，可按租户、任务及尝试前缀排查；
  中断进程可能在临时目录留下文件，确认对应任务已失败后可清理。平台不会自动删除历史成功制品。
- 发布程序需要保持数据向后兼容。自动打包不会替代真机回归、签名公钥的受信分发及首次迁移验收。

## 命令行生成发布包（发布流水线或排障）

1. 用项目要求的 Node/pnpm 运行 `bash scripts/build-gateway-console.sh`。
2. 准备与 `runtime/pyproject.toml` SHA256、CPU 架构及 Python 3.12 一致的离线 wheelhouse。
   沿用现有 `runtime/deployment-wheels/<pyproject摘要>/<架构>-cp312/manifest.json` 格式，
   每个 wheel 都固定 SHA256；不接受现场联网解析依赖。
3. 使用经过确认的独立 CPython 包及固定 SHA256。RKNN 盒子的 wheelhouse 必须含匹配的
   RKNNLite 及所需 Python 依赖。Linux `generic` 包用于模拟器，不能代替 RKNN 机型发布。
4. 发布私钥保留在发布环境；只将公钥交给设备。首次可在受控环境生成，例如：

```bash
umask 077
openssl genpkey -algorithm ED25519 -out release.key
openssl pkey -in release.key -pubout -out release.pem
```

```bash
runtime/.venv/bin/python scripts/build-box-release.py \
  --version 1.0.0 --arch aarch64 --devices rk3566 rk3568 \
  --python /absolute/path/cpython-install_only.tar.gz \
  --python-sha256 <经确认的64位摘要> \
  --wheels /absolute/path/aarch64-cp312 \
  --key-id production-2026 --signing-key /secure/path/release.key \
  --backward-compatible --notes /absolute/path/release-notes.txt \
  --output /absolute/path/release-1.0.0
```

输出 `.lup`、首次迁移用 `linsight-bootstrap.pyz`、`release-public.pem` 及 SHA256 信息。
可传 `--result-file /absolute/path/result.json` 输出机器可读构建结果，供平台和流水线使用。
`--backward-compatible` 是发布人的兼容声明，不会自动证明数据兼容。
同一版本号不能对应不同内容；发布工具拒绝覆盖已有包。

## 已生产设备：首次接入升级能力

首次需要一个受信 SSH 或本地终端维护窗口。旧设备还没有安装器和新页面，不能仅复制
一个包就获得执行权限。先选一台维护窗口可控、具备人工恢复手段的设备做迁移验收。

将已核对摘要的 `linsight-bootstrap.pyz`、对应 `.lup`、通过独立受信渠道分发的公钥
复制到设备。**公钥不能从未知升级包中自行取出并信任**。

```bash
sudo /opt/linsight/venv/bin/python /path/linsight-bootstrap.pyz \
  --bundle /path/linsight-box-1.0.0-aarch64.lup \
  --public-key /path/release.pem --key-id production-2026 --check
```

预检只接受仓库标准部署目录、相同服务用户、仍正常运行的 Runtime/Agent、稳定的绝对
数据/身份路径；拒绝旧独立 Agent 签名版本和未完成验收的 SSH 部署回滚计时器。
自定义布局检查失败时，应先完成适配，不能跳过检查强行切换。

通过后执行相同命令，去掉 `--check`。首次迁移：

- 保存旧 Runtime 和旧 venv 为 `legacy` 回退基线；保留原服务 EnvironmentFile 和用户。
- 新增独立安装器、公钥、启动包装器、systemd drop-in；迁移过程不主动重启旧应用。
- 安装器单独持有自己的 Python/依赖；应用包不会更新正在负责回退的安装器。
- 首次迁移中断时，用**原包、原公钥及原迁移程序**重试；已完成设备拒绝重复迁移。

随后首次应用升级：

```bash
sudo linsight-upgrade check /path/linsight-box-1.0.0-aarch64.lup
sudo linsight-upgrade install /path/linsight-box-1.0.0-aarch64.lup
sudo linsight-upgrade status
```

`check` 会校验并准备一个新目录，需要磁盘空间但不切换服务；`install` 会执行切换。
首次新应用安装完成后，本地管理页面才具备应用升级入口。
已迁移设备的旧覆盖式 SSH 部署、旧 Agent 单独升级会被拒绝，后续统一使用应用包。

## 日常升级入口

| 入口 | 操作 |
| --- | --- |
| 复制到盒子 | `sudo linsight-upgrade check <包>`；确认维护窗口后 `install <包>` |
| 盒子本地网页 | 登录 → 应用升级 → 上传 `.lup` → 等待“准备完成” → 安装新版本 |
| 中心平台 | 边缘节点详情 → 应用升级；需 `ai-video:node:upgrade` 权限和在线网关隧道 |

网页通过现有鉴权通道分块传输，每块 256 KiB；同一页面内网络中断可重新选择同一文件续传。
刷新/离开页面后可重新上传，已落盘的安装任务继续执行。上传完毕只触发预检，安装有单独确认。
设备接收包走现有带租户校验的分块通道。生成页提供的短时下载链接供操作人员下载发布物。

```bash
sudo linsight-upgrade rollback
```

手动回退同样检查本机健康；失败会尝试恢复回退前的应用。重复的任务 ID 不会重复切换。
保留多个已准备版本，首版不自动删除版本目录；空间不足会拒绝新包。不能手工删除
`current`、`previous` 指向的目录、`legacy` 基线或 `/opt/linsight-updater`。

## 排障与恢复

```bash
sudo linsight-upgrade status
sudo journalctl -u linsight-app-updater -u linsight-ai-runtime -u linsight-edge-agent -n 100
sudo cat /var/lib/linsight-updater/job.json
```

安装详细日志在 root 专用 `/var/lib/linsight-updater/installer.log`，首次迁移日志为
`bootstrap.log`；各次任务状态在 `history/`。对外错误不包含子进程日志、设备密码或 API key。
切换与旧部署共用部署锁，并等待已有配置写入结束。另保留 16 MiB 日志应急空间，
应对切换期间其他进程占满磁盘；这不能替代设备的磁盘健康管理。

`FAILED`：原版本未切换，按错误修复后重新上传；`ROLLED_BACK`：已经恢复旧版本；
`RECOVERY_FAILED`：恢复检查未通过，需要维护人员核对磁盘、服务和摄像头，不应连续批量重试。
安装器本身升级、公钥轮换、非兼容数据迁移需单独维护方案，不通过首版普通应用包隐式执行。

## 验证范围

本轮已执行的检查和具体限制见 [本机验证记录](BOX_APPLICATION_UPGRADE_VERIFICATION.md)。

电脑模拟器见 [模拟盒子说明](../deploy/box-simulator/README.md)。模拟器用于验证真实 Linux
进程、systemd、离线依赖、页面、持久任务和故障恢复。正式下发前仍需在目标机型验证
RKNN 推理、视频硬解、实际摄像头任务恢复、存储介质断电行为及版本兼容性。
