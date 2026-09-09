# 边缘节点模块审查记录

日期：2026-09-06。范围：新节点部署、在线重部署、签名升级/回滚、节点运维、运行日志、部署历史。

后续修复及验证见 [EDGE_NODE_MODULE_FIXES_20260906.md](EDGE_NODE_MODULE_FIXES_20260906.md)。下文保留审查当时的证据与问题，源码行号可能已随修复变化。

本轮为审查，没有修改业务代码，也没有执行现场升级、重启、关机或删除。结论来自当前源码、只读数据库查询及隔离复现。截图中 `preflight` 的 `code=0`、`supported=true` 证明本次 SSH 认证与环境探测成功；此前将问题归因为密码错误的判断不成立。

## 核心证据

- 数据库 `ai_node_deployment` 当前有 16 条未删除记录，16 条 `output_log` 均为 NULL；最新为 #16，创建于 2026-09-04 17:33:37。当前没有新版本代码生成的部署记录可用于证明现场 SSH 输出闭环。
- 隔离复现从当前 `deployment-drawer.vue` 提取原始 `runPreflight` / `startDeployment` 函数，使用实际 `FormApi` 与 `StateHandler` 等待方法，模拟成功 HTTP 响应和表单挂载状态。结果：

```text
Existing-node preflight after success response:
  responseReceived=true, step=0, locked=true
Create-deployment after returned ID:
  deploymentId=999, step=2, locked=true, pollsStarted=0
```

这是异步控制流的隔离复现，不是现场 SSH 部署验收。运行脚本从标准输入执行，没有增加业务测试文件。尝试通过 Vite SSR 加载整套表单依赖时遇到模块解析问题，最终使用 TypeScript 转译执行上述实际方法完成复现。

## 问题与修复方向

### F01 · P1：已有节点预检必然等待未挂载表单

位置：[deployment-drawer.vue:177](/Users/mateng/Documents/VibeCodingProjects/linsight/frontend/apps/web-antd/src/views/ai-video/node/modules/deployment-drawer.vue:177)、[form-api.ts:519](/Users/mateng/Documents/VibeCodingProjects/linsight/frontend/packages/@core/ui-kit/form-ui/src/form-api.ts:519)。

当响应包含 `existingNodeCode` 时，代码先 `await deploymentFormApi.setValues(...)`，之后才设置 `currentStep=1`。但 `DeploymentForm` 位于第二步的 `v-if` 内，必须先切换步骤才会挂载；`setValues` 又会等待挂载。因此 HTTP 已完成，流程仍永远到不了 `finally` 中的解锁。截图中的节点恰好满足该条件。

修复：把向导状态与表单实例生命周期分开。可以保持表单挂载并切换可见性，或先完成步骤切换/挂载再赋值；所有初始化、预检、关闭清理需遵守同一策略。单纯延长请求超时不能修复此问题。

### F02 · P1：部署创建成功后，清空旧表单再次卡死，日志轮询未启动

位置：[deployment-drawer.vue:224](/Users/mateng/Documents/VibeCodingProjects/linsight/frontend/apps/web-antd/src/views/ai-video/node/modules/deployment-drawer.vue:224)。

进入第二步时 `ConnectionForm` 已被 `v-if` 卸载。创建接口成功后，代码等待这个旧表单的 `setFieldValue('password', '')`，随后才调用 `schedulePoll()` 和解锁。结果是后台可能已经部署，页面却一直显示等待，无法更新进度和日志。`reset()` 及 `onOpenChange()` 也同时操作可能尚未挂载的两个表单，存在同类悬挂。

修复：凭据清理使用独立的临时状态和明确的表单生命周期，不能阻塞已创建任务的轮询；取得任务 ID 后立刻进入可恢复的任务详情。第二步应能返回修改连接配置，失败结果应能用新凭据重试，避免整个页面刷新。

### F03 · P1：在线重部署失败没有恢复路径，菜单回滚也无法恢复它

位置：[NodeDeploymentRunner.java:319](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/service/node/NodeDeploymentRunner.java:319)、[manager.py:69](/Users/mateng/Documents/VibeCodingProjects/linsight/runtime/edge_agent/app/upgrade/manager.py:69)。

安装脚本停止旧服务，把源码与虚拟环境分别移到 `/opt/linsight/runtime.previous`、`venv.previous`，随后覆盖环境配置和 systemd 文件。切换后健康检查或注册失败时，脚本直接退出，Java 只把记录标记为 FAILED，没有恢复旧目录、配置和服务的操作。

“回滚版本”调用的是签名升级管理器，仅切换 `/var/lib/linsight/edge-agent/current` 与 `previous` 链接。它不会恢复上述源码/虚拟环境，也不会恢复 Runtime 或旧配置。仅做过在线重部署的节点可能根本没有可用的签名版本链接。

修复：给在线重部署建立完整的版本快照和失败恢复流程，覆盖代码、依赖、配置、启动入口；明确“回滚 Agent”与“回滚整套部署”的范围，按钮依据实际可回滚能力启用。验收必须包括切换后启动失败与回滚后新鲜心跳。

### F04 · P1：部署、签名升级和主机操作缺少统一互斥

位置：[NodeDeploymentServiceImpl.java:57](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/service/node/NodeDeploymentServiceImpl.java:57)、[NodeLifecycleServiceImpl.java:55](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/service/node/NodeLifecycleServiceImpl.java:55)、[NodeUpgradeServiceImpl.java:141](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/service/node/NodeUpgradeServiceImpl.java:141)。

创建部署未检查同一主机是否已有活动部署；重启/关机只检查命令表，不检查 SSH 部署；签名升级只检查最近升级记录。在线重部署执行时仍可下发重启/关机，签名升级也可能与源码替换交叉进行。并发执行的部署还共用固定的 `runtime.new`、`venv.new` 和 previous 路径。

修复：在 node 领域建立以租户、节点/已验证主机为范围的操作占用与条件状态迁移；创建端提供幂等键，前端展示占用原因，服务端原子拒绝冲突操作。不能仅靠禁用浏览器按钮。

### F05 · P1：部署记录持久化了，执行任务却只存在内存中

位置：[NodeDeploymentServiceImpl.java:90](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/service/node/NodeDeploymentServiceImpl.java:90)、[NodeDeploymentRunner.java:48](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/service/node/NodeDeploymentRunner.java:48)、[NodeDeploymentExecutorConfiguration.java:12](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/config/NodeDeploymentExecutorConfiguration.java:12)。

数据库插入 QUEUED 后直接调用 `@Async`，线程池容量为 1 个核心线程、最多 2 个线程、20 个排队任务。队列拒绝或控制面重启没有对应的部署恢复/终止扫描；已写入的 QUEUED/RUNNING 记录可长期保留，页面随之一直轮询。bootstrap token 在排队前生成且 30 分钟到期，也可能等待执行时已失效。

修复：持久化执行租约、执行者和最后进展时间；进程启动时核对中断任务，凭据已丢失时明确标为中断并要求重新输入，不保存明文 SSH 密码来伪装可恢复。入队失败及时写失败状态，注册令牌有效期从实际执行需求考虑。

### F06 · P1：在线升级只靠 IP 字符串识别原节点，没有绑定目标身份

位置：[NodeDeploymentServiceImpl.java:146](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/service/node/NodeDeploymentServiceImpl.java:146)、[NodeDeploymentCreateReqVO.java:11](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/controller/admin/node/vo/NodeDeploymentCreateReqVO.java:11)。

从某一节点行打开在线升级后，请求没有携带选中的 nodeId，后端仅用 `selectByIpAddress(host)` 决定 INITIAL 或 REDEPLOY。使用主机名、地址改变、清理过节点凭据或编辑目标地址时，页面所选节点、连接主机和最终注册身份可能不一致。重复编码要等安装完成、Agent 注册时才会被拒绝。

修复：在线重部署显式绑定已有节点，连接预检验证远端现有身份与目标相符；新节点先校验编码占用及是否已安装，明确接管/恢复身份分支。IP 是连接属性，不应是身份唯一依据。

### F07 · P2：预检“支持部署”的判断与实际安装条件不一致

位置：[NodeDeploymentServiceImpl.java:28](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/service/node/NodeDeploymentServiceImpl.java:28)、[NodeDeploymentRunner.java:284](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/service/node/NodeDeploymentRunner.java:284)。

`sudoAvailable` 只判断 sudo 命令是否存在，不验证当前用户能否提权；系统版本只展示、不参与支持判断；Python 3.13 可以通过，但安装包名固定包含 Ubuntu Python 3.12 的 `libpython3.12t64` 等。内存读取 MemTotal，却标为“可用内存”。预检也没有验证后续控制面地址的反向可达性，该地址在下一步才输入。

修复：分为连接/认证、系统适配、提权权限、磁盘与可用内存、控制面连通几组明确检查；区分阻断项和可自动补齐项，安装器与支持矩阵使用同一份条件。部署配置确认后、替换旧服务前验证控制面可达。

### F08 · P2：日志自动刷新重载整页，干扰历史阅读

位置：[node-logs/index.vue:95](/Users/mateng/Documents/VibeCodingProjects/linsight/frontend/apps/web-antd/src/views/ai-video/node-logs/index.vue:95)、[NodeLogMapper.java:24](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/dal/mysql/node/NodeLogMapper.java:24)。

页面每 10 秒调用一次 `gridApi.query()`。VxeGrid 的该路径会设置整表 loading，并在响应后 `loadData()` 替换数据；即使在第 2 页、设置了历史时间范围，也照常刷新。接口按时间和 ID 倒序、使用页码分页，新增日志使历史页的记录位置移动，可能重复看到或跳过原先的行。“暂停滚动”实际上停止请求，与单纯停止跟随滚动不是同一操作。

本轮没有证据证明该页面重复注册了多个 interval：源码只有一个创建点，VxeGrid 也有查询进行中的拦截。应先修正整页重载策略，不能把所有重复 `list/page` 请求都归因于定时器泄漏。

修复：实时模式只在最新页后台获取增量、按稳定 ID 去重并保留阅读位置；进入历史页或固定时间范围后冻结结果，提示新增数量。分别控制“实时刷新”和“跟随滚动”。失败重试退避，错误提示不要每轮弹窗。

### F09 · P2：SSH 历史缺失是真实数据问题，空状态却无条件归因为旧记录

位置：[deployment-terminal.vue:15](/Users/mateng/Documents/VibeCodingProjects/linsight/frontend/apps/web-antd/src/views/ai-video/node/modules/deployment-terminal.vue:15)、[NodeDeploymentMapper.java:27](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/dal/mysql/node/NodeDeploymentMapper.java:27)。

现有 16 条记录没有持久化 SSH 内容。新增迁移只增加 nullable 字段，没有历史输出来源；刷新 UI 不能补回原始文本。当前源码会在创建时写 QUEUED 日志，并在执行时追加输出，但仍缺少一条新任务的现场闭环证据。

终端把任何 FAILED/SUCCEEDED 且日志为空的记录都解释成“创建于日志功能启用前”，没有采集版本或日志状态依据。今后的采集故障、读取失败也可能被误报为旧记录。此外，服务诊断只在等待心跳超时分支采集，安装命令直接失败时只写异常摘要；随机 diagnosticId 没有对应的可导航诊断详情。

修复：增加日志采集状态/版本、截断标记、游标和诊断关联；准确区分未采集、采集中、采集失败、无输出。保留历史缺失事实；对新任务验证执行中内容增长、关闭重开仍可读、失败时有定位信息。列表不返回 outputLog 是现有轻量投影设计，详情接口才取原文，这一点本身正确。

### F10 · P2：签名升级的成功仅代表切换目录，尚未验证新进程

位置：[executor.py:233](/Users/mateng/Documents/VibeCodingProjects/linsight/runtime/edge_agent/app/command/executor.py:233)、[NodeUpgradeServiceImpl.java:99](/Users/mateng/Documents/VibeCodingProjects/linsight/backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main/java/com/linsight/module/aivideo/service/node/NodeUpgradeServiceImpl.java:99)。

Agent 安装后立即上报 SUCCEEDED/ACTIVATING，结果里带 `restartRequired=true`；后台直接把升级记录置为成功。虽然页面文案提醒手动重启，但升级记录不会继续等待目标版本心跳，也没有启动失败后的自动回退。在线重部署与签名升级的“成功”含义不同。

修复：区分已安装、待激活、激活中、待健康确认、成功、已回退；成功以本次目标版本进程运行和新鲜心跳为依据。若保留人工重启，应将业务状态保留在“待激活”，并提供同一记录内的后续动作及确认结果。

## 其他交互与验收缺口

- 新部署和在线重部署共享抽屉，但没有完整的返回/重试、已部署身份校验、控制面配置继承及当前/目标版本说明；向导需要围绕任务状态设计。
- 部署记录只取最近 20 条，不能按节点筛选或分页；返回列表也不更新已完成状态。在线重部署在“部署记录”，签名升级在另一套“升级与命令记录”，查一次升级需要跨多个入口。
- 升级与命令抽屉每 3 秒请求两组记录，即使仅查看一个标签页、所有操作已结束也继续。应由活动操作驱动刷新并在终态收敛。
- 节点页顶部“生成注册令牌”“部署新节点”缺少与后端对应的按钮权限控制；后端有校验，因此不是已确认的越权，但普通查看用户会看到无法执行的入口。
- 节点资源缺失时默认显示 0%，会把“未上报”解释成“空闲”；页面尚未完整提供任务数、模型数、磁盘等既定节点概览字段。
- 现有部署 Runner 测试主要断言脚本文字与心跳判断，节点向导没有覆盖实际分步挂载的成功路径。类型检查、构建和后端单元测试通过，不能证明前端部署闭环可用。

## 建议修复顺序与回归标准

1. 修复 F01/F02 的整个向导生命周期，而非仅交换某一行代码。覆盖全新主机、已有节点、预检失败、创建失败、关闭再开；成功响应后必须解除锁定，取得 ID 后必须开始查询。
2. 完成新任务日志的持久化及前端实时显示闭环，区分历史缺失；日志页历史阅读不得因实时刷新变化，失败提示与重试有界。
3. 补齐按节点互斥、请求幂等及控制面重启后的中断处理；同节点双请求、重部署时重启/升级要明确拒绝，不能交叉覆盖文件。
4. 统一目标身份与部署支持条件，更新/检查节点配置后再切换服务。
5. 建立部署失败恢复及升级激活确认；回归启动失败、控制面不可达、磁盘不足、回滚后版本恢复，并验证旧任务能按既有恢复策略恢复。

现场验收应先完成可逆的预检及在线重部署，确认 SSH 日志持续增长、持久化可回读、目标版本心跳达成。真实主机关机验收另需具备现场开机条件；本次未执行。
