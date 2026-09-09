package com.linsight.module.aivideo.controller.node.node.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "节点端 - Edge Agent 心跳 Response VO")
@Data
public class NodeHeartbeatRespVO {

    private Long acceptedSequence;
    private LocalDateTime serverTime;
    private Long clockOffsetMillis;

}
