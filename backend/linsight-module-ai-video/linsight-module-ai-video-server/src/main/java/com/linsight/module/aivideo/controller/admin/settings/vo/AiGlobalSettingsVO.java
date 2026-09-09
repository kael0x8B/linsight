package com.linsight.module.aivideo.controller.admin.settings.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

import java.math.BigDecimal;

@Schema(description = "AI 视频强类型全局参数")
@Data
public class AiGlobalSettingsVO {
    @NotBlank
    @Pattern(regexp = "1\\.0", message = "当前仅支持 1.0 配置 Schema")
    private String schemaVersion;

    @NotNull @Min(0) @Max(120)
    private Integer recordBeforeSeconds;
    @NotNull @Min(0) @Max(120)
    private Integer recordAfterSeconds;

    @NotNull @DecimalMin("0.01") @DecimalMax("1.00")
    private BigDecimal defaultConfidence;
    @NotNull @DecimalMin("0.1") @DecimalMax("10.0")
    private BigDecimal defaultFps;

    @NotBlank
    @Pattern(regexp = "OBJECT_STORAGE", message = "V1 证据存储必须使用对象存储")
    private String evidenceStorageMode;
    @NotNull @Min(1) @Max(3650)
    private Integer evidenceRetentionDays;

    @NotNull
    private Boolean notificationsEnabled;
    @NotNull @Min(10) @Max(3600)
    private Integer nodeOfflineThresholdSeconds;
}
