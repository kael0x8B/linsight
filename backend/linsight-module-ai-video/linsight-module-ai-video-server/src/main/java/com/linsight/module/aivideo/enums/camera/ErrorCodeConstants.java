package com.linsight.module.aivideo.enums.camera;

import com.linsight.framework.common.exception.ErrorCode;

/**
 * Camera 领域错误码，使用 1-020-000-000 段。
 */
public interface ErrorCodeConstants {

    ErrorCode CAMERA_GROUP_NOT_FOUND = new ErrorCode(1_020_000_000, "摄像头分组不存在");
    ErrorCode CAMERA_GROUP_NAME_DUPLICATE = new ErrorCode(1_020_000_001, "同级下已存在该摄像头分组");
    ErrorCode CAMERA_GROUP_PARENT_ERROR = new ErrorCode(1_020_000_002, "不能将分组设置为自己的上级");
    ErrorCode CAMERA_GROUP_PARENT_IS_CHILD = new ErrorCode(1_020_000_003, "不能将分组移动到自己的下级");
    ErrorCode CAMERA_GROUP_HAS_CHILDREN = new ErrorCode(1_020_000_004, "分组存在下级分组，无法删除");
    ErrorCode CAMERA_GROUP_HAS_CAMERAS = new ErrorCode(1_020_000_005, "分组内存在摄像头，请先迁移摄像头");

    ErrorCode CAMERA_NOT_FOUND = new ErrorCode(1_020_000_100, "摄像头不存在");
    ErrorCode CAMERA_CODE_DUPLICATE = new ErrorCode(1_020_000_101, "摄像头编码已存在");
    ErrorCode CAMERA_MAIN_STREAM_REQUIRED = new ErrorCode(1_020_000_102, "主码流地址不能为空");
    ErrorCode CAMERA_PROTOCOL_INVALID = new ErrorCode(1_020_000_103, "摄像头接入协议不支持");
    ErrorCode CAMERA_STREAM_CHECK_NOT_FOUND = new ErrorCode(1_020_000_110, "摄像头检测任务不存在");
    ErrorCode CAMERA_STREAM_CHECK_STATE_INVALID = new ErrorCode(1_020_000_111, "摄像头检测任务状态不允许当前操作");
    ErrorCode CAMERA_STREAM_CHECK_NODE_MISMATCH = new ErrorCode(1_020_000_112, "摄像头检测任务不属于当前节点");
    ErrorCode CAMERA_PREVIEW_STREAM_NOT_CONFIGURED = new ErrorCode(1_020_000_120, "摄像头未配置所选码流");
    ErrorCode CAMERA_PREVIEW_RUNTIME_DISABLED = new ErrorCode(1_020_000_121, "预览 Runtime 未启用");
    ErrorCode CAMERA_PREVIEW_UNAVAILABLE = new ErrorCode(1_020_000_122, "预览启动失败，诊断 ID：{}");
    ErrorCode CAMERA_PREVIEW_SESSION_NOT_FOUND = new ErrorCode(1_020_000_123, "预览会话不存在或已过期");
    ErrorCode CAMERA_PREVIEW_SESSION_FORBIDDEN = new ErrorCode(1_020_000_124, "无权访问该预览会话");
    ErrorCode CAMERA_PREVIEW_MEDIA_NOT_READY = new ErrorCode(1_020_000_125, "预览媒体尚未就绪");
    ErrorCode CAMERA_PREVIEW_TUNNEL_NOT_CONNECTED = new ErrorCode(1_020_000_126,
            "边缘节点 {} 的预览通道未连接，诊断 ID：{}");

    ErrorCode VIDEO_WALL_LAYOUT_NOT_FOUND = new ErrorCode(1_020_000_130, "视频墙布局方案不存在");
    ErrorCode VIDEO_WALL_LAYOUT_SLOT_OCCUPIED = new ErrorCode(1_020_000_131, "该方案位置已有布局，请使用覆盖操作");
    ErrorCode VIDEO_WALL_LAYOUT_SPLIT_INVALID = new ErrorCode(1_020_000_132, "视频墙布局必须为 1/4/9/16 分屏，且摄像头位置与分屏数量一致");

}
