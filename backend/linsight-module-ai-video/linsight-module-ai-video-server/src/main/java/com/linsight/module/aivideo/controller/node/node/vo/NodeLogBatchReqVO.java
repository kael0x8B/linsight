package com.linsight.module.aivideo.controller.node.node.vo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;

@Data
public class NodeLogBatchReqVO {
    @Valid
    @NotEmpty
    @Size(max = 100)
    private List<NodeLogEntryReqVO> entries;
}
