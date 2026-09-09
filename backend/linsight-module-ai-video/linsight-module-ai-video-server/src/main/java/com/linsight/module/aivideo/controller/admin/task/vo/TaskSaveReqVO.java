package com.linsight.module.aivideo.controller.admin.task.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
public class TaskSaveReqVO extends TaskConfigurationReqVO {
    private Long id;
    @NotBlank @Size(max = 100) private String name;
    @NotBlank @Pattern(regexp = "^[a-z][a-z0-9-]{1,63}$") private String code;
    @NotNull private Long cameraId;
}
