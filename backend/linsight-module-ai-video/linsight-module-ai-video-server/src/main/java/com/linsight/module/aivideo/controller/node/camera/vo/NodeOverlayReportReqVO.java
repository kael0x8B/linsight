package com.linsight.module.aivideo.controller.node.camera.vo;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@Data
public class NodeOverlayReportReqVO {

    @NotNull
    @Positive
    private Long taskId;

    @NotBlank
    @Size(min = 36, max = 36)
    private String runId;

    @NotNull
    @Positive
    private Long cameraId;

    @NotBlank
    @Size(max = 128)
    private String frameId;

    @NotNull
    private Instant timestamp;

    @NotNull
    @Positive
    private Integer sourceWidth;

    @NotNull
    @Positive
    private Integer sourceHeight;

    @Size(max = 349528)
    @jakarta.validation.constraints.Pattern(regexp = "^/9j/[A-Za-z0-9+/]*={0,2}$")
    private String imageBase64;

    @jakarta.validation.constraints.Pattern(regexp = "^[0-9a-f-]{36}$")
    private String streamId;

    @jakarta.validation.constraints.Min(0)
    @jakarta.validation.constraints.Max(9007199254740991L)
    private Long sourcePts;

    @jakarta.validation.constraints.Pattern(regexp = "^[0-9a-f]{32}$")
    private String frameKey;

    @NotNull
    @Size(max = 512)
    private List<@Valid OverlayObject> objects;

    @Data
    public static class OverlayObject {

        @Size(max = 128)
        private String trackId;

        @JsonProperty("class")
        @NotBlank
        @Size(max = 80)
        private String className;

        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        private Double confidence;

        @Valid
        @NotNull
        private BoundingBox bbox;

        @NotNull
        @Size(max = 64)
        private Map<String, Object> attributes;
    }

    @Data
    public static class BoundingBox {

        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        private Double x;

        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        private Double y;

        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        private Double width;

        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        private Double height;

        @JsonIgnore
        @AssertTrue(message = "bbox 必须位于归一化画面范围内")
        public boolean isInsideFrame() {
            if (x == null || y == null || width == null || height == null) {
                return true;
            }
            return x + width <= 1.0 && y + height <= 1.0;
        }
    }
}
