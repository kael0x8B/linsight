package com.linsight.module.aivideo.controller.node.camera.vo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class StreamCheckStageReqVO {

    @NotBlank(message = "检测阶段名称不能为空")
    @Pattern(regexp = "DNS|TCP|AUTH|STREAM|KEYFRAME", message = "检测阶段名称不正确")
    private String name;

    @NotBlank(message = "检测阶段状态不能为空")
    @Pattern(regexp = "SUCCESS|FAILED|SKIPPED", message = "检测阶段状态不正确")
    private String status;

    @Min(value = 0, message = "阶段耗时不能小于 0")
    @Max(value = 60000, message = "阶段耗时不能超过 60000 毫秒")
    private Integer durationMs;

    @Size(max = 200, message = "阶段摘要不能超过 200 个字符")
    private String message;

}
