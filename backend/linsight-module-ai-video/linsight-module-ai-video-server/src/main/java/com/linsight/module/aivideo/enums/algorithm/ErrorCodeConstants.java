package com.linsight.module.aivideo.enums.algorithm;

import com.linsight.framework.common.exception.ErrorCode;

/** Algorithm 领域错误码，使用 1-020-002-000 段。 */
public interface ErrorCodeConstants {
    ErrorCode ALGORITHM_NOT_FOUND = new ErrorCode(1_020_002_000, "算法不存在");
    ErrorCode ALGORITHM_CODE_DUPLICATE = new ErrorCode(1_020_002_001, "算法编码已存在");
    ErrorCode ALGORITHM_CODE_IMMUTABLE = new ErrorCode(1_020_002_002, "算法编码使用后不可修改");
    ErrorCode PIPELINE_NOT_FOUND = new ErrorCode(1_020_002_010, "Pipeline 版本不存在");
    ErrorCode PIPELINE_INVALID = new ErrorCode(1_020_002_011, "Pipeline DAG 校验失败");
    ErrorCode PIPELINE_NOT_PUBLISHED = new ErrorCode(1_020_002_012, "Pipeline 尚未发布");
    ErrorCode PIPELINE_ACCEPTANCE_BLOCKED = new ErrorCode(1_020_002_013,
            "Pipeline 生产验收未通过，当前状态：{}");
    ErrorCode FACE_EXTRACTION_INVALID = new ErrorCode(1_020_002_026, "无法提取人脸特征：{}");
    ErrorCode RECOGNITION_LIBRARY_NOT_FOUND = new ErrorCode(1_020_002_020, "识别参考库不存在");
    ErrorCode RECOGNITION_LIBRARY_CODE_DUPLICATE = new ErrorCode(1_020_002_021, "识别参考库编码已存在");
    ErrorCode RECOGNITION_LIBRARY_IDENTITY_IMMUTABLE = new ErrorCode(1_020_002_022,
            "识别参考库编码、类型和条目归属不可修改");
    ErrorCode RECOGNITION_LIBRARY_NOT_EMPTY = new ErrorCode(1_020_002_023,
            "识别参考库仍有条目，请先清空后删除");
    ErrorCode RECOGNITION_LIBRARY_ENTRY_NOT_FOUND = new ErrorCode(1_020_002_024, "识别参考条目不存在");
    ErrorCode RECOGNITION_LIBRARY_ENGINE_NOT_READY = new ErrorCode(1_020_002_025,
            "识别引擎模型版本尚未发布或不可执行");
}
