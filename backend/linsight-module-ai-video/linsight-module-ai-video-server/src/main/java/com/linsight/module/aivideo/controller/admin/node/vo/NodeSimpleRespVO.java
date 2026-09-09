package com.linsight.module.aivideo.controller.admin.node.vo;

import lombok.Data;

@Data
public class NodeSimpleRespVO {
    private Long id;
    private String code;
    private String name;
    private String agentVersion;
    private Integer onlineStatus;
    private Boolean previewTunnelConnected;
    private Integer status;
}
