# LInsight 架构与编码规范

> 2026-09-08 已批准的架构扩展：网关拥有本机执行配置，平台和本地管理双入口并存。原有“配置仅由中心拥有、浏览器仅访问 Java”的约束在此单节点范围内由 [ADR](adr/ADR-20260908-dual-entry-gateway.md) 修订，操作与迁移见 [双入口说明](GATEWAY_DUAL_ENTRY.md)。


> 状态：V1.0 基线规范。适用于 LInsight Java 控制面、AI Runtime / Edge Agent、Vue 管理端以及三者之间的协议开发。
>
> 本规范延续当前基座的 Maven Module、Spring Boot 分层、Vue 目录与独立 Runtime 方案，不引入另一套架构。文中的“必须/禁止”属于合并门禁，“建议”允许在评审后例外。

## 1. 设计原则

1. 以“摄像头可用 → 视频可看 → 模型可部署 → 任务可运行 → 规则可确认 → 事件可处置 → 边缘可自治”为主链路。
2. 控制面、计算面、展示面分离。Java 管理状态与编排，Runtime 处理视频和推理，Vue 负责交互与可视化。
3. V1.0 保持模块化单体控制面。业务边界先通过 Module、Package、接口和测试固化，达到独立扩缩容条件后再评估拆服务。
4. 领域数据只有一个写入责任方。其他领域只通过明确的 Service/API 契约读取或发起命令。
5. 接口、命令、配置和实时消息从 V1 起版本化；所有重试路径必须幂等。
6. 不为复用而提前抽象。出现至少两个稳定调用方、语义一致且生命周期一致时，才能提取公共组件。
7. 新业务代码必须沿用 `com.linsight`、`linsight-*`、`ai-video:*` 命名体系。

## 2. 系统边界与运行职责

| 组件 | 负责 | 不负责 |
| --- | --- | --- |
| `linsight-server` Java 控制面 | 用户权限、租户、业务配置、版本、编排、事件主记录、处置、审计、开放 API | RTSP 长连接、FFmpeg 解码、逐帧推理、GPU 资源调度 |
| AI Runtime | 拉流、解码、采样、模型池、推理、跟踪、规则计算、证据缓冲、运行指标 | 用户权限、菜单、业务配置真值、人工事件处置 |
| Edge Agent | 节点注册、心跳、资源上报、命令执行、模型/配置下载、离线缓存与补传、升级回滚 | 自行修改中心配置、直接写控制面数据库、业务审批 |
| Vue 管理端 | 配置、监控、视频/Overlay 展示、事件处置、诊断入口 | 在浏览器内执行模型推理、持有明文设备密钥、代替后端做权限判断 |
| MySQL | 控制面配置和业务主数据 | 视频帧、长录像、模型二进制 |
| Redis | 会话、短期缓存、分布式协调和限流状态 | 唯一业务真值、不可重建的事件数据 |
| MinIO | 模型、截图、录像、导出文件等对象 | 业务状态机和权限真值 |

强制边界：

- Runtime / Agent 只能通过 `/node-api/ai-video/**`、gRPC 或约定消息协议访问控制面，不得连接控制面 MySQL。
- 管理端只能调用 `/admin-api/**`，不得直接访问 Runtime、Redis、MySQL 或 MinIO 管理凭据。
- Java 控制面不得引入 FFmpeg 解码循环或 ONNX 推理主循环；连通性探测必须有超时、限流并与持续拉流分离。
- 本地默认由 `linsight-server` 聚合运行；启用 Gateway/Nacos 或拆分服务必须单独提交 ADR，不得由单个 Story 顺带引入。

## 3. Maven Module 划分

### 3.1 现有 Module 责任

| Module | 责任 | 依赖规则 |
| --- | --- | --- |
| `linsight-common` / `linsight-framework/*` | 无业务语义的通用类型与技术 Starter | 禁止依赖任何业务 Module |
| `linsight-module-system` | 用户、组织、租户、RBAC、字典、通知、审计 | 不得反向依赖 AI 视频业务 |
| `linsight-module-infra` | 文件、配置、任务调度、API 日志等技术基础设施 | 不得包含摄像头、模型、事件等业务规则 |
| `linsight-module-ai-video` | AI 视频控制面全部业务能力 | 可依赖 `system-api`、`infra-api` 和 Framework |
| `linsight-server` | 聚合各 `*-server` 并提供启动入口 | 不编写业务逻辑 |
| `linsight-gateway` | 未来多服务入口；本地模块化单体不强制启动 | 不编写业务逻辑 |

### 3.2 AI 视频 Module 结构

新增业务必须放入同一个 Maven 父模块，不按 camera、event 等拆成多个微服务：

```text
backend/linsight-module-ai-video/
├── pom.xml
├── linsight-module-ai-video-api/
│   └── src/main/java/com/linsight/module/aivideo/api/
└── linsight-module-ai-video-server/
    ├── src/main/java/com/linsight/module/aivideo/
    ├── src/main/resources/
    └── src/test/java/com/linsight/module/aivideo/
```

`*-api` 只允许包含：

- 跨 Maven Module 使用的 API 接口、DTO、枚举和常量；
- 稳定、最小、与存储实现无关的契约；
- 必要的 Bean Validation 注解。

`*-api` 禁止包含 Controller、Service 实现、Mapper、DO、XML、定时任务和具体 SDK Client。没有跨 Module 调用方的接口不放入 `*-api`。

`*-server` 包含控制面实现，并依赖自己的 `*-api`。`linsight-server` 只增加对 `linsight-module-ai-video-server` 的聚合依赖。

### 3.3 新 Module 门槛

以下条件全部满足才允许新建 Maven 业务 Module：

1. 有独立且稳定的业务语言和数据所有权；
2. 与 AI 视频主链路的发布节奏明显不同；
3. 需要独立部署、扩缩容或安全隔离；
4. 拆分后不存在高频分布式事务；
5. ADR 已说明替代方案、依赖方向、数据迁移和回滚方法并通过评审。

未满足时使用 `linsight-module-ai-video` 内部领域包，不允许以“文件太多”为理由拆服务。

## 4. Java Package 与分层规范

### 4.1 标准 Package 模板

延续当前基座的“技术分层在前、业务域在后”结构：

```text
com.linsight.module.aivideo
├── api/{domain}/                 # 本模块对其他 Module 的实现适配（需要时）
├── controller/admin/{domain}/
│   └── vo/                       # SaveReqVO、PageReqVO、RespVO 等
├── controller/node/{domain}/
│   └── vo/                       # Agent/Runtime 协议 VO，与 admin 隔离
├── service/{domain}/             # Service 接口、Impl、领域校验与用例编排
├── dal/dataobject/{domain}/      # MyBatis DO
├── dal/mysql/{domain}/           # Mapper
├── dal/redis/{domain}/           # 可重建缓存与短期状态
├── convert/{domain}/             # MapStruct 或纯转换器
├── enums/{domain}/               # 状态、类型、错误码
├── mq/message/{domain}/          # 异步消息契约
├── mq/producer/{domain}/
├── mq/consumer/{domain}/
├── job/{domain}/                 # 仅触发 Service，不承载业务规则
├── integration/{adapter}/        # Webhook、Runtime、对象存储等适配器
└── framework/                    # 仅本 Module 使用的配置与横切能力
```

`{domain}` 只能使用：`camera`、`model`、`algorithm`、`task`、`rule`、`event`、`node`、`integration`。不得创建含义模糊的 `common`、`misc`、`manager`、`handler` 大包；确需共享的纯值对象放在最接近所有者的领域中。

### 4.2 分层职责

| 层 | 可以做 | 禁止做 |
| --- | --- | --- |
| Controller | 参数接收、`@Valid`、权限、协议转换、调用 Service、返回 `CommonResult` | 直接调用 Mapper、编写事务、实现状态机、拼装复杂 SQL |
| Service | 业务校验、用例编排、事务边界、状态迁移、调用本领域 Mapper/外部端口 | 返回 Controller VO 给其他领域、吞异常、在长事务内调用不可靠外部服务 |
| Mapper/DAL | 本领域数据读写和查询优化 | 业务决策、调用 Service、直接读写其他领域表 |
| Convert | 无副作用的对象转换 | 查库、远程调用、业务校验 |
| API | 跨 Module 的稳定能力契约 | 暴露 DO/Mapper/内部状态机细节 |
| Integration | 封装第三方协议、SDK、重试与错误映射 | 决定核心业务状态、绕过 Service 写库 |
| Job/Consumer | 验证消息/任务元信息并调用 Service | 复制 Service 逻辑、无幂等地修改状态 |

依赖方向必须是：`controller/job/consumer → service → dal`，`service → integration`。反向依赖一律禁止。

### 4.3 Java 命名

- 持久化对象：`CameraDO`；请求对象：`CameraSaveReqVO`、`CameraPageReqVO`；响应对象：`CameraRespVO`。
- 跨 Module 传输对象：`CameraDTO`；API：`CameraApi`；内部业务接口：`CameraService`、实现类 `CameraServiceImpl`。
- Mapper：`CameraMapper`；转换器：`CameraConvert`；枚举：`CameraStatusEnum`；错误码集中到领域或模块的 `ErrorCodeConstants`。
- 布尔字段优先使用可读语义，如 `enabled`、`online`、`executionReady`；避免 `flag1`、`type2`。
- 数据库 ID 使用 `Long`；协议中的业务编码使用稳定字符串，已被引用的 code 不得修改。
- 新代码作者信息使用团队或省略，不得继续写入上游作者/推广信息。

### 4.4 Controller 与 API

- 延续基座的 action 风格路径：`/create`、`/update`、`/delete`、`/get`、`/page`、`/simple-list`，同一资源不得混用另一套风格。
- Admin Controller 根路径为 `/ai-video/{domain}`，由全局前缀形成 `/admin-api/ai-video/{domain}/**`。
- Node Controller 与 Admin Controller 分包、分认证链，形成 `/node-api/ai-video/**`；禁止复用 Admin Token。
- 所有管理接口返回 `CommonResult<T>`；分页返回统一 `PageResult<T>`。
- Controller 必须使用 `@Validated`/`@Valid`、OpenAPI 注解和 `@PreAuthorize`。权限码统一为 `ai-video:{domain}:{action}`。
- Controller 不返回 DO，不接受 Mapper 查询对象；请求/响应字段必须有清晰说明、边界和示例。
- 列表接口必须有确定排序；分页大小设置上限；批量接口设置数量上限。
- API 删除或不兼容变更必须提供迁移窗口。Runtime/Agent 协议通过 envelope `version` 演进，不静默改变字段语义。

### 4.5 Service、事务与状态机

- 写用例的事务边界放在 Service 实现方法；只读查询不得为了方便开启写事务。
- 事务内只进行必要的数据库操作。模型下载、Webhook、节点调用、MinIO 大文件操作必须在事务提交后异步执行。
- 需要“写库 + 发消息/命令”一致性时使用本地消息表/Outbox；禁止依赖“先写库再直接发消息且不补偿”。
- 状态迁移必须通过聚合所属 Service 的显式方法，例如 `startTask`、`confirmEvent`，禁止通用 `updateStatus(id, status)` 绕过校验。
- 乐观并发使用版本号或条件更新；节点命令必须包含 `commandId`、`configVersion` 和幂等键。
- 幂等记录要能区分“处理中、成功、失败可重试、失败不可重试”，不得只用一个布尔值。
- 捕获异常时必须保留 cause；业务异常使用统一 ErrorCode，禁止向前端返回堆栈、数据库或设备凭据。

### 4.6 Java 代码风格

- 使用 Java 17、UTF-8、LF 和 4 空格缩进；不启用 Preview Feature，不在业务模块覆盖父 POM 的依赖版本。
- 延续基座的 Spring 注入与 Lombok 用法；禁止通过静态上下文获取 Bean，禁止把 `ApplicationContext` 当作服务定位器。
- 一个公开类对应一个主文件；方法名表达业务动作。禁止创建不断膨胀的 `Utils`、`Manager`、`Helper` 承载业务逻辑。
- 简单同构对象可使用基座 `BeanUtils`；存在字段重命名、枚举转换或嵌套结构时使用显式 `Convert`，不得在 Controller 中散落转换代码。
- 集合查询无结果返回空集合，不返回 `null`；对外方法的可空参数和返回值必须通过校验、注释或类型语义明确。
- 使用受 Spring 管理且有界的线程池；禁止直接 `new Thread`。异步任务必须显式传递租户、traceId 和必要的安全上下文。
- 禁止 `System.out/err`、空 catch、捕获后忽略 `Throwable`。日志使用参数占位符，不进行无意义字符串拼接。
- 配置统一进入 `application*.yaml` 和类型安全配置类；地址、阈值、密钥和环境差异不得硬编码在 Java 类中。
- 新增公开 Service/API、复杂状态迁移和非显然算法必须有说明“为什么”的注释；不写逐行复述代码的注释。

## 5. 业务域责任与数据所有权

| 领域 | 唯一负责 | 不得负责 | 主要数据 |
| --- | --- | --- | --- |
| `camera` | 摄像头/分组、接入参数、凭据密文、连通检测结果、流状态摘要 | 持续解码、推理任务状态、事件处置 | `ai_camera_group`、`ai_camera` |
| `model` | 模型资产、版本、SHA256、许可证、发布/回滚、节点部署期望与结果 | 定义业务告警、直接启动推理任务 | `ai_model`、`ai_model_version`、模型部署记录 |
| `algorithm` | 算法定义、能力依赖图、Pipeline 草稿/发布版本、默认参数 Schema | 绑定具体摄像头、维护运行实例 | `ai_algorithm`、Pipeline 版本表 |
| `rule` | ROI、时间、N/M 帧、持续、数量、冷却、组合规则及 Schema 校验 | 拉流、保存事件主记录 | `ai_rule`、规则版本表 |
| `task` | 组合 Camera/Algorithm/Model/Rule/Node，管理期望状态、命令、运行摘要与指标 | 拥有模型文件、修改事件处置状态 | `ai_task`、任务版本/运行记录 |
| `event` | 事件状态机、去重主键、证据元数据、处置、误报、通知结果 | 定义模型版本、控制节点升级 | `ai_event`、`ai_event_media`、`ai_event_action` |
| `node` | Agent 身份、认证、心跳、资源、命令执行状态、日志、升级/回滚 | 解释算法语义、修改任务业务配置 | `ai_edge_node`、`ai_node_command` |
| `integration` | WebSocket、Webhook、开放 API、签名、投递重试和外部错误映射 | 成为事件或任务的第二真值库 | `ai_webhook`、投递记录 |

### 5.1 跨域协作规则

- 一个领域只能直接注入自己的 Mapper。跨域读取调用对方的 Service 查询接口；跨域写入调用对方的命令方法或发布领域事件。
- 禁止从 `event` 直接更新 `task` 表，禁止从 `task` 直接更新 `camera` 状态，禁止从 `model` 直接更新 `node` 表。
- 跨域响应使用 DTO/只读投影，不传播对方 DO。DTO 只包含调用所需字段，不复制整张表。
- 高频只读组合页面可以建设专用 Query Service；它可读多个领域的只读投影，但不得承担写操作或状态机。
- `task` 是配置编排者，不是所有领域的“上帝服务”。事件确认由 `event` 负责，模型供应链元数据由 `model` 负责，节点命令执行由 `node` 负责。
- 领域发生变化时优先发布有版本的事件；同步调用仅用于调用方必须立即得到确定结果的场景。
- 跨 Module 只能依赖 `*-api`，不得依赖其他 Module 的 `*-server`。

### 5.2 允许的主依赖方向

```text
camera ─┐
model ──┼──> task ──> node(command)
algorithm ┤      │
rule ───┘       └──> event(runtime result)

event ──> integration(notification)
model ──> node(deployment command)
```

箭头表示通过 Service/事件使用对方能力，不表示可以访问对方 Mapper。任何反向调用形成闭环时，必须改为事件或独立编排 Service，并在评审中说明。

## 6. 数据库、缓存与对象存储

### 6.1 表和 DO

- AI 视频表统一使用 `ai_` 前缀、`snake_case`，表名使用单数业务名或现有清单中的固定名称。
- 租户隔离业务表继承 `TenantBaseDO`；真正全局的数据继承 `BaseDO`，并在设计评审中说明为何不属于租户。
- 保留基座标准审计字段和逻辑删除语义。不得另造 `created_at`、`is_delete` 等同义字段。
- 状态和类型使用小整数/稳定字符串并配套 Enum；禁止在代码中散落魔法值。
- JSON 配置必须包含 `schemaVersion`，通过 JSON Schema 校验；被查询、排序、约束的稳定字段应拆成列。
- 所有外键语义必须建立索引；事件查询至少评估租户、摄像头、任务、状态、发生时间组合索引。
- 不依赖数据库级跨领域级联删除。删除前由所有者 Service 校验引用关系并记录审计。

### 6.2 SQL 迁移

- 当前基座继续使用 MySQL 8.4。新增增量脚本放入 `backend/sql/mysql/migrations/ai-video/`，命名为 `VYYYYMMDDHHMM__short_description.sql`。
- 每个迁移必须说明前置条件、数据量影响、锁表风险、回滚或前向修复方法；生产数据禁止用不可恢复的单步删除。
- 初始化快照 `backend/sql/mysql/linsight.sql` 用于新环境，不替代增量迁移历史。
- 引入 Flyway/Liquibase 属于基础设施变更，需单独 ADR；在引入前由发布流程记录已执行版本，禁止人工执行未入库 SQL。

### 6.3 Redis 与 MinIO

- Redis Key 由模块常量集中管理，格式为 `ai-video:{tenantId}:{domain}:{purpose}:{id}`，必须设置与业务语义匹配的 TTL。
- Redis 数据必须可以从数据库、节点上报或源事件重建；不得只在缓存保存任务真值。
- 分布式锁必须设置租约、拥有者标识和超时；业务正确性不能只依赖锁。
- MinIO 对象 Key 使用租户/领域/日期/业务 ID 分层；数据库只保存对象标识和元数据，不保存永久公开 URL。
- 模型、截图、录像使用不同 Bucket/生命周期策略；下载使用短时签名 URL。

## 7. Runtime / Edge Agent 代码规范

### 7.1 Python Package

```text
runtime/
├── ai_runtime/app/
│   ├── api/              # FastAPI/gRPC 入站协议
│   ├── core/             # 配置、生命周期、日志、错误
│   ├── stream/           # StreamHub、解码、重连、采样
│   ├── capability/       # Detector/Tracker/OCR/Rule 插件协议
│   ├── model/            # ModelPool、adapter、预后处理
│   ├── rule/             # ROI 与时序规则执行
│   ├── evidence/         # 环形缓冲、截图、录像
│   ├── event/            # 运行侧候选事件、去重和上报
│   ├── client/           # 控制面、MinIO、节点协议客户端
│   └── observability/    # metrics、trace、health
└── edge_agent/app/
    ├── command/
    ├── heartbeat/
    ├── artifact/
    ├── offline/
    └── upgrade/
```

- Python 使用类型标注和 Pydantic 契约；边界数据进入核心逻辑前必须验证。
- `StreamHub(cameraId)` 是拉流唯一所有者；多个任务通过有界队列订阅，不得各自创建 FFmpeg。
- 队列必须有容量、丢帧策略和指标；实时链路不允许无界积压。
- 模型实例由 `ModelPool(modelVersionId, device)` 管理；加载、预热、卸载和 OOM 降级可观测。
- 模型差异封装在 Adapter；统一输出归一化坐标、class、confidence、trackId 和 attributes。
- 核心逻辑不得依赖 FastAPI Request 或具体 SDK 类型，便于录制视频回放测试。
- 离线缓存记录幂等键、重试次数和校验值；补传成功前不得删除本地证据。
- 日志不得包含 RTSP 密码、节点密钥、签名 URL；日志和指标必须携带 nodeId/taskId/cameraId/traceId 中适用字段。

## 8. Vue / TypeScript 代码规范

### 8.1 目录

```text
frontend/apps/web-antd/src/
├── api/ai-video/{domain}/        # 类型与 HTTP 请求
├── views/ai-video/{domain}/      # 路由页
│   ├── index.vue
│   ├── data.ts                   # 表格列、Schema 等静态定义
│   └── modules/                  # 页面私有组件
├── components/ai-video/          # 至少两个领域稳定复用的业务组件
├── store/                        # 仅跨页面、需持久共享的状态
└── router/routes/modules/        # 静态路由；业务菜单优先后端权限路由
```

### 8.2 职责与约束

- 页面组件负责组合查询、交互和展示；HTTP 请求只定义在 `src/api/ai-video`，通用 UI 组件不得直接调用接口。
- 页面私有组件放 `views/.../modules`；未达到稳定复用条件时不得放全局 components。
- 服务端状态优先按页面请求和缓存策略管理；Pinia 仅保存身份、跨页面工作区或确有持久化需求的状态。
- API 类型按领域命名空间组织；新代码禁止无说明的 `any`、非空断言和重复定义后端枚举。
- 列表页沿用 VxeGrid、统一搜索栏、分页和操作列；轻量编辑用 Drawer，复杂流程用整页向导。
- 所有页面覆盖 loading、empty、error、no-permission、offline、partial-data；失败状态提供重试和诊断 ID。
- 权限既控制路由/按钮显示，也必须由后端强制校验；隐藏按钮不等于授权。
- 视频 Overlay 使用独立 Canvas/WebGL 层，统一坐标转换工具和 class 色表，不把检测框烧录进 `<video>`。
- 组件卸载时释放播放器 session、WebSocket、定时器、Observer 和对象 URL。
- 文案进入 locale 文件；状态不能只靠颜色表达；图标按钮必须有 tooltip/aria-label。

## 9. 协议、事件与可观测性

### 9.1 统一协议

- 检测帧至少包含 `frameId`、`timestamp`、`cameraId`、`objects[]`、原帧宽高。
- Object 至少包含 `trackId`（适用时）、`class`、`confidence`、`bbox`、`attributes`。
- 实时消息统一 envelope：`type`、`version`、`messageId`、`occurredAt`、`traceId`、`data`。
- 时间使用带时区的 ISO-8601 或协议明确约定的 epoch 毫秒；同一协议内不得混用。
- 坐标统一为 `[0,1]` 归一化左上/右下或 `x/y/width/height`，具体格式在 V1 Schema 固定。
- 未知字段接收方应忽略；删除字段或改变语义必须升级版本。

### 9.2 日志与指标

- 所有跨进程调用传递 `traceId`；命令链同时记录 `commandId`，事件链记录 `eventId`/幂等键。
- 业务日志描述“对象、动作、结果、原因”，禁止只写“操作失败”。异常日志保留堆栈且只记录一次。
- 控制面指标：API 延迟/错误率、任务和事件吞吐、通知重试、对象存储失败。
- Runtime 指标：拉流状态、重连次数、输入/分析 FPS、队列深度、推理延迟、GPU/显存、丢帧和证据积压。
- 高基数字段不得直接作为 Metrics Label；cameraId/taskId 放日志或 Trace，不无界写入 Prometheus Label。

## 10. 安全、租户与审计

- 所有租户业务表和查询默认启用租户隔离；忽略租户必须使用基座机制并写明理由和测试。
- 新增接口默认需要权限。匿名、Node、内部接口分别使用独立安全链，不能通过省略注解实现放行。
- RTSP/ONVIF 密码、Webhook secret、节点凭据必须加密存储，响应中只返回脱敏值；日志严禁输出。
- 模型上传验证扩展名、实际格式、大小和 SHA256；许可证或权重使用条款作为来源元数据记录，不设置商业审核或发布阻断。
- Webhook 使用时间戳、nonce、签名和重放窗口；重试不改变业务事件内容。
- 创建、更新、删除、发布、回滚、任务启停、事件处置、节点升级必须有操作审计。
- SQL、日志、错误信息和导出文件必须遵循最小必要原则；前端不得保存设备明文密码。

## 11. 测试与合并门禁

### 11.1 测试分层

- Service：领域校验、状态机、幂等、并发和权限/租户边界单测。
- Repository：MySQL 8.4 Testcontainers 集成测试，验证索引相关查询和逻辑删除/租户条件。
- API：请求校验、权限码、错误码和 OpenAPI/契约测试。
- Runtime：固定视频回放、帧级 golden result、断流/弱网/磁盘满/GPU OOM 故障注入。
- 前端：TypeScript、lint、组件测试和 Playwright 主链路；视频/ROI 使用确定性 fixture。
- 跨进程：契约兼容、重复命令、乱序上报、断网补传和版本回滚测试。

### 11.2 架构自动检查

AI 视频 Module 骨架建立时必须增加 ArchUnit 或等价检查，至少覆盖：

- Controller 不依赖 `dal..`；
- Mapper 不依赖 `service..` 或 `controller..`；
- 不同 `{domain}` 的 DAL 互不依赖；
- `system`、`infra` 不依赖 `aivideo`；
- `*-api` 不依赖 `*-server`，也不包含 DO/Mapper/Controller。

### 11.3 Pull Request 清单

- [ ] 代码放在正确 Module、领域和分层 Package。
- [ ] 没有跨域 Mapper/DO 访问或循环依赖。
- [ ] 权限、租户、审计和敏感字段处理完整。
- [ ] 状态迁移、重试和命令具备幂等性。
- [ ] 数据库变更有迁移、索引评估和回滚/修复方案。
- [ ] API/消息 Schema 向后兼容并更新契约。
- [ ] loading/empty/error/offline 等页面状态齐全。
- [ ] 单测、集成测试或 E2E 覆盖主要成功/失败路径。
- [ ] 日志、指标、traceId 和诊断信息可定位故障。
- [ ] README、需求映射和页面规格随行为变更同步更新。

## 12. 架构变更流程

以下变更必须先写 ADR 并由负责人确认，不能在普通功能 PR 中隐式完成：

- 新增或拆分 Maven Module、微服务、数据库、消息中间件；
- 改变 `api/server`、Controller/Service/DAL 分层或包命名；
- Runtime 更换推理后端、视频传输主协议或坐标格式；
- 改变领域数据所有权、事件状态机或跨域依赖方向；
- 引入新的全局状态管理、UI 框架、ORM 或数据库迁移框架；
- 不兼容 API/消息/模型配置变更。

ADR 至少记录：背景、决策、备选方案、影响范围、迁移步骤、兼容策略、回滚方案和验收证据。

## 13. Definition of Done

一个业务 Story 只有同时满足以下条件才算完成：

1. 需求编号、页面、API、表/事件和权限码可追踪；
2. 代码符合 Module、Package、职责和依赖规则；
3. 真实业务链路可运行，Mock 只用于并行开发和自动化测试；
4. 成功、失败、超时、重试、离线、无权限和空状态均有定义；
5. 数据迁移、幂等、审计、监控和回滚可验证；
6. 对应测试和构建通过，无新增高危漏洞；
7. 接口文档、运维说明和本规范要求的架构证据已更新。
