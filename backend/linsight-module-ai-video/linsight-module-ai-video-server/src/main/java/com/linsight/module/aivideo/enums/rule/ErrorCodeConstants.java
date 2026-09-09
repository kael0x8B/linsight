package com.linsight.module.aivideo.enums.rule;

import com.linsight.framework.common.exception.ErrorCode;

/** Rule 领域错误码，使用 1-020-004-000 段。 */
public interface ErrorCodeConstants {
    ErrorCode RULE_NOT_FOUND = new ErrorCode(1_020_004_000, "规则不存在");
    ErrorCode RULE_CODE_DUPLICATE = new ErrorCode(1_020_004_001, "规则编码已存在");
    ErrorCode RULE_CODE_IMMUTABLE = new ErrorCode(1_020_004_002, "规则编码不可修改");
    ErrorCode RULE_VERSION_NOT_FOUND = new ErrorCode(1_020_004_010, "规则版本不存在");
    ErrorCode RULE_AST_INVALID = new ErrorCode(1_020_004_011, "规则 AST 校验失败");
    ErrorCode RULE_VERSION_NOT_PUBLISHED = new ErrorCode(1_020_004_012, "规则版本尚未发布");
    ErrorCode RULE_RUNTIME_UNAVAILABLE = new ErrorCode(1_020_004_013, "节点规则试算不可用，请确认节点在线并重新部署最新 Agent（诊断 ID：{}）");
}
