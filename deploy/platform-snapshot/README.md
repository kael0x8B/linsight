# 复现当前开发机的业务环境

这是交付给同事的恢复入口。只导入 `backend/sql/mysql/linsight.sql` 得到的是基础结构和历史种子，不能得到开发机已配置的任务、规则、上传的算法包和已验证模型。

## Windows + IDEA：只配置两个文件

先拉取最新代码并停止目标环境的后端。安装 Python 3.12（或 3.13），在项目根目录操作：

1. **部署密钥**：由交付人员单独提供 `deployment.key`，复制到项目根目录并命名为 **`.deployment-key`**。交付人员原文件在 `var/platform-snapshot/deployment.key`，不要提交 Git。它用于解密摄像头凭据、人员库及业务配置。
2. **连接配置**：复制 `deploy/model-assets/native.env.example` 为项目根目录 **`.env.native`**，用 IDEA 打开编辑即可。填写同事实际使用的服务：

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=linsight
MYSQL_USER=root
MYSQL_PASSWORD=同事的MySQL密码
MYSQL_SSL_CA=
MINIO_ENDPOINT=http://127.0.0.1:9000
MINIO_ROOT_USER=同事的MinIO账号
MINIO_ROOT_PASSWORD=同事的MinIO密码
LINSIGHT_MODEL_PUBLIC_ENDPOINT=http://同事电脑或服务器的局域网IP:9000
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DATABASE=0
REDIS_PASSWORD=
DB_URL=
```

MySQL、MinIO、Redis 在远程服务器时，将相应地址和端口改为服务器实际值。MinIO 填 API 端口，默认 `9000`；`9001` 是控制台端口。`LINSIGHT_MODEL_PUBLIC_ENDPOINT` 必须能被盒子和浏览器访问，跨机器使用时不能填 `127.0.0.1`。使用 MySQL TLS 时，在 `MYSQL_SSL_CA` 配置脚本所用证书路径，并在 `DB_URL` 填写后端所需的完整 JDBC TLS 配置。

然后只执行：

```powershell
py -3.12 -m pip install -r scripts/requirements-model-assets.txt
py -3.12 scripts/restore-platform-snapshot.py
```

已有数据库会在 SQL 迁移完成后备份业务配置，再替换为交付快照；数据库不存在时会自动创建。**这是完整配置恢复，会替换目标租户 1 的业务配置；请用于同事的部署库，不要在已有独立业务数据的生产库直接运行。** 脚本不连接源开发机，不需要 Docker、Bash 或在线下载模型。

恢复完成后，IDEA 后端使用 **`local` profile** 启动；工作目录设为项目根目录、`backend` 或 `backend/linsight-server` 均可。生成的 `var/application-native-local.yaml` 自动覆盖数据库和 Redis 连接，`var/application-release-local.yaml` 自动启用升级包构建。无须再手工同步 `application-local.yaml` 里的连接参数。

前端按仓库原启动方式重启并重新登录。保持后端默认端口 `48888` 时无需修改前端；如果 IDEA 改了后端端口，同时将 `frontend/apps/web-antd/vite.config.ts` 中 `backendTarget` 的默认地址改为对应地址，或给前端进程设置 `LINSIGHT_DEV_PROXY_TARGET`。

## 恢复结果

| 内容 | 数量 / 范围 |
| --- | --- |
| 启用模型 | 15 个；保留源环境实际测试记录、执行契约与可部署版本 |
| 算法中心 | 24 类；底层 27 条定义，界面按名称合并；含 17 个当前算法包 |
| 规则中心 | 18 条及规则版本 |
| AI 任务 | 9 个当前任务，包含模型绑定、参数、ROI、摄像头和节点关联 |
| 摄像头 / 边缘节点 | 4 路 / 5 个 |
| 其他配置 | 识别库、人员参考、出入口配置、监控布局、全局设置和已有关联配置 |
| 文件 | 当前及任务引用的模型版本、算法包、测试凭据图片、识别库必需资源；每个文件校验 SHA256 |

快照保留当前指针及任务固定引用的模型/Pipeline 版本，不打包无引用的旧版制品。历史告警、录像、运行日志、任务运行记录和原数据库账号权限不复制；新库系统账号使用基础 SQL 的账号。

任务恢复为**已停止**，节点/摄像头恢复为**离线**；这是进程状态，需目标环境重新建立连接。模型的 READY 与测试记录来自源环境的真实数据，不能替代新硬件的现场验收。同事在相同网络可直接使用原摄像头配置；盒子 Agent 的平台地址需要指向新平台，已有节点密钥摘要保留，可继续使用原节点身份。新网络的摄像头和节点地址在对应页面修改后，再启动任务。脚本不会自动控制正在源平台运行的设备。

## 升级包生成

完整恢复会一起准备 ARM64 发布基线：独立 Linux Python 3.12、离线依赖、网关网页制品、本机签名密钥和构建配置。重启后端后，“边缘节点 → 盒子升级包”即可生成 `.lup`，目标为 RK3566 / RK3568 / RK3588（glibc ≥ 2.34）。不要求 Windows 安装 Linux Runtime 依赖。

只修复发布环境时可单独运行 `py -3.12 scripts/prepare-application-release.py`。已有发布配置与私钥保留；项目移动目录后，用 `--replace-config` 重新生成路径。自己的代码改变 Runtime 依赖或网页后，需要重新构建/导出发布基线，不能继续使用过期制品。

新发布机生成独立签名密钥。已有盒子首次信任该发布机时，按 [盒子应用升级说明](../../docs/BOX_APPLICATION_UPGRADE.md) 完成受信任公钥配置/首次迁移，再使用 `.lup` 安装；平台生成升级包不要求先连接盒子。

## 重复恢复与回退

同一快照重复恢复不会新增重复业务记录。恢复前加密备份位置会打印为 `var/platform-snapshot/before-restore-*.enc`；对象文件按摘要存放，旧文件不删除。停止目标后端后可回退业务配置：

```powershell
py -3.12 scripts/restore-platform-snapshot.py --rollback-backup var/platform-snapshot/before-restore-实际时间.enc
```

回退不撤销 SQL 结构升级；数据库/Redis 本机连接配置和发布密钥保持现状。解密密钥错误、资源校验失败会终止恢复，业务数据写入与文件元数据在一个数据库事务内提交。

交付人员更新快照使用 `scripts/export-platform-snapshot.py`，更新可公开初始化的算法目录使用 `scripts/export-deployment-algorithms.py`，更新发布基线使用 `scripts/export-release-baseline.py`。这些导出器只读取源数据库和对象文件，不修改本机业务配置。
