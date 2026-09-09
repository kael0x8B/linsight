# 模型资产与版本契约 V1

本文固化 Backlog Story 5 的控制面边界。Model 是可修改的逻辑资产；ModelVersion 是不可原地覆盖的文件版本。
Story 5 的“发布”只选择资产目录默认版本，不表示模型已经完成单图测试、标准化输出或节点部署。Story 6 在同一节点部署 `READY` 且单图测试成功后建立独立的 `executionStatus=READY`；它仍不是精度或业务生产验收结论，执行协议见 `MODEL_EXECUTION_PROTOCOL_V1.md`。

## 数据与所有权

- `model` 领域独占 `ai_model`、`ai_model_version` 的写入。
- 两张表均继承租户、审计和逻辑删除语义。
- 模型文件通过 Infra `FileApi` 写入当前对象存储；数据库保存内部对象引用，管理 API 不返回该引用或永久公开 URL。
- 版本以租户内 `modelId + version` 唯一，文件以租户内 SHA256 去重。
- 12 个需求指定的预置资产只初始化逻辑 Model，不虚构仓库、commit、权重、许可证或可用状态。

## 管理 API 与权限

| API | 权限 | 说明 |
| --- | --- | --- |
| `POST /admin-api/ai-video/model/create` | `ai-video:model:create` | 创建逻辑资产 |
| `PUT /admin-api/ai-video/model/update` | `ai-video:model:update` | 修改资产元数据 |
| `GET /admin-api/ai-video/model/page` | `ai-video:model:query` | 分页查询 |
| `POST /admin-api/ai-video/model/version/upload` | `ai-video:model:upload` | 直传小模型，计算 SHA256、验证扩展名并落对象存储 |
| `GET /admin-api/ai-video/model/version/list` | `ai-video:model:query` | 查看不可变版本，响应不含对象引用 |
| `POST /admin-api/ai-video/model/version/publish` | `ai-video:model:publish` | 选择目录默认版本或回滚到历史版本 |

## 门禁与状态

目录发布要求：

1. 来源仓库与固定 commit/tag 均已填写；
2. SHA256 已由控制面根据实际上传字节计算；
3. 文件扩展名属于受控格式；
4. 版本已登记合法的 `runtimeManifest`（任务、预处理、解码协议、标签/字符表）；
5. 许可证或权重使用条款已作为来源元数据记录。

许可证字段不触发商业审核或目录发布阻断；目录发布表示默认版本切换，不代表节点执行、
节点部署或生产验收通过。

目录状态为 `DRAFT → PUBLISHED → SUPERSEDED`。回滚不会覆盖文件或历史版本，只将目标版本重新设为默认目录版本。

当前直传受平台 16MB Multipart 上限约束，适用于契约验证和小模型。内置大模型由锁定清单同步；
节点下载校验、声明式通用 Runtime 和技术执行 `ready` 已具备。大模型分片/断点续传、剩余模型家族协议、
真实权重精度验收仍未完成，目录发布与技术执行状态均不得解释为生产验收完成。
