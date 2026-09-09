package com.linsight.module.aivideo.controller.admin.node.vo;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class NodeRespVO {
    private Long id;
    private Long taskCount;
    private Long modelCount;
    private String code;
    private String name;
    private String agentVersion;
    private String hostName;
    private String ipAddress;
    private Integer onlineStatus;
    private Boolean previewTunnelConnected;
    private LocalDateTime lastHeartbeatTime;
    private Long clockOffsetMillis;
    private String resourceSnapshot;
    private Integer status;
}
