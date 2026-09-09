package com.linsight.module.aivideo.controller.node.camera.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Schema(description = "节点端 - 待执行摄像头连通检测 Response VO；仅返回给已认证的指定节点")
@Getter
@Setter
public class StreamCheckTaskRespVO {

    private Long checkId;
    private Long cameraId;
    private String protocol;
    private String host;
    private Integer port;
    @ToString.Exclude
    private String streamUri;
    @ToString.Exclude
    private String username;
    @ToString.Exclude
    private String password;

}
