# 当前算法交付目录

`catalog.json` 含 27 条已启用、已发布的算法定义，界面按名称合并为 24 类；`files/` 提供 17 个经过 SHA256/manifest 校验的算法包。模型关联使用稳定编码，在目标数据库转换为实际 ID。

`initialize-model-assets-native.py` 和 `sync-builtin-model-assets.py` 在导入内置模型时一起同步本目录，退役已知旧种子算法，重复执行复用相同版本。通用初始化保留新环境的验收门禁。

**要复现交付开发机的规则、任务、已验证模型及关联配置，请使用 [完整业务快照恢复](../platform-snapshot/README.md)**。
