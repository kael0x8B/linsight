package com.linsight.module.aivideo.controller.admin.task.vo;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.EqualsAndHashCode;
import java.util.List;

@Data
@EqualsAndHashCode(callSuper = true)
public class TaskBatchCreateReqVO extends TaskConfigurationReqVO {
    @NotNull @Size(min = 1, max = 100)
    private List<@NotNull @Positive Long> cameraIds;
    @NotNull @Pattern(regexp = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    private String requestId;
    private boolean confirmSharedRegions;
}
