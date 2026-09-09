package com.linsight.module.aivideo.controller.node.node.vo;

import lombok.Data;

@Data
public class NodeCommandRespVO {
    private String commandId;
    private String commandType;
    private Long aggregateId;
    private Integer configVersion;
    private String idempotencyKey;
}
