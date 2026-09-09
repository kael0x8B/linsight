package com.linsight.module.aivideo.controller.admin.rule.vo;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;

@Data
public class RuleDryRunReqVO {
    @NotNull private Long ruleVersionId;
    @Min(1) private Long nodeId;
    @Min(1) private Long cameraId;
    @NotEmpty @Size(max = 300) @Valid private List<Frame> frames;

    @Data
    public static class Frame {
        @NotNull @Min(0) private Long timestampMillis;
        @NotNull @Valid private List<DetectedObject> objects;
    }

    @Data
    public static class DetectedObject {
        @JsonProperty("class") @NotBlank @Size(max = 64) private String className;
        @Size(max = 128) private String trackId;
        @jakarta.validation.constraints.DecimalMin("0") @jakarta.validation.constraints.DecimalMax("1")
        private Double confidence = 1.0;
        @NotNull @Valid private Bbox bbox;
    }

    @Data
    public static class Bbox {
        @NotNull @Min(0) @Max(1) private Double x;
        @NotNull @Min(0) @Max(1) private Double y;
        @NotNull @Min(0) @Max(1) private Double width;
        @NotNull @Min(0) @Max(1) private Double height;
    }
}
