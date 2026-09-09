package com.linsight.module.aivideo.controller.admin.camera.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - 摄像头安全响应，不包含码流路径和访问凭据")
@Data
public class CameraRespVO {
    private java.util.List<CameraCapabilityRespVO> recognitionCapabilities;

    private Long id;
    private String name;
    private String code;
    private Long groupId;
    private String protocol;
    private String host;
    private Integer port;
    private String maskedStreamEndpoint;
    private Boolean credentialConfigured;
    private Integer onlineStatus;
    private LocalDateTime lastOnlineTime;
    private LocalDateTime lastCheckTime;
    private String lastErrorCode;
    private String lastErrorMessage;
    private Integer status;
    private Integer version;
    private LocalDateTime createTime;

}
