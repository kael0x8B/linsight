# 模型资产初始化

本目录交付当前发布的 15 个逻辑模型及对应权重、来源版本、许可证、SHA256 和 Runtime 执行契约。
权重位于 `files/`，目录与版本映射位于 `catalog.json`，执行契约位于 `runtime-manifests.json`。
这些文件随 Git 一起交付，新环境初始化不需要访问 Hugging Face 或其他模型下载站。

## 新环境或旧版本补齐

安装根目录 README 中的依赖后，从仓库根目录执行：

```bash
git pull --ff-only
make init
make model-assets-init
```

该命令启动基础设施、执行完整增量迁移、校验每个权重、上传至私有 MinIO 并按模型编码登记模型和版本。
重复执行保留同一版本，不复制节点、摄像头、用户或现场测试记录。同一版本已有不同权重或执行契约时会拒绝覆盖。
使用外部 MySQL 容器时可通过 `LINSIGHT_MYSQL_CONTAINER` 和 `LINSIGHT_MIGRATION_DATABASE` 指定。
导入到其他租户时，在完成迁移后执行 `python3 scripts/sync-builtin-model-assets.py --register --tenant-id <租户编号>`。

跨机器接入节点前，在 `.env` 设置 `LINSIGHT_MODEL_PUBLIC_ENDPOINT=http://平台可达IP:29000`
（或实际 HTTPS MinIO API 地址），再执行初始化。默认回环地址只适合同机部署。
初始化完成后启动或重启后端，刷新前端的“模型资产”列表；已运行基础设施时也可以单独执行 `make model-assets-sync`。
生产静态前端需重新构建以应用模型资产默认页：`cd frontend && corepack pnpm@11.7.0 build:antd`。

## 版本与硬件

导入后的版本已发布，执行状态初始为 `NOT_READY`。在“版本与部署”中选择相匹配的节点部署、完成单图测试后，
版本才会进入“可部署模型”目录。源环境的节点测试结果不能代替目标机器的执行验证。
ONNX 版本使用对应 Runtime 适配器；RK3566 和 RK3588 的 RKNN 权重需要匹配芯片的 NPU 环境，
人脸组合 ZIP 同样需要其执行契约指定的后端。普通 x86 机器可显示这些资产，但不能加载 Rockchip NPU 权重。

只执行 `make infra` 会完成数据库迁移，模型权重和版本仍需通过上述模型初始化命令导入。

## 后续发布维护

维护者可从已配置的 MySQL/MinIO 导出当前发布版本：

```bash
python3 scripts/export-deployment-model-assets.py --catalog-version YYYY.MM.DD.N
```

导出器校验文件大小、SHA256 和 ONNX 格式，并只保存逻辑模型、版本、执行契约及权重；
对象存储地址、签名参数、数据库主键和节点凭据不进入交付目录。
提交前检查目录差异；完整初始化及重复导入可通过 `bash scripts/tests/model-assets-roundtrip.sh` 验证。
