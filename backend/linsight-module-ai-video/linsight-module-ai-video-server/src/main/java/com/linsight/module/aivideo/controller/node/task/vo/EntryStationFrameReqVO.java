package com.linsight.module.aivideo.controller.node.task.vo;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import lombok.Data;
import java.util.List;
/** Ephemeral face locations on the source timeline; contains no identity or image. */
@Data
public class EntryStationFrameReqVO {
    @NotBlank @Size(max=120) private String frameId;
    @NotBlank @Size(max=120) private String runId;
    @NotNull @Positive private Long cameraId;
    @NotNull @Positive private Long timestamp;
    @NotNull @Min(1) @Max(16384) private Integer sourceWidth;
    @NotNull @Min(1) @Max(16384) private Integer sourceHeight;
    @Size(max=120) private String streamId;
    @PositiveOrZero private Long sourcePts;
    @Pattern(regexp="^[0-9a-f]{32}$") private String frameKey;
    @NotNull @Size(max=16) @Valid private List<Face> faces;
    @Data public static class Face {
        @NotNull @DecimalMin("0") @DecimalMax("1") private Double x;
        @NotNull @DecimalMin("0") @DecimalMax("1") private Double y;
        @NotNull @DecimalMin(value="0", inclusive=false) @DecimalMax("1") private Double width;
        @NotNull @DecimalMin(value="0", inclusive=false) @DecimalMax("1") private Double height;
        @NotNull @DecimalMin("0") @DecimalMax("1") private Double confidence;
        @Size(max=80) private String trackId;
        @AssertTrue public boolean isInFrame() { return x==null||y==null||width==null||height==null||(x+width<=1.000001&&y+height<=1.000001); }
    }
}
