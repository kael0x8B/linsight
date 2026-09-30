# LInsight 文档导航

本目录保留长期维护的规范、协议、功能说明、操作手册与架构决策。历史修复、审查、部署回执和测试验收记录已清理；页面规格中的批准约束仍保留。

文档描述实现约定与使用方法，不代表当前版本已通过现场验收；生产发布仍按发布手册检查实际证据。

## 入门学习

- [AI 技术与项目架构学习地图：从平台到盒子](AI_TECH_AND_PROJECT_MAP.md)：技术解释、执行链路、分包目录树与源码阅读顺序。

## 项目规范与规格

- [LInsight 架构与编码规范](ARCHITECTURE_AND_CODING_GUIDELINES.md)
- [LInsight 需求汇总与实施口径](REQUIREMENTS_SUMMARY.md)
- [LInsight 开发计划与页面级规格](DEVELOPMENT_PLAN.md)
- [LInsight 平台基线说明](BASELINE.md)
- [LInsight 控制台 UI/UX 优化基线](UI_UX_OPTIMIZATION_BASELINE.md)

## 协议与数据契约

- [算法、Pipeline 与 AI 任务协议 V1](ALGORITHM_PIPELINE_TASK_PROTOCOL_V1.md)
- [LInsight AI 全局参数与版本下发协议 V1](GLOBAL_SETTINGS_PROTOCOL_V1.md)
- [模型资产与版本契约 V1](MODEL_ASSET_VERSION_CONTRACT_V1.md)
- [模型部署与单图测试协议 V1](MODEL_EXECUTION_PROTOCOL_V1.md)
- [单路预览与 Overlay 协议 V1](PREVIEW_AND_OVERLAY_PROTOCOL_V1.md)
- [子码流 WebRTC 预览与 Overlay 协议 V2](PREVIEW_AND_OVERLAY_PROTOCOL_V2.md)
- [Rule、Event 与区域入侵闭环协议 V1](RULE_EVENT_AREA_INTRUSION_PROTOCOL_V1.md)
- [LInsight Webhook 投递协议 V1](WEBHOOK_PROTOCOL_V1.md)

## 功能与使用说明

- [LInsight 内置通用模型与算法目录 V1](BUILTIN_MODEL_ALGORITHM_CATALOG_V1.md)
- [摄像头算法管理](CAMERA_ALGORITHM_MANAGEMENT.md)
- [入口主动刷脸核验实施说明](ENTRY_FACE_VERIFICATION_IMPLEMENTATION.md)
- [已录入人员的特征提取](FACE_REFERENCE_EXTRACTION.md)
- [网关独立运行与平台双入口](GATEWAY_DUAL_ENTRY.md)
- [盒子通用事件接口](GATEWAY_EVENT_DELIVERY.md)
- [矿区车头车牌场景配置](GATEWAY_PLATE_EVENT_DELIVERY.md)
- [可部署算法包（SDK 1.0）](algorithm-packages/README.md)
- [算法配置与算法包使用](algorithm-packages/USAGE.md)

## 部署、运维与发布

- [边缘节点部署与依赖说明](EDGE_DEPLOYMENT_GUIDE.md)
- [LInsight Operations SOP](OPERATIONS_SOP.md)
- [LInsight V1.0 发布与回滚手册](V1_RELEASE_RUNBOOK.md)
- [LInsight 生产现场验收 Runbook](PRODUCTION_FIELD_ACCEPTANCE_RUNBOOK.md)

## 架构决策

- [ADR-0001：多格式模型执行与可信 PT 边界](ADR-0001_MULTI_FORMAT_MODEL_EXECUTION.md)
- [ADR-0002：通过 SSH 完成边缘节点初始接管部署](ADR-0002_EDGE_INITIAL_PROVISIONING_OVER_SSH.md)
- [ADR-0003：Edge Agent 反向预览通道](ADR-0003_EDGE_PREVIEW_REVERSE_CHANNEL.md)
- [ADR-0004：固定子码流的 WebRTC 实时预览](ADR-0004_SUBSTREAM_WEBRTC_PREVIEW.md)
- [ADR-0005：声明式模型 Runtime 与目录去重](ADR-0005_DECLARATIVE_MODEL_RUNTIME_AND_CATALOG_CONSOLIDATION.md)
- [ADR-0006：Edge Agent 在线重部署与节点生命周期闭环](ADR-0006_EDGE_ONLINE_REDEPLOYMENT_AND_LIFECYCLE.md)
- [ADR-0007：RK3566 NPU 加速与识别画面同步](ADR-0007_RKNN_ACCELERATION_AND_PREVIEW_ALIGNMENT.md)
- [ADR-0008：网关控制台独立不可变制品](ADR-0008_GATEWAY_CONSOLE_IMMUTABLE_ARTIFACT.md)
- [ADR：网关自治与平台、本地双入口](adr/ADR-20260908-dual-entry-gateway.md)
- [可部署算法包](adr/ADR-20260909-deployable-algorithm-packages.md)
- [ADR：盒子通用事件定向投递](adr/ADR-20260920_GATEWAY_EVENT_DELIVERY.md)

## 发布配置与模板

- [现场验收清单模板](production-acceptance.example.json)：供发布流程生成现场证据清单。
- [依赖风险配置](security/dependency-risk-acceptance.json)：供依赖审计及发布门禁读取，不是历史报告。
