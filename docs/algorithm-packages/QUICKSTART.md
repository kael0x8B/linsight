# 算法开发者快速入门

适用于 SDK 1.0。沿用现有 Python Runtime、算法 ZIP 和模型角色绑定，不需要启动 Java、数据库或摄像头即可验证处理逻辑。

## 1. 安装与生成示例

使用 Python 3.12 或 3.13，在仓库根目录执行：

```bash
cd runtime
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m ai_runtime.sdk init /tmp/hello-person
```

安装后也可用 `linsight-sdk` 替代 `python -m ai_runtime.sdk`。`init` 不覆盖已有目录，生成 `algorithm.json`、`processor.py`、README、`fixtures/frame.json` 和 `fixtures/expected.json`。

示例通过 `sdk.infer("person")` 获取固定模型响应，按置信度过滤人员并返回候选。网关使用同一个 `PackageRunner`，模型响应由绑定的真实模型提供。

## 2. 校验与回归

```bash
python -m ai_runtime.sdk check /tmp/hello-person
python -m ai_runtime.sdk run /tmp/hello-person \
  --fixture /tmp/hello-person/fixtures/frame.json \
  --expect /tmp/hello-person/fixtures/expected.json \
  --output /tmp/sdk-result.json
```

预期 `status: PASS`、`source: SDK_FIXTURE`，输出一个人员候选。修改 `processor.py` 后重复执行同一命令。`--expect` 精确比较标准化后的 `objects` 与 `observationValid`；不传该参数时只验证执行及输出契约，不表示效果达标。`--parameters parameters.json` 可替换 manifest 中的默认参数。

退出码：`0` 校验/执行/比较成功，`1` 执行失败或期望不一致，`2` 输入、文件或包契约无效。`check` 不导入代码；导入、初始化和执行由 `run` 验证。

fixture 使用空白画布及合成检测结果，**不执行真实 ONNX/RKNN 推理，不测量视频准确率、时延或规则时序**。`modelResults` 的 key 必须匹配模型角色；裁剪 fixture 的对象坐标以裁剪区域为基准。入门运行器不模拟 embedding 或人员参考库，这类算法通过真实节点验证。完整 SDK 契约见 [README](README.md)。

## 3. 定位错误

在 `process` 内临时加入 `raise ValueError("debug")` 后运行上一条命令。错误写入 stderr 和 `--output` JSON：

```json
{
  "status": "ERROR",
  "source": "SDK_FIXTURE",
  "error": {
    "schemaVersion": "1.0",
    "code": "ALGORITHM_PROCESS_FAILED",
    "stage": "PROCESS",
    "exceptionType": "ValueError",
    "frames": [{"file": "processor.py", "line": 3, "function": "process"}],
    "packageCode": "hello-person",
    "packageVersion": "0.1.0",
    "timestampMillis": 1000
  }
}
```

实际报告还包含 `diagnosticId`、`packageSha256` 和固定修复提示。定位保留包内相对文件名、行号和函数，最多 6 层；不返回异常原文、绝对路径、变量或源码。`print` 不作为协议输出。错误码及控制台入口见 [开发者基础能力](../DEVELOPER_FOUNDATION.md)。

## 4. 打包与真实视频评测

恢复正确代码后：

```bash
python -m ai_runtime.sdk pack /tmp/hello-person --output /tmp/hello-person.zip
```

同一内容使用固定文件顺序、时间和权限，得到相同 SHA256。`pack` 不覆盖已有 ZIP；发布新逻辑前提升 manifest 版本并输出到新路径。允许 `.py/.json/.txt/.md`，忽略隐藏目录、缓存及根目录下的 `fixtures/tests`，拒绝符号链接。模型、虚拟环境、输出 ZIP 应放在包目录外。与生产安装共用 8 MB 压缩、32 MB 解压和 128 文件限制。

在算法中心上传 ZIP，按 manifest 声明绑定兼容的模型版本；权重仍由模型域管理。选择规则与任务参数，在网关运行固定视频测试，保留数据集清单哈希、视频时长、硬件/Runtime 版本及结果报告。原“视频识别验收”入口现在展示“视频评测记录”：选择任务，核对平台配置与网关修订，填写真实指标、阈值和证据引用后保存。

SDK fixture 不能冒充实测评测。本轮视频评测为人工录入并明确标记 `MANUAL_VIDEO`，不会自动发布 Pipeline。视频调试器、自动事件指标计算与规则回放不在本轮范围内。算法包应来自可信开发者，进程隔离不是不可信代码的安全沙箱。
