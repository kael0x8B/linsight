package com.linsight.module.aivideo.controller.admin.settings.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;

@Schema(description = "管理后台 - AI 全局参数保存 Request VO")
@Data
public class GlobalSettingsSaveReqVO {
    @NotNull @Min(0)
    private Integer expectedVersionNo;

    @Valid @NotNull
    private AiGlobalSettingsVO settings;

    @NotNull
    @Pattern(regexp = "NEW_TASKS|GRAY|ALL_RUNNING")
    private String applyScope;

    @Size(max = 100, message = "单次灰度最多选择 100 个任务")
    private List<Long> grayTaskIds;
}
