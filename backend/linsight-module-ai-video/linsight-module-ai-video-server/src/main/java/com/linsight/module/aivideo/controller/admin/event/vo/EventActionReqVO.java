package com.linsight.module.aivideo.controller.admin.event.vo;

import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class EventActionReqVO {
    private Long assigneeId;
    @Size(max = 1000) private String remark;
    @Size(max = 64) private String reasonCode;
}
