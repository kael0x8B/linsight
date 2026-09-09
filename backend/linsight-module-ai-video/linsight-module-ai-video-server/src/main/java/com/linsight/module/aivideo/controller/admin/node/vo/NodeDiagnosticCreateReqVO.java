package com.linsight.module.aivideo.controller.admin.node.vo;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

import java.time.LocalDateTime;

@Data
public class NodeDiagnosticCreateReqVO {
    @NotNull
    private Long nodeId;
    private Long taskId;
    @NotNull
    private LocalDateTime rangeStart;
    @NotNull
    private LocalDateTime rangeEnd;
}
