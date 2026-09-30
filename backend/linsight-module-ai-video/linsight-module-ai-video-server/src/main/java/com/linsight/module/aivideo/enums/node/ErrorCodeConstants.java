package com.linsight.module.aivideo.enums.node;

import com.linsight.framework.common.exception.ErrorCode;

/**
 * Node 领域错误码，使用 1-020-006-000 段。
 */
public interface ErrorCodeConstants {

    ErrorCode NODE_BOOTSTRAP_TOKEN_INVALID = new ErrorCode(1_020_006_000, "节点注册令牌无效或已使用");
    ErrorCode NODE_BOOTSTRAP_TOKEN_EXPIRED = new ErrorCode(1_020_006_001, "节点注册令牌已过期");
    ErrorCode NODE_CODE_DUPLICATE = new ErrorCode(1_020_006_002, "节点编码已存在");
    ErrorCode NODE_AUTHENTICATION_FAILED = new ErrorCode(1_020_006_003, "节点身份认证失败");
    ErrorCode NODE_HEARTBEAT_SEQUENCE_STALE = new ErrorCode(1_020_006_004, "节点心跳序号已过期");
    ErrorCode NODE_NOT_AVAILABLE = new ErrorCode(1_020_006_005, "边缘节点不存在、已停用或当前离线");
    ErrorCode NODE_COMMAND_NOT_FOUND = new ErrorCode(1_020_006_010, "节点命令不存在或不属于当前节点");
    ErrorCode NODE_COMMAND_TYPE_INVALID = new ErrorCode(1_020_006_011, "节点命令类型不支持");
    ErrorCode NODE_COMMAND_STATUS_INVALID = new ErrorCode(1_020_006_012, "节点命令状态不允许当前操作");
    ErrorCode NODE_UPGRADE_NOT_FOUND = new ErrorCode(1_020_006_020, "节点升级或回滚记录不存在");
    ErrorCode NODE_UPGRADE_PACKAGE_INVALID = new ErrorCode(1_020_006_021, "升级包必须为 64MB 内的非空 tar.gz/tgz 文件");
    ErrorCode NODE_UPGRADE_IN_PROGRESS = new ErrorCode(1_020_006_022, "节点已有正在执行的升级或回滚命令");
    ErrorCode NODE_UPGRADE_GUARD_REQUIRED = new ErrorCode(1_020_006_023, "节点尚未启用升级健康守护，请先执行一次在线重新部署");
    ErrorCode NODE_UPGRADE_ROLLBACK_UNAVAILABLE = new ErrorCode(1_020_006_024, "节点没有可回滚的签名 Agent 版本；源码部署请使用完整部署回滚");
    ErrorCode NODE_UPGRADE_VERSION_UNCHANGED = new ErrorCode(1_020_006_025, "目标版本与当前运行版本相同，请使用新的不可变版本号");
    ErrorCode NODE_LOG_NOT_FOUND = new ErrorCode(1_020_006_030, "节点日志不存在");
    ErrorCode NODE_DIAGNOSTIC_RANGE_INVALID = new ErrorCode(1_020_006_031, "诊断时间范围必须在最近 7 天内且不超过 24 小时");
    ErrorCode NODE_DIAGNOSTIC_NOT_FOUND = new ErrorCode(1_020_006_032, "节点诊断包不存在");
    ErrorCode NODE_DEPLOYMENT_DISABLED = new ErrorCode(1_020_006_040, "控制台节点部署功能未启用");
    ErrorCode NODE_DEPLOYMENT_NOT_FOUND = new ErrorCode(1_020_006_041, "节点部署记录不存在");
    ErrorCode NODE_DEPLOYMENT_PREFLIGHT_FAILED = new ErrorCode(1_020_006_042, "节点连接或环境预检失败：{} ");
    ErrorCode NODE_DEPLOYMENT_HOST_KEY_CHANGED = new ErrorCode(1_020_006_043, "SSH 主机指纹已变化，请重新执行预检并确认");
    ErrorCode NODE_LIFECYCLE_IN_PROGRESS = new ErrorCode(1_020_006_050, "节点已有部署、升级或运维操作；请在操作记录中完成/激活后重试");
    ErrorCode NODE_DELETE_ONLINE = new ErrorCode(1_020_006_051, "在线节点不能删除，请先关机并等待节点离线");
    ErrorCode NODE_TASK_REMOVE_FAILED = new ErrorCode(1_020_006_053, "网关配置未移除，请确认网关已升级并在线，刷新状态后重试");
    ErrorCode NODE_TASK_CAPACITY_PREFLIGHT_FAILED = new ErrorCode(1_020_006_054, "网关任务容量预检失败：{}");
    ErrorCode NODE_DELETE_REFERENCED = new ErrorCode(1_020_006_052, "节点仍有关联任务，请先迁移或删除任务");

}
