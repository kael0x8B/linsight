package com.linsight.module.aivideo.controller.admin.event.vo;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class EventActionRespVO {
    private Long id;
    private String actionType;
    private String fromStatus;
    private String toStatus;
    private Long operatorId;
    private Long assigneeId;
    private String remark;
    private String reasonCode;
    private LocalDateTime createTime;
}
