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

## Windows + IDEA，使用本机或远程 MySQL/MinIO

仅手动导入 `backend/sql/mysql/linsight.sql` 不会完成部署。基础快照之外还需要完整增量迁移，
以及 MinIO 中的真实权重和数据库中的模型版本。截图中“0 个版本 / 未上传”表示只有逻辑目录；
吸烟、分割、通用 OCR 等已移除的占位模型仍显示，说明目标库未完成相关迁移。

安装 Python 3.10+、启动现有 MySQL/MinIO 后，在**同事实际启动的仓库根目录**打开 PowerShell：

```powershell
git pull --ff-only
Copy-Item deploy/model-assets/native.env.example .env.native
notepad .env.native
python -m pip install -r scripts/requirements-model-assets.txt
python scripts/initialize-model-assets-native.py
```

首次复制配置后填写 `MYSQL_HOST/PORT/DATABASE/USER/PASSWORD` 和 MinIO API 地址及账号密码。
再次执行时直接运行最后一条命令，保留已填写的 `.env.native`。该文件已加入 Git 忽略规则。
MinIO 使用 API 端口（一般 9000），不是控制台端口（一般 9001）；地址必须能被 Java 后端访问。
跨机器部署节点时填写 `LINSIGHT_MODEL_PUBLIC_ENDPOINT`。数据库账号需要执行增量 DDL 和业务数据写入的权限。
使用远程 MySQL TLS 时可设置 `MYSQL_SSL_CA`。

命令输出的 `[target]` 数据库地址与库名必须与 IDEA 启动配置里的 `DB_URL` 一致。
运行时会按版本顺序补齐增量 SQL、写入同一张 `infra_schema_migration` 迁移记录表、校验仓库权重，
直接上传 MinIO 并登记 15 个当前发布模型。已有迁移和相同模型版本会复用；不重新导入基础快照。
如果目标库没有基础快照，会停止并提示先导入，避免覆盖已存在的业务数据。

完成后重启 IDEA 中的后端，并在同一仓库重新启动前端：

```powershell
cd frontend
corepack pnpm@11.7.0 dev:antd
```

部署静态页面则执行 `corepack pnpm@11.7.0 build:antd` 并替换服务器上的前端文件。
前端需要 Node.js 22.18+ 的 22 系列或 24 系列。最新资产页按钮为“查看可部署模型”。
模型资产列表应显示实际版本、ONNX/RKNN 等格式和文件大小；新导入版本的执行状态仍为 `NOT_READY`。

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
本机或远程连接入口的 TCP/S3 回归可在已启动 Docker 基础设施的测试机器上运行
`python scripts/tests/model-assets-native-roundtrip.py`；测试创建临时库和独立 MinIO，验证后清理。
