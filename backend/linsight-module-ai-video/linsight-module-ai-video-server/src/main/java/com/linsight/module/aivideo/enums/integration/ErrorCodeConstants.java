package com.linsight.module.aivideo.enums.integration;

import com.linsight.framework.common.exception.ErrorCode;

/** Integration 领域错误码，使用 1-020-008-000 段。 */
public interface ErrorCodeConstants {
    ErrorCode WEBHOOK_NOT_FOUND = new ErrorCode(1_020_008_000, "Webhook 端点不存在");
    ErrorCode WEBHOOK_URL_UNSAFE = new ErrorCode(1_020_008_001, "Webhook 地址必须是可解析的公网 HTTPS 地址");
    ErrorCode WEBHOOK_DELIVERY_NOT_FOUND = new ErrorCode(1_020_008_002, "Webhook 投递记录不存在");
    ErrorCode WEBHOOK_DELIVERY_NOT_REPLAYABLE = new ErrorCode(1_020_008_003, "只有死信投递可以重放");
}
