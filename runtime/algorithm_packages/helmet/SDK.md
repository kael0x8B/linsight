# 可部署算法包（SDK 1.0）

从 Git 基线 `c691cb2` 增加。架构决策见 [ADR](../adr/ADR-20260909-deployable-algorithm-packages.md)。

## 操作方式

已有算法无需重新打包即可通过任务编排使用；入口与逐步操作见 [使用指南](USAGE.md)。

1. 在模型中心上传模型，完成原有格式、来源、授权和单图验证。默认目录按已发布、可执行的具体模型版本展示；历史资产仍在“资产与历史版本”。
2. 在算法中心上传供应方的 ZIP。上传校验不执行其中的 Python；检查用途、类型、依赖和配置项后发布。
3. 进入目标网关 → 识别算法 → 添加识别算法。选择摄像头和算法，系统解析兼容模型。确认精确版本后，未安装的模型先下发并等待 READY，再保存和启动配置。
4. 启停只作用于当前网关。配置固定引用算法包 SHA256、PipelineVersion 和每个模型角色的 ModelVersion；发布新包不会升级运行中的配置。
5. 不选择告警规则时展示标准识别结果；选择规则后沿用规则引擎的连续帧、冷却、去重、证据和离线上传机制。规则选项按所选包版本的 `eventType` 匹配。
6. 停止后可以移除识别配置。平台先确认网关已释放该配置，再移除平台记录；网关不可达时保留记录，恢复连接后重试。历史事件保留。

平台下发时自动安装算法包，不增加服务或要求逐台安装。网关升级到 SDK 1.0 后可以重复使用。
本地入口可安装 ZIP、使用已安装模型创建配置、编辑算法参数和启停；平台部署的同一份配置断开平台后继续运行，重启后自动恢复。
人员库算法的本地编辑使用此前授权同步到该配置的人员，可缩小比对范围。新人员库/新增人员及新版特征需要在平台准备并同步；SDK 1.0 不包含独立的人像采集建库界面。

## 算法与模型的边界

- 模型提供推理能力；算法包提供输出解释、模型组合、时序或业务判定。安全帽、反光衣、区域、人脸的示例业务代码位于各自包中。
- 主程序负责一台摄像头共享解码、模型池、工作进程、帧时钟、跟踪、规则、证据和命令回执。
- 未使用包的历史 Pipeline 和入口刷脸配置保留原执行路径。迁移由操作者选择，不能自动替换正在使用的模型或参数。
- 无须修改平台代码的前提是模型符合已有输入/输出契约、目标设备支持该格式，并且包使用 SDK 1.0。任意二进制、任意输出张量和未安装的第三方依赖不在此承诺内。

## 包结构

ZIP 根目录包含 `algorithm.json` 和入口 `.py`，可带其他 Python/JSON/说明文件。最大 8 MB，展开最大 32 MB、128 个文件；模型权重独立上传。版本不可覆盖；修改任何字节必须增加版本号。

```json
{
  "schemaVersion": "1.0", "sdkVersion": "1.0",
  "code": "supplier-zone", "version": "1.0.0", "name": "指定区域检测",
  "category": "REGION", "eventType": "AREA_INTRUSION",
  "entrypoint": "processor.py", "timeoutMillis": 5000,
  "models": [{"slot": "person", "name": "人员检测", "taskType": "OBJECT_DETECTION", "formats": ["ONNX", "RKNN"], "labels": ["person"]}],
  "parameterSchema": {"type": "object", "properties": {"confidence": {"type": "number", "title": "置信度", "minimum": 0.01, "maximum": 1}}, "required": ["confidence"], "additionalProperties": false},
  "defaultParameters": {"confidence": 0.5}
}
```

类别：`PPE`、`IDENTITY`、`BEHAVIOR`、`REGION`、`OCR`、`SCENE`、`GENERAL`。分类用于目录展示；不会选择业务代码。
`eventType` 声明候选事件对应的规则类型，缺省为 `ALGORITHM_EVENT`。它随包版本固定；发布新版不会改变旧配置的规则匹配。示例包 1.0.1 分别使用 `SAFETY_HELMET`、`REFLECTIVE_VEST`、`AREA_INTRUSION` 和 `FACE_IDENTIFICATION`。
模型角色按任务类型、格式和标准标签匹配，可绑定同一具体模型版本；共享模型只推理一次。

参数支持对象、数字、整数、布尔、字符串、基础数组，必填、枚举、范围和长度限制。界面按描述生成表单，参数放入 `parameters.algorithm`，不能由旧字段覆盖。
界面扩展：`x-widget: roi` 使用归一化矩形，`person-library` 选择人员库，`people` 选择人员（`x-library-field` 指定关联库字段）。实际示例见 `runtime/algorithm_packages/face/algorithm.json`。

```python
class Algorithm:
    def process(self, frame, sdk):
        objects = []
        for obj in frame["objects"]:
            if obj["class"] == "person" and obj["confidence"] >= frame["parameters"]["confidence"]:
                obj["attributes"] = {
                    **obj.get("attributes", {}),
                    "displayLabel": "人员",
                    "eventCandidate": False,
                }
                objects.append(obj)
        return {"objects": objects}
```

`frame` 包含当前帧对象、源尺寸、毫秒时间、算法参数和授权资源摘要；不包含 RTSP、平台令牌、下载地址和服务器文件路径。
输出对象字段沿用统一契约：`class`、`confidence`、`bbox{x,y,width,height}`（0–1）、`attributes`，可选 `trackId`。`displayLabel` 是纯文本；`eventCandidate` 仅表示候选，真正事件继续由规则确认。

### 通用结果展示契约

`bbox` 和 `confidence` 是参与跟踪、ROI 和规则的目标检测结果。需要展示局部证据、其他判断分数或结果状态时，在 `attributes` 中声明以下兼容 SDK 1.0 的字段。沿用已有标量属性通道，控制面、Runtime、Agent 和离线存储均透传，不增加算法类型分支。

| 字段 | 语义 |
| --- | --- |
| `displayBoxX / displayBoxY / displayBoxWidth / displayBoxHeight` | 四个字段一起提供，源图归一化展示框。必须有限、宽高大于零且不越界；缺少或无效时回退到目标 bbox。 |
| `displayLabel` | 纯文本结果名称，最多显示 100 字符；只控制文字，不覆盖位置或分数。 |
| `displayConfidence` | 结果判断的 0–1 分数；显式 null 表示不展示分数。省略时使用目标分数；无效值不显示。 |
| `displayState` | `alert`、`normal`、`unknown`、`neutral`；控制结果语义色。unknown 隐藏判断分数。语义色优先于算法图层的标识颜色。 |
| `visibleByDefault` | 可选布尔值；省略时 alert/neutral 显示，normal/unknown 隐藏，可通过页面“显示合规与待确认目标”查看。 |

新算法包通过这些字段表达结果，不依赖旧版 PPE 专用属性。历史内置编排由固定的兼容适配器处理；旧包未提供展示字段时仍能显示原目标。平台实时预览、网关工作台、本地入口和截图共用一个绘制器。视频插值独立处理目标框和展示框，不插值分数，不跨结果状态/标签变化，不把平滑结果写回规则或证据。

安全帽、反光衣包 1.0.2 默认显示模型实际检测部位及穿戴分数；匹配不到证据时保持待确认，不按人体比例捏造头部框。包声明的 `showPersonBox`（显示人员全身框）仅改变展示框，不改变模型绑定、原目标、ROI 或告警候选。这个选项由已有 Schema 表单生成，不需要为该算法编写专用前端。

SDK 调用：

- `sdk.infer(slot, region=None)`：通过共享模型池对当前帧/裁剪区域推理；裁剪结果坐标相对裁剪图，需要算法映射回源图。
- `sdk.extract_embedding(slot, region=None)`：人脸特征。无合格人脸时 `embedding` 为空；不等于身份不匹配。
- `sdk.reference_embedding(resource_key, entry_id)`：仅允许引用该配置已同步、未过期的参考人员。参考图片由主程序校验并提取特征。

每帧最多 32 次 SDK 调用；结果最多 512 个对象、4 MB。处理默认 3 秒，可设置 100–30000 毫秒。错误、超时会回收工作进程并上报任务失败；旧任务不会切换到新逻辑。
算法进程使用网关现有 Python 环境。供应方可随包提供纯 Python 模块；SDK 1.0 不自动运行 pip、安装脚本或扩展原生依赖。
进程隔离用于故障控制，不是运行不可信代码的安全沙箱。只有经过审核的代码包才能获得发布权限。

## 人员库资源

人脸包声明 `resources`，将配置字段与资源/模型角色绑定：

```json
{"key":"people","type":"FACE_LIBRARY","parameter":"libraryId","selectionParameter":"personIds","modelSlot":"face"}
```

控制面按租户、库状态、人员状态、特征模型版本及有效期读取引用；Agent 校验 SHA256 后复制到 Runtime 私有目录。浏览器和子进程均不获得下载地址和本地路径。
此示例提供身份比对，不包含活体检测或通行控制，也不替代现有入口主动刷脸流程的业务验收。

## 示例与验证

运行 `python3 scripts/build-algorithm-packages.py` 生成可上传包：安全帽、反光衣、区域入侵、人员库刷脸、跌倒和车辆违停。
构建固定 ZIP 元数据，相同源文件得到相同哈希。示例用于验证扩展契约和配置流程，实际识别效果取决于所选模型、摄像头和阈值，须按场景验收。

针对包运行 `runtime/.venv/bin/python -m pytest runtime/tests/test_algorithm_packages.py`；包验证的 Java 测试为 `AlgorithmPackageValidatorTest`。
同版本覆盖、SDK 不匹配、路径越界、哈希/文件变化、错误参数、错误模型角色应被拒绝；独立进程超时、SDK 调用、资源脱敏、平台/本地配置冲突及离线恢复均有测试。

## 默认告警条件（兼容 SDK 1.0）

`algorithm.json` 可声明可选 `defaultRule`，内容为现有 Rule AST 1.0。事件类型必须与算法的 `eventType` 一致；上传时控制面和 Runtime 都校验规则。该字段只是新配置的初始值，不在包内执行第二套时序判断，也不会覆盖已有任务。

新建配置在“告警条件”调整区域、N/M、持续时间、静止容差和告警间隔；平台保存为独立的不可变规则版本。本地入口保存同一份 Rule AST 随网关配置离线运行。模板复制后不会联动更改其他任务。没有规则时只展示候选识别结果。

跌倒示例 `fall-detection-package` 只接受模型输出的 `fall` 类别；违停示例 `vehicle-parking-package` 使用车辆检测、统一跟踪和 `STATIONARY` 规则。发布或运行成功都不自动形成现场效果验收结论。
