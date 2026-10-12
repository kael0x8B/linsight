package com.linsight.module.aivideo.enums.task;

import com.linsight.framework.common.exception.ErrorCode;

/** Task 领域错误码，使用 1-020-003-000 段。 */
public interface ErrorCodeConstants {
    ErrorCode TASK_EVALUATION_NOT_FOUND = new ErrorCode(1_020_003_011, "评测记录不存在");
    ErrorCode TASK_EVALUATION_CONFIG_CHANGED = new ErrorCode(1_020_003_012, "任务配置已改变，请核对测试版本后重新记录");
    ErrorCode TASK_EVALUATION_REQUEST_CONFLICT = new ErrorCode(1_020_003_013, "评测请求编号已用于不同内容，请刷新后重新记录");
    ErrorCode TASK_EVALUATION_INVALID = new ErrorCode(1_020_003_014, "评测数据不完整或无效：{}");
    ErrorCode TASK_NOT_FOUND = new ErrorCode(1_020_003_000, "AI 任务不存在");
    ErrorCode TASK_CODE_DUPLICATE = new ErrorCode(1_020_003_001, "任务编码已存在");
    ErrorCode TASK_CODE_IMMUTABLE = new ErrorCode(1_020_003_002, "任务编码不可修改");
    ErrorCode TASK_STATUS_INVALID = new ErrorCode(1_020_003_003, "当前任务状态不允许执行该操作");
    ErrorCode TASK_CONFIG_INVALID = new ErrorCode(1_020_003_004, "任务配置不符合已发布 Pipeline 或模型门禁");
    ErrorCode TASK_RUN_NOT_FOUND = new ErrorCode(1_020_003_005, "任务运行记录不存在");
    ErrorCode TASK_REPORT_STALE = new ErrorCode(1_020_003_006, "任务状态上报的运行编号或配置版本已过期");
    ErrorCode TASK_MODEL_CAPABILITY_MISMATCH = new ErrorCode(1_020_003_007, "节点 {} 所选模型缺少必需类别：{}，请在模型中心选择支持该能力的版本");
    ErrorCode TASK_CONFIRMATION_LATENCY_CONFLICT = new ErrorCode(1_020_003_008,
            "预计最短确认时延 {} 秒，超过 2 秒目标；请提高分析帧率或降低规则连续帧/持续时间");
    ErrorCode TASK_MODEL_CAPACITY_EXCEEDED = new ErrorCode(1_020_003_009, "任务启动容量预检未通过：{}");
    ErrorCode TASK_STREAM_CONFLICT = new ErrorCode(1_020_003_010,
            "同一网关上的摄像头已有使用其他码流的识别任务，请先停止该任务后再切换码流");
}
