# 本机 Linux 模拟盒子

在 Docker Desktop 的 Linux VM 中运行真实 Runtime、Agent 和 systemd。Mac 不安装
systemd，不替换本机 Python。容器无宿主机目录或设备挂载；仅将管理口映射为
`127.0.0.1:48911`。systemd 需要容器 `privileged` 权限。
Docker 桥接网络允许出站；模拟器配置的中心地址固定为 `127.0.0.1:9`，身份全部为合成数据。

## 首次创建

准备 `generic` 机型、与 Docker Linux CPU 架构一致的签名包。Mac ARM64 使用 `aarch64`。
构建步骤见 [应用升级说明](../../docs/BOX_APPLICATION_UPGRADE.md)。测试私钥只能用于模拟器。

```bash
docker compose -f deploy/box-simulator/compose.yml up -d --build
docker exec linsight-box-simulator mkdir -p /simulation/keys
docker cp /absolute/path/app.lup linsight-box-simulator:/simulation/release.lup
docker cp /absolute/path/linsight-bootstrap.pyz linsight-box-simulator:/simulation/linsight-bootstrap.pyz
docker cp /absolute/path/simulator.pem linsight-box-simulator:/simulation/keys/simulator.pem
docker cp /absolute/path/aarch64-cp312 linsight-box-simulator:/simulation/wheels
docker cp deploy/box-simulator/provision.py linsight-box-simulator:/simulation/provision.py
docker exec linsight-box-simulator python -m pip install --no-index --find-links /simulation/wheels cryptography
docker exec -e LINSIGHT_SIMULATOR=1 linsight-box-simulator python /simulation/provision.py
```

打开 <http://127.0.0.1:48911>，测试管理密码 `linsight-simulator-only`。
该容器模拟未迁移的标准旧设备，provision 只允许执行一次，不能在实体设备运行。

## 迁移与升级演练

```bash
docker exec linsight-box-simulator /opt/linsight/venv/bin/python /simulation/linsight-bootstrap.pyz \
  --bundle /simulation/release.lup --public-key /simulation/keys/simulator.pem --key-id simulator --check
docker exec linsight-box-simulator /opt/linsight/venv/bin/python /simulation/linsight-bootstrap.pyz \
  --bundle /simulation/release.lup --public-key /simulation/keys/simulator.pem --key-id simulator
docker exec linsight-box-simulator linsight-upgrade install /simulation/release.lup
docker exec linsight-box-simulator linsight-upgrade status
docker exec linsight-box-simulator linsight-upgrade rollback
```

也可在应用升级标签页实际上传包、预检、确认安装及回退。安装期间暂时断线属预期，
页面会自动查询恢复状态。使用另一版本号的包才能模拟下一次发布。

数据保留检查可创建一条停止任务和未发送事件：

```bash
docker cp deploy/box-simulator/data_probe.py linsight-box-simulator:/simulation/data_probe.py
docker exec -e LINSIGHT_SIMULATOR=1 linsight-box-simulator /opt/linsight/venv/bin/python /simulation/data_probe.py seed
# 执行升级、回退或中断恢复后：
docker exec -e LINSIGHT_SIMULATOR=1 linsight-box-simulator /opt/linsight/venv/bin/python /simulation/data_probe.py check
```

中断演练脚本只接受固定容器名和模拟身份。先把另一个版本的包放到
`/simulation/next.lup` 并执行 `linsight-upgrade check /simulation/next.lup`，再运行：

```bash
python3 deploy/box-simulator/interrupt_test.py daemon --evidence var/box-simulator/evidence/daemon.json
# 再次 check 准备后，可以演练容器被强制终止：
python3 deploy/box-simulator/interrupt_test.py container --evidence var/box-simulator/evidence/container.json
```

脚本在 `CHECKING` 时注入故障，等待回退并核对数据探针；每轮必须重新准备包。
这些是进程和容器中断测试，不能称为实体设备断电试验。

日常 `docker compose ... stop` / `start` 会保留容器状态；`down`、`--force-recreate`
会清除该模拟盒子内部数据，重建需重新 provision。发布包和测试密钥建议保存在仓库已忽略的
`var/box-simulator/` 下。模拟器不会证明 RKNN/MPP/RGA、实际摄像头或物理断电行为正确。


## 平台网页生成升级包

本机主平台入口：http://localhost:5666/ai-video/node （本地初始化账号 `admin / admin123`）。
进入“盒子升级包 → 生成升级包”，填写新的版本号和更新说明即可。主平台默认生成
“ARM64 统一应用包（本机测试）”，适用列表包含 RK3566 / RK3568 / RK3588 和模拟器 generic；
同一包只有一份程序和依赖，使用模拟器测试密钥，不能作为已验收的客户发布包。
主平台本机配置保存在忽略文件 `var/application-release-local.yaml`，使用 `local` profile 正常重启
后端即可加载；测试包使用专用私有文件配置及本机下载域名。此配置只用于当前电脑和模拟器。

另保留隔离平台验证环境：http://127.0.0.1:5667/ai-video/node 。
其后端 48889 使用独立数据库和 Redis DB 14，不接入客户节点。

隔离平台启动配置位于忽略目录 `var/platform-release-simulator/`，运行中的构建使用受信源码、
已有 gateway-console、aarch64 固定依赖和模拟器私钥。机器重启后的复现方式：

```bash
bash var/platform-release-simulator/start-backend.sh
# 另一个终端，使用项目要求的 Node/pnpm 环境：
LINSIGHT_DEV_PROXY_TARGET=http://127.0.0.1:48889 pnpm --dir frontend/apps/web-antd exec vite --mode development --host 127.0.0.1 --port 5667
```

正式部署的一次性配置见 [盒子应用升级文档](../../docs/BOX_APPLICATION_UPGRADE.md) 与
[`application-release.example.yaml`](../application-release/application-release.example.yaml)。
