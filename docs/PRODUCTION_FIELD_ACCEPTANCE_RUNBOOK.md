# LInsight 生产现场验收 Runbook

## 验收边界

只有同一台目标硬件、同一组真实摄像头、同一份不可变发布清单产生的证据才能合并。任何 `WAITING_FOR_*`、缺文件、哈希不符、Mock/测试权重、未知来源或未获商用授权都不得改成 PASS。故障注入必须只阻断 Edge 到控制面的链路，不得同时切断摄像头 RTSP 或本地 Runtime。

## 0. 人员与窗口

到场前确认客户业务验收人、算法验收人、网络管理员、设备管理员和回滚负责人；约定维护窗口、告警接收人、允许的摄像头与测试区域。备份数据库和配置，保存 V1 镜像 Digest、模型、配置和回滚命令。

## 1. 封版与供应链验真

```bash
make release-manifest VERSION=1.0.0
python3 scripts/model-inventory.py --strict
python3 scripts/security-release-scan.py --target \
  --image registry.example/linsight-server@sha256:REPLACE \
  --image registry.example/linsight-runtime@sha256:REPLACE
```

核对 `release-manifest.json` 必须包含 Git Commit、全部镜像 Digest、Java/Python/模型 SHA256、配置版本和构建时间。逐个模型确认来源 revision、下载地址、License、商用许可、输入尺寸和目标设备后端。任一正式模型缺失、哈希不符、空权重、Mock、同一二进制伪装或商用状态不明，停止验收。

## 2. 摄像头与基础运行预检

为每一路记录厂商、型号、固件、RTSP 主/子码流、分辨率、FPS、码率、白天/夜间模式和安装位置。运行现有现场预检：

```bash
make field-preflight-verify
make status
```

确认 Java、AI Runtime、模型、配置、摄像头、历史事件均正常；保存版本页面、健康检查、RTSP 探测和 Runtime snapshot。

## 3. 真实算法与车辆/车牌专项验收

按 `acceptance/datasets/README.md` 放入客户授权的真实图片/视频、标注和预测。不得用合成数据替代现场验收。车辆/车牌数据必须覆盖白天、夜间、逆光、雨天、模糊、污损、遮挡、小目标、倾斜、远距离、运动模糊、强光，并覆盖九类车辆与蓝牌、黄牌、新能源、大型车辆、双层车牌。

```bash
make algorithm-benchmark
```

逐算法签字确认 TP、FP、TN、FN、Precision、Recall、F1、误报率、漏报率、P50/P95/P99、FPS。车牌另核对中文省份字符、OCR 置信度、连续帧 Track ID、车辆绑定、多帧投票和稳定结果；任何单帧 OCR 直接形成最终结果均判失败。车牌透视矫正和双层牌必须以真实样本单列结果，不得合并进系统平均值。

## 4. Edge Capacity Benchmark

复制 `acceptance/edge-capacity.example.json` 为 `acceptance/edge-capacity.json`，填写目标硬件、摄像头码流和阈值。每档至少稳定运行 300 秒；建议生产签字档运行 30 分钟。运行期间 Java、AI、解码、网络、日志和补传必须同时开启。

每档启动 1/2/4/8/16/32 路后采集：

```bash
python3 scripts/capture-runtime-observability.py \
  --runtime-url http://127.0.0.1:9000 \
  --environment-name TARGET-EDGE --hardware "REPLACE" \
  --software-version 1.0.0 --run-id capacity-STREAMS \
  --java-pid JAVA_PID --duration-seconds 300 --interval-seconds 2 \
  --output acceptance/raw/capacity-STREAMS.json
python3 scripts/edge-capacity-benchmark.py --config acceptance/edge-capacity.json
```

达到硬件极限后在配置中显式写 `hardwareLimitReached=true`。报告必须给出最大稳定路数、按余量折算的推荐生产路数、CPU/内存/GPU/NPU 峰值、P95、FPS、丢帧和重连；理论模型 FPS 不作为容量结论。

## 5. Offline Chaos Test

复制并补全 `acceptance/offline-chaos.example.json`。对断网 5/10/30/60 分钟、DNS 失败、TCP 断开、HTTP Timeout、HTTP 500、HTTP 429、服务端不可达逐项配置显式命令和证据文件。HTTP 故障可使用：

```bash
python3 scripts/http-fault-endpoint.py --mode 429 --port 19090 \
  --log acceptance/raw/http-429.jsonl
python3 scripts/offline-chaos-test.py --config acceptance/offline-chaos.json --execute
```

每项验证摄像头和 AI 继续运行、事件与图片持久化、队列有界、磁盘安全；恢复后验证自动通信、补传、退避、去重、幂等、顺序、重启持久化，且事件/媒体生成数与上传数一致、重复和缺失均为 0。历史 30 分钟证据只能作为回归参考，当前候选版本仍须复验完整矩阵。

## 6. 监控与告警演练

部署 `deploy/monitoring/prometheus.yml`，导入 `deploy/monitoring/grafana/linsight-production-dashboard.json`，加载 `deploy/monitoring/rules/linsight-alerts.yml`。控制面投影导出器用环境变量传令牌：

```bash
python3 scripts/control-plane-metrics-exporter.py \
  --control-plane-url http://127.0.0.1:48080 --host 127.0.0.1 --port 9918
```

依次制造摄像头离线、磁盘 80%/90% 测试阈值、CPU/内存高压、模型加载失败、FPS/P95 异常、离线队列增长、补传超时和服务重启。每条告警验证触发、路由、值班人员收到、按 `docs/OPERATIONS_SOP.md` 处置、恢复自动关闭，并保留时间戳截图或 API 证据。

## 7. 升级失败与回滚

复制 `acceptance/rollback-drill.example.json`，只填经过复核的命令数组，环境必须是隔离的目标硬件。先确认 V1 备份可恢复，再执行：

```bash
python3 scripts/rollback-drill.py --config acceptance/rollback-drill.json --execute
```

演练必须真实执行 V1→V2、故障注入、失败检测、V2→V1，并逐项验证 Java 服务、AI 服务、模型、配置、摄像头、数据、历史事件。任一检查失败不得发布。

## 8. 汇总与交付判定

```bash
make production-readiness-report VERSION=1.0.0
make production-evidence-verify
```

`production-readiness-report` 只聚合已采集证据，不会用默认 WAITING 配置覆盖现场报告。
首次检查空白/缺失项时可使用 `make production-readiness-refresh` 生成全套等待态模板。

只有以下条件同时成立才可将阶段从 `Engineering Ready / Waiting For Field Acceptance` 升级为 `Production Ready`：模型供应链零阻断；所有核心算法达到客户签字阈值；容量有推荐路数；弱网零丢失零重复；Critical/High 清零；升级回滚成功；Dashboard 与全部关键告警闭环；所有证据绑定同一 Git Commit、镜像 Digest、模型 SHA 和配置版本。

## 一票否决

- 模型来源、License、商用授权、文件或 SHA256 任一不明。
- 核心算法漏报/误报超过签字阈值，或仅有系统平均值。
- 最大稳定路数/推荐路数未知，或容量测试未覆盖完整共载负荷。
- 离线事件、媒体丢失或重复，幂等/顺序/重启持久化未通过。
- 最终镜像或目标 OS 存在未处置的 Critical/High。
- V2 失败后无法恢复 V1 服务、模型、配置或历史数据。
- 监控看不到关键指标，或关键告警不能送达和闭环。
