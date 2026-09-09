# LInsight V1.0 发布与回滚手册

## 发布判定

执行 `make release-check`。该命令先刷新前端、Python Runtime 与 Java Server 依赖审计和 SBOM，再执行完整
发布检查。只有 `overall=PASS` 才允许生产发布；
`BLOCKED_EXTERNAL` 表示工程检查通过但现场证据不完整，不能改写成“已验收”。先复制
`docs/production-acceptance.example.json` 到 `evidence/production-acceptance.json`。证据清单使用
schema 1.1，必须填写验收环境、目标硬件、发布版本和带时区生成时间；每个 `PASS` 项至少附一个
位于证据目录内的非空文件及其 SHA256。路径越界、文件缺失、hash 不匹配或证据超过 90 天都会
保持 `BLOCKED_EXTERNAL`，不能仅修改状态字段绕过门禁。

## 现场证据工作区

先在目标环境为本次发布建立一次性证据工作区。初始化命令只生成 `PENDING` 模板，并在目标文件
已存在时拒绝覆盖：

```bash
python3 scripts/production_evidence.py init \
  --directory evidence \
  --environment-name '生产验收环境名称' \
  --hardware 'CPU/GPU/内存/磁盘/网络/摄像头完整规格' \
  --software-version '不可变发布 tag 或 commit SHA'
```

现场执行六组测试，把原始日志、扫描导出、截图或录像放入 `evidence/raw/`，然后填写
`evidence/reports/` 下对应的结构化 JSON。每份报告必须保留原始附件的相对路径和 SHA256；
报告环境必须与总清单完全一致。算法报告强制覆盖 12 个预置模型和 11 类算法，逐项校验来源、
许可证、固定测试集、事件级指标、阈值、端到端时延、去重和资源占用。其余报告分别校验真实
30 分钟断网、目标路数与 API P95、生产镜像/OS/最终 Java 制品、Edge 回滚以及监控告警。

全部报告真实通过并改为 `PASS` 后组装总清单；该命令校验指标并自动写入报告哈希，任一字段、
阈值或原始附件不符合要求时不会生成可发布清单：

```bash
python3 scripts/production_evidence.py assemble --directory evidence
make production-evidence-verify
make release-check
```

证据文件中的 `PASS` 只能来自实际现场执行结果。初始化模板、自动化 fixture、本地虚拟时钟测试
和本地健康压测都不能替代生产证据。

### Runtime 现场指标采集

弱网、目标路数压测和可观测性三份报告必须附
`scripts/capture-runtime-observability.py` 生成的原始 JSON。采集器通过本机 Runtime 的鉴权接口读取
真实指标，密钥只允许由 `LINSIGHT_RUNTIME_API_KEY` 环境变量注入。`--environment-name`、
`--hardware`、`--software-version` 和 `--run-id` 必须与正在填写的结构化报告完全一致。

真实断网前先启动任务，再从边缘节点执行 30 分钟采集。网络故障必须使中心健康地址在整个采集期
不可达，但不能中断本机 Runtime；期间应持续有分析 FPS 和事件积压：

```bash
export LINSIGHT_RUNTIME_API_KEY='由密钥系统注入的节点 Runtime 密钥'
python3 scripts/capture-runtime-observability.py \
  --runtime-url http://127.0.0.1:48900 \
  --control-plane-health-url https://control.example.com/actuator/health \
  --duration-seconds 1800 --interval-seconds 10 \
  --environment-name '生产验收环境名称' \
  --hardware 'CPU/GPU/内存/磁盘/网络/摄像头完整规格' \
  --software-version '不可变发布 tag 或 commit SHA' \
  --run-id 'weak-network-field-001' \
  --output evidence/raw/weak-network-outage-runtime-series.json
```

恢复网络并等待补传完成后，以同一 `run-id` 再采集至少 60 秒。结果必须显示中心可达、事件和状态
转换队列归零、媒体文件无缺失；断网与恢复两段的 `deadLetterTransitions` 都不得高于各自首个样本：

```bash
python3 scripts/capture-runtime-observability.py \
  --runtime-url http://127.0.0.1:48900 \
  --control-plane-health-url https://control.example.com/actuator/health \
  --duration-seconds 60 --interval-seconds 10 \
  --environment-name '生产验收环境名称' \
  --hardware 'CPU/GPU/内存/磁盘/网络/摄像头完整规格' \
  --software-version '不可变发布 tag 或 commit SHA' \
  --run-id 'weak-network-field-001' \
  --output evidence/raw/weak-network-recovery-runtime-series.json
```

目标路数压测期间并行运行同一采集器，输出到
`evidence/raw/api-load-runtime-series.json`；管理 API 压测的原始报告保存为
`evidence/raw/admin-api-load-report.json`。门禁会核对采集器观测到的活跃共享流数和最低分析 FPS，
不能只在报告中手填路数。监控验收另输出 `evidence/raw/observability-runtime-series.json`，并附
`evidence/raw/observability-dashboard.png`；门禁至少验证进程、任务、流、模型和投递五组 Runtime
指标真实存在，监控平台截图与告警路由仍由现场人员复核。

每个原始文件用 `shasum -a 256 <文件>` 计算 SHA256 并填写到对应报告。采集失败、环境或
`run-id` 不一致、弱网时中心仍可达、恢复后队列不为零、压测路数/FPS 不足，都会阻止组装清单。

## Edge Agent 升级

升级包必须为 `tar.gz`，包含 `bin/edge-agent`。清单包含 `version`、包的 `sha256`，以及
`HMAC-SHA256(version + ':' + sha256)` 的 `signature`。生产签名密钥必须由密钥系统注入，
不得写入仓库或命令历史。

```bash
export PYTHONPATH="$PWD/runtime"
export LINSIGHT_AGENT_UPGRADE_SIGNING_KEY='由密钥系统注入的至少 32 字节密钥'
python3 scripts/manage-edge-release.py install \
  --root /opt/linsight-edge --package edge-agent.tar.gz --manifest manifest.json
```

安装会拒绝 hash/签名不匹配、符号链接、设备文件和路径穿越；通过后以原子符号链接切换
`current`，旧版本保存在 `previous`。服务健康检查失败时执行：

```bash
python3 scripts/manage-edge-release.py rollback --root /opt/linsight-edge
```

回滚后必须确认 Agent 心跳版本、任务状态和离线事件补传恢复。

控制台路径为“边缘计算 → 边缘节点”。先生成一次性注册令牌完成节点注册，再对在线节点下发
签名升级包；进度通过耐久命令回报并保留在“升级记录”。控制面只负责包的 SHA256、短期下载
地址和命令审计，签名真伪必须由 Edge Agent 使用本地密钥验证。离线节点允许查看历史，但不能
下发升级或回滚。

## 弱网与安全检查

Runtime 自动化包含 30 分钟虚拟时钟故障注入：每 10 秒生成事件与状态转换，期间模拟进程
重启和指数退避，恢复后校验 180 组记录恰好投递一次。该测试证明队列语义，不替代真实网络、
真实截图/录像和目标磁盘的现场验证。

发布检查器同时执行 UTF-8 完整性、源代码凭据扫描和上传内容校验回归，拒绝私钥、常见
云/GitHub 令牌、URL 内嵌凭据，以及扩展名/MIME 伪装的模型、图片、视频和升级包。
`make dependency-audit` 使用官方 npm registry、`pip-audit`、CycloneDX 与 OSV 生成
`artifacts/security/dependency-audit-latest.json` 和 `artifacts/security/linsight-server-bom.cdx.json`；
报告与 `pnpm-lock.yaml`、`uv.lock`、全部 Maven POM、安全回补源文件及风险接受清单的 SHA256
绑定，超过 7 天或任一输入变化都会阻断发布。无修复版本的 WangEditor 4 已从
生产依赖链移除，表单设计器使用项目的 TinyMCE 规则，并保留只输出纯文本的兼容回退组件。

Java Server 当前 302 个运行时组件中无未接受漏洞。OSV 仍报告 2 项已限时接受风险：
`dynamic-datasource-spring 4.5.0` 的中危 SpEL 注入已回补上游修复，并由源码门禁禁止 `@DS`
表达式；`xxl-job-core 2.4.2` 的低危项仅涉及未打包的示例 `httpJobHandler`，源码门禁禁止引入。
风险清单位于 `docs/security/dependency-risk-acceptance.json`，到期后自动阻断；高危和严重漏洞
即使写入清单也不能被接受。

本地依赖报告不替代目标制品扫描。生产容器镜像、操作系统包和最终目标 Java 制品仍需在实际发布
镜像上扫描，并作为 `securityScan` 外部证据提交。

工程环境可运行 `scripts/admin-api-load.py` 对算法、摄像头、模型、任务、事件和节点管理 API
进行带鉴权并发压测。访问令牌只能通过 `LINSIGHT_LOAD_ACCESS_TOKEN` 环境变量传入，报告默认写入
`artifacts/load/admin-api-local.json`。本地报告只用于回归，不得作为目标硬件的 `apiLoadP95` 证据。

## 数据库与应用回滚

数据库迁移只允许新增文件，不修改已登记校验和。每个迁移头部均包含回滚说明；先停止新增写入，
再按版本倒序执行人工回滚并恢复上一个应用制品。事件和媒体表的删除操作必须先做备份与抽样恢复验证。

## 当前外部阻断项

- 12 个预置资产的真实权重、固定来源、许可证和商业再分发结论。
- 11 类算法固定验收集、真实 RTSP/ONVIF 设备与目标边缘硬件。
- 30 分钟真实弱网故障注入、目标并发路数、生产镜像/OS/Java 制品安全扫描报告。

这些阻断项不会影响契约测试，但会使生产门禁保持 `BLOCKED_EXTERNAL`。任意非空文件不再能
通过门禁；每类验收必须提供唯一结构化报告、原始附件哈希、环境/版本绑定和可计算指标。

平台部署前执行 `make runtime-source-fingerprint`，保存输出中的确定性源码 SHA256；部署后必须在
网关 `/opt/linsight/runtime` 对同一文件集合复算并匹配。正式证据中的 `softwareVersion` 应绑定
平台部署编号和该 SHA256，不能只使用可重复的版本显示字符串或“部署成功”状态。


## 在线升级与生命周期操作（2026-09-06）

节点“更多 → 在线升级（重新部署）”复用 SSH 预检与主机指纹确认。保留节点编码、节点身份凭据、
模型和事件数据，重新安装控制面当前 Runtime/Agent 源码。此操作会短暂中断该节点的推理与预览。
成功必须匹配 `source-<包 SHA256 前 12 位>` 版本且收到安装后新鲜心跳；仅有旧进程心跳不算成功。
部署抽屉每 1.5 秒刷新受限的日志尾部，关闭即停止；读取失败保留已收到的输出并自动重试。
老部署没有原始输出时明确显示不可回溯，不再一直显示等待。

SSH 部署安装的 systemd Agent 入口现在使用 release launcher。签名发布环境应由密钥系统在
`/etc/linsight/agent-upgrade.env` 注入 `LINSIGHT_AGENT_UPGRADE_SIGNING_KEY`（至少 32 字节），
文件由 root 持有且权限 0600；这个配置不由控制台返回或自动生成，重部署保留它。
签名包安装到 `/var/lib/linsight/edge-agent/releases`，校验后切换 `current`。
安装/回滚命令成功表示目录已切换，随后执行“重启节点”并核对心跳版本才算启用完成。
在线重部署恢复源码启动入口，已有签名 current 保存为 previous，供后续受控回滚使用。

重启/关机通过既有耐久命令提交，Agent 原子发布固定动作，由 systemd 延迟 15 秒执行。
命令完成表示请求已提交，不等于已证明主机关机；关机应结合离线状态，重启应结合离线和恢复心跳验收。
持久化命令回执与生命周期去重记录位于 Runtime 数据目录，丢失应答或 Agent 重启后重复命令不会再次
触发主机动作或反复切换回滚。进程在发布请求前崩溃的极小不确定窗口采用不重复执行策略，需要人工
核对主机状态后创建新的操作，不能盲目重放。

删除仅允许离线、无关联任务、无活动命令的节点；逻辑删除后原凭据失效，保留部署/升级/日志审计。
关机会要求现场开机恢复，因此日常回归使用隔离节点验证固定动作与命令契约，不关闭业务现场网关。
