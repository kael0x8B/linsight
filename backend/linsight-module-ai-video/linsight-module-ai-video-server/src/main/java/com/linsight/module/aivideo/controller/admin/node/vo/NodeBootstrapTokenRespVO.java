package com.linsight.module.aivideo.controller.admin.node.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.ToString;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - 节点一次性注册令牌 Response VO；令牌只返回一次")
@Data
public class NodeBootstrapTokenRespVO {

    @ToString.Exclude
    private String token;
    private LocalDateTime expireTime;

}
