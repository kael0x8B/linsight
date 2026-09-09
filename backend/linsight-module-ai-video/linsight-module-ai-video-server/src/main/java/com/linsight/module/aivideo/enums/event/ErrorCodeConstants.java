package com.linsight.module.aivideo.enums.event;

import com.linsight.framework.common.exception.ErrorCode;

/** Event 领域错误码，使用 1-020-005-000 段。 */
public interface ErrorCodeConstants {
    ErrorCode EVENT_NOT_FOUND = new ErrorCode(1_020_005_000, "事件不存在");
    ErrorCode EVENT_STATUS_INVALID = new ErrorCode(1_020_005_001, "当前事件状态不允许此操作");
    ErrorCode EVENT_NODE_MISMATCH = new ErrorCode(1_020_005_002, "事件不属于当前节点");
    ErrorCode EVENT_MEDIA_INVALID = new ErrorCode(1_020_005_003, "事件证据文件无效");
}
