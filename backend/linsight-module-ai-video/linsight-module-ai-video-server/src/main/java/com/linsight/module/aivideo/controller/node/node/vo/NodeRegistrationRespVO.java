package com.linsight.module.aivideo.controller.node.node.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.ToString;

@Schema(description = "节点端 - Edge Agent 注册 Response VO；长期凭据只返回一次")
@Data
public class NodeRegistrationRespVO {

    private Long nodeId;
    private Long tenantId;
    @ToString.Exclude
    private String credential;

}
