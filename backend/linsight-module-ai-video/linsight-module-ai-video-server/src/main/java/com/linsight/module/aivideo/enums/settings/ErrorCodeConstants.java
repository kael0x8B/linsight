package com.linsight.module.aivideo.enums.settings;

import com.linsight.framework.common.exception.ErrorCode;

/** Settings 领域错误码，使用 1-020-009-000 段。 */
public interface ErrorCodeConstants {
    ErrorCode SETTINGS_VERSION_CONFLICT = new ErrorCode(1_020_009_000, "全局参数已被其他操作更新，请刷新后重试");
    ErrorCode SETTINGS_GRAY_TASKS_REQUIRED = new ErrorCode(1_020_009_001, "灰度下发至少需要选择一个运行任务");
}
