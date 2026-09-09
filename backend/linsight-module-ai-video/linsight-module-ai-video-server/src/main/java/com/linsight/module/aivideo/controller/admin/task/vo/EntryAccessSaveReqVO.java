package com.linsight.module.aivideo.controller.admin.task.vo;
import lombok.Data;
import jakarta.validation.constraints.*;
import java.util.List;
@Data public class EntryAccessSaveReqVO {
    private Long id;
    @NotBlank @Size(max=100) private String name;
    @NotNull @Positive private Long cameraId;
    @NotNull @Positive private Long nodeId;
    @NotNull @Positive private Long libraryId;
    @NotNull @Positive private Long modelVersionId;
    @NotNull private Boolean enabled;
    @NotNull @Pattern(regexp="MANUAL|FACE_ZONE") private String triggerMode = "MANUAL";
    @NotNull @Min(0) private Integer version;
    @NotNull @DecimalMin("0.1") @DecimalMax("1") private Double similarityThreshold;
    @NotNull @DecimalMin("0.01") @DecimalMax("0.5") private Double ambiguityMargin;
    @NotNull @Min(2) @Max(10) private Integer temporalN;
    @NotNull @Min(2) @Max(15) private Integer temporalM;
    @NotNull @Size(max=256) private List<@Positive Long> allowedEntryIds;
    @NotNull @DecimalMin("0") @DecimalMax("1") private Double roiX;
    @NotNull @DecimalMin("0") @DecimalMax("1") private Double roiY;
    @NotNull @DecimalMin("0.01") @DecimalMax("1") private Double roiWidth;
    @NotNull @DecimalMin("0.01") @DecimalMax("1") private Double roiHeight;
}
