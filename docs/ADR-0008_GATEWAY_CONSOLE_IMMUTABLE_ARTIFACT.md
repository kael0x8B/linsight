# ADR-0008：网关控制台使用独立不可变制品

- 状态：Accepted
- 日期：2026-09-11
- 范围：Vue 网关入口、Runtime、Node 在线部署与发布流程

## 背景

网关控制台由 Vue 构建产生，历史上直接展开到 `runtime/edge_agent/app/console/` 并纳入 Git。
构建工具为 JS/CSS 文件生成内容 hash，一次普通页面修改会表现为数百个删除和新增，淹没业务源码 Diff，
也无法仅凭目录回答某台节点使用的是哪个完整网页制品。Runtime 与 Agent 源码已有确定性打包和 SHA256，
但网页资源缺少自己的 manifest、文件清单及独立完整性校验。

## 决策

1. 网关控制台构建输出改为 `runtime/gateway-console/`，该目录由 Git 忽略，不再跟踪展开后的 JS/CSS。
2. 构建生成确定性的 `gateway-console-<sha256前12位>.tar.gz` 和 `manifest.json`。Manifest 记录 Schema、
   前端源码摘要、制品 SHA256、大小、入口文件以及全部静态文件的路径、大小和 SHA256。
   构建元数据时间使用标准 `SOURCE_DATE_EPOCH`；仓库脚本默认取当前 Git commit 时间，避免墙钟时间使
   相同源码产生不同 chunk hash。无 Git 的发布环境必须显式提供该值。
3. 本地运行和节点部署都使用同一个校验/安装程序。安装先验证 manifest 与制品，再限制文件数量、
   解压总量及归档路径，拒绝链接和设备文件，最后复核逐文件摘要并原子替换 `current/`。
4. Node 在线部署仍只有一个最终 Runtime 包版本。控制面在打包阶段校验并纳入控制台 manifest 与制品；
   节点在停止旧服务前再次验证和展开。因此控制台变化会改变 Runtime 包 SHA256，但不再污染源码审查。
5. Runtime 从 `runtime/gateway-console/current/` 提供本地管理页面。旧 HLS/WebRTC、任务、事件、模型和
   Agent 协议均不因本决策改变。

## 备选方案

- 继续提交展开目录：部署简单，但持续制造大规模 hash 文件删增，缺少独立供应链身份，不采用。
- 只提交一个固定名称 ZIP：减少文件数，但没有内容寻址、逐文件清单和安全解包约束，不采用。
- 节点运行时从互联网 CDN 下载：增加外部可用性与供应链依赖，不符合边缘离线部署要求，不采用。

## 兼容、迁移与回滚

首次迁移执行 `make gateway-console` 生成制品，并从 Git 删除旧 `runtime/edge_agent/app/console/` 生成目录。
旧节点不受影响；只有执行新部署时才切换到新目录。部署快照继续覆盖完整 `/opt/linsight/runtime`，因此
健康检查失败时恢复旧 Runtime 和旧网页资源。回滚应用源码时须同时提供该版本 manifest 引用的制品。

## 验收

- 相同前端输入重复构建得到相同控制台归档 SHA256。
- 篡改归档或 manifest 文件清单会在安装前失败，现有 `current/` 保持可用。
- Runtime 包缺少控制台制品或摘要不匹配时，控制面拒绝开始节点切换。
- 新部署通过 `48901/gateway-health` 与首页健康检查，回滚后恢复上一版本页面。
- 前端构建不再造成 `runtime/edge_agent/app/console/` 下数百个 Git 删除和新增。
