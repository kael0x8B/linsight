# 交付验证记录

日期：2026-10-07。源代码基线：`a9fc13f` 加本次交付修改。

- MySQL 8.4 空库导入基础 SQL，执行全部 55 个增量迁移。
- 原生 TCP/S3 初始化执行两次：15 个发布模型、27 条算法定义（界面 24 类）、17 个算法包；通用初始化的执行门禁保持 NOT_READY。
- 完整快照在独立 MySQL 数据库、独立 MinIO 中恢复两次：15 个可部署版本、24 类算法、18 条规则、9 个当前任务；当前模型/Pipeline/规则版本及任务固定版本关联均无缺失。
- 96 个必需资源共 272,611,758 字节，上传后逐个下载，大小与 SHA256 全部匹配；资源引用已迁移到目标 MinIO。
- 错误解密密钥未改变业务数据；恢复前加密备份可以回退，再次恢复成功。
- JDK 17 Maven `linsight-server -am package -DskipTests` 成功；前端网关网页制品生产构建成功。
- 启动独立后端/前端，Chrome 自动登录后验证：模型中心 15 个可部署版本、算法中心“共 24 个算法”、规则 18、任务 9。
- 使用自动生成的发布配置，在含中文及空格的路径中，通过网页生成 ARM64 `.lup` 成功，状态 SUCCEEDED，大小 155,803,898 字节。文件从目标 MinIO 下载后，整体 SHA256、Ed25519 签名、233 个载荷文件和中文更新说明全部验证通过。
- 无密码 Redis 的配置省略 password，避免 Redisson 发送空密码 AUTH。
- 所有交付资源均纳入 Git；摄像头/人员库等业务配置与新增私有资源以 AES-GCM 加密，部署密钥和发布私钥不在 Git 中。

验证机器为 macOS；测试通过 TCP/S3 连接隔离服务，业务恢复和发布准备脚本不依赖 Docker/Bash。尚未在同事的 Windows 机器实际执行，也未在目标盒子安装本次测试包。真实设备连接与硬件兼容性需在目标环境建立，未将其报告为已完成。

复验入口：

```text
python scripts/tests/model-assets-native-roundtrip.py
python scripts/tests/platform-snapshot-roundtrip.py --key-file .deployment-key --keep
node frontend/tests/e2e/platform-snapshot.mjs
```

前两个测试使用开发机的 Docker 服务创建隔离测试资源，不代表交付恢复要求 Docker。最后一个测试应指向隔离恢复环境，默认前端地址 `http://127.0.0.1:5681`，会创建一个测试升级包。
