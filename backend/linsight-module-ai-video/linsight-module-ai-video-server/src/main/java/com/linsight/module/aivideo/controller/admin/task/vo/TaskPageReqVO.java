package com.linsight.module.aivideo.controller.admin.task.vo;

import com.linsight.framework.common.pojo.PageParam;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
public class TaskPageReqVO extends PageParam {
    @Size(max = 100) private String name;
    @Size(max = 64) private String code;
    private Long cameraId;
    private Long algorithmId;
    private Long nodeId;
    @Pattern(regexp = "DRAFT|STOPPED|STARTING|RUNNING|STOPPING|FAILED|OFFLINE")
    private String actualStatus;
}
