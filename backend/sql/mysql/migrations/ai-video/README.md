# AI 视频增量 SQL

本目录保存 `linsight-module-ai-video` 的 MySQL 8.4 增量脚本。文件按
`VYYYYMMDDHHMM__short_description.sql` 命名；统一通过项目根目录的
`make migrate` 执行。脚本会强制 MySQL 客户端使用 `utf8mb4`、按文件名排序执行、校验已执行脚本的
SHA-256，并在 `infra_schema_migration` 表中登记版本。不要直接用未声明字符集的 `mysql < file.sql`
导入中文迁移，也不使用初始化快照替代迁移历史。

执行前必须确认脚本头部的前置条件、锁表风险和数据量影响。失败后优先采用脚本注明的前向修复；
只有确认没有业务数据或已经完成备份时，才执行回滚段中的破坏性语句。

AI 视频业务表统一使用 `ai_` 前缀、标准审计字段和逻辑删除字段。租户业务表必须包含
`tenant_id`，JSON 配置必须携带 `schemaVersion`。

当前执行顺序：

1. `V202609011430__init_ai_video_module.sql`
2. `V202609011530__add_edge_node_registration.sql`
3. `V202609011700__add_single_camera_preview.sql`
4. `V202609011730__repair_ai_video_menu_encoding.sql`
5. `V202609011900__add_model_asset_version.sql`
6. `V202609021000__add_model_test_deployment_command.sql`
7. `V202609021130__repair_ai_video_utf8_metadata.sql`
8. `V202609021430__add_algorithm_pipeline_task_lifecycle.sql`
9. `V202609021500__add_rule_roi_ast.sql`
10. `V202609021600__add_event_evidence_disposition.sql`
11. `V202609021700__add_area_intrusion_vertical_sample.sql`
12. `V202609021800__add_story11_controlled_algorithm_pipelines.sql`
13. `V202609021900__add_node_upgrade_control_plane.sql`
14. `V202609022000__add_story11_runtime_parameter_contracts.sql`
15. `V202609022100__add_node_logs_and_diagnostics.sql`
16. `V202609022200__add_webhook_delivery.sql`
17. `V202609022300__add_global_settings_versions.sql`
18. `V202609022330__add_universal_model_algorithm_catalog.sql`
19. `V202609022340__repair_license_plate_ocr_catalog_pipelines.sql`
20. `V202609022350__allow_shared_model_artifacts.sql`
21. `V202609030000__remove_model_commercial_review.sql`
22. `V202609030100__correct_pytorch_checkpoint_format.sql`
23. `V202609030200__add_node_initial_deployment.sql`
24. `V202609031215__make_runtime_source_event_id_authoritative.sql`
25. `V202609031600__add_video_wall_layout.sql`
26. `V202609031700__add_recognition_reference_libraries.sql`
27. `V202609031710__add_task_model_bindings.sql`
28. `V202609031720__add_video_acceptance_workbench.sql`
29. `V202609031800__record_node_runtime_package_sha256.sql`
30. `V202609031900__bind_video_wall_layout_to_edge_node.sql`

本地执行：

```bash
make migrate
```

`make infra` 在依赖容器健康后也会自动执行同一套迁移。迁移文件一旦登记不得原地修改；如需修复，
新增前向迁移。
