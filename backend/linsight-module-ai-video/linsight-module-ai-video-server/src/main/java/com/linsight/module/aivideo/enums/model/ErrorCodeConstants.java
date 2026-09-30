package com.linsight.module.aivideo.enums.model;

import com.linsight.framework.common.exception.ErrorCode;

/** Model 领域错误码，使用 1-020-001-000 段。 */
public interface ErrorCodeConstants {
    ErrorCode MODEL_UNINSTALL_UNSUPPORTED = new ErrorCode(1_020_001_028, "当前网关尚不支持模型卸载，请先在线升级网关");
    ErrorCode MODEL_NODE_INCOMPATIBLE = new ErrorCode(1_020_001_029, "模型与目标网关不兼容：{}");
    ErrorCode MODEL_NOT_FOUND = new ErrorCode(1_020_001_000, "模型资产不存在");
    ErrorCode MODEL_CODE_DUPLICATE = new ErrorCode(1_020_001_001, "模型编码已存在");
    ErrorCode MODEL_HAS_VERSIONS = new ErrorCode(1_020_001_002, "模型已有版本，不能删除");
    ErrorCode MODEL_VERSION_DUPLICATE = new ErrorCode(1_020_001_010, "模型版本标识已存在");
    ErrorCode MODEL_ARTIFACT_DUPLICATE = new ErrorCode(1_020_001_011, "相同 SHA256 的模型文件已登记");
    ErrorCode MODEL_ARTIFACT_EMPTY = new ErrorCode(1_020_001_012, "模型文件为空");
    ErrorCode MODEL_FORMAT_UNSUPPORTED = new ErrorCode(1_020_001_013, "模型文件格式不支持");
    ErrorCode MODEL_VERSION_NOT_FOUND = new ErrorCode(1_020_001_014, "模型版本不存在");
    ErrorCode MODEL_VERSION_VALIDATION_BLOCKED = new ErrorCode(1_020_001_016, "模型格式校验未通过，禁止发布");
    ErrorCode MODEL_SOURCE_INCOMPLETE = new ErrorCode(1_020_001_017, "模型来源仓库或固定 revision 缺失，禁止发布");
    ErrorCode MODEL_ARTIFACT_TOO_LARGE = new ErrorCode(1_020_001_018, "当前模型直传通道最大支持 64MB");
    ErrorCode MODEL_ADAPTER_ONNX_REQUIRED = new ErrorCode(1_020_001_020,
            "当前模型没有受控 Runtime 适配器，或制品格式不支持直接执行");
    ErrorCode MODEL_VERSION_NOT_PUBLISHED = new ErrorCode(1_020_001_021, "模型版本尚未完成目录发布");
    ErrorCode MODEL_DEPLOYMENT_NOT_FOUND = new ErrorCode(1_020_001_022, "模型部署记录不存在");
    ErrorCode MODEL_DEPLOYMENT_NOT_READY = new ErrorCode(1_020_001_023, "模型尚未在所选节点进入 ready 状态");
    ErrorCode MODEL_TEST_IMAGE_INVALID = new ErrorCode(1_020_001_024, "测试图片必须是 10MB 内的 JPEG、PNG 或 WebP");
    ErrorCode MODEL_TEST_NOT_FOUND = new ErrorCode(1_020_001_025, "单图测试记录不存在");
    ErrorCode MODEL_TEST_RESULT_INVALID = new ErrorCode(1_020_001_026, "节点返回的标准化检测结果不符合 V1 契约");
    ErrorCode MODEL_RUNTIME_MANIFEST_INVALID = new ErrorCode(1_020_001_027,
            "模型 Runtime Manifest 缺失或不符合 V1 执行契约");
}
