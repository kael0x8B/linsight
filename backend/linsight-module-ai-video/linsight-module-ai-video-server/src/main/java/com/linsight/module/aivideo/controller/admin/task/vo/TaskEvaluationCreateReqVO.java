package com.linsight.module.aivideo.controller.admin.task.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import lombok.Data;

import java.math.BigDecimal;

@Data
@Schema(description = "人工视频评测记录；指标达标不改变算法发布或生产验收状态")
public class TaskEvaluationCreateReqVO {
    @NotBlank @Pattern(regexp = "[a-zA-Z0-9-]{16,64}") private String requestId;
    @NotNull @Positive private Long taskId;
    @NotNull @Positive private Integer expectedConfigVersion;
    @NotNull @Min(0) private Long expectedGatewayRevision;
    @NotNull @Positive private Long measuredAtMillis;
    @NotBlank @Size(max = 100) private String datasetVersion;
    @NotBlank @Pattern(regexp = "[a-fA-F0-9]{64}") private String datasetSha256;
    @NotBlank @Pattern(regexp = "[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,511}") private String evidenceRef;
    @NotBlank @Size(max = 1000) private String environmentDescription;
    @NotNull @Valid private Metrics metrics;
    @NotNull @Valid private Thresholds thresholds;
    @NotNull @Valid private Resources resourceUsage;
    @NotNull private Boolean cooldownDedupPass;
    @Size(max = 2000) private String note;

    @Data
    public static class Metrics {
        @NotNull @DecimalMin("0") @DecimalMax("1") private BigDecimal eventPrecision;
        @NotNull @DecimalMin("0") @DecimalMax("1") private BigDecimal eventRecall;
        @NotNull @DecimalMin("0") @Digits(integer = 12, fraction = 6) private BigDecimal falsePositivesPerStreamHour;
        @NotNull @Min(0) private Integer missedEvents;
        @NotNull @DecimalMin("0") @Digits(integer = 12, fraction = 6) private BigDecimal endToEndP95Ms;
        @NotNull @DecimalMin("0") @Digits(integer = 12, fraction = 6) private BigDecimal averageFps;
    }

    @Data
    public static class Thresholds {
        @NotNull @DecimalMin("0") @DecimalMax("1") private BigDecimal minEventPrecision;
        @NotNull @DecimalMin("0") @DecimalMax("1") private BigDecimal minEventRecall;
        @NotNull @DecimalMin("0") @Digits(integer = 12, fraction = 6) private BigDecimal maxFalsePositivesPerStreamHour;
        @NotNull @Min(0) private Integer maxMissedEvents;
        @NotNull @DecimalMin(value = "0", inclusive = false) @Digits(integer = 12, fraction = 6) private BigDecimal maxEndToEndP95Ms;
        @NotNull @DecimalMin(value = "0", inclusive = false) @Digits(integer = 12, fraction = 6) private BigDecimal minAverageFps;
    }

    @Data
    public static class Resources {
        @NotNull @DecimalMin("0") @DecimalMax("100") private BigDecimal cpuPeakPercent;
        @NotNull @DecimalMin("0") @Digits(integer = 12, fraction = 6) private BigDecimal memoryPeakMiB;
        @NotNull @DecimalMin("0") @Digits(integer = 12, fraction = 6) private BigDecimal acceleratorMemoryPeakMiB;
    }
}
