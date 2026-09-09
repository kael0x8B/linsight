package com.linsight.module.aivideo.controller.admin.algorithm.vo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class RecognitionLibrarySaveReqVO {
    private Long id;
    @NotBlank @Size(max = 100) private String name;
    @NotBlank @Pattern(regexp = "^[a-z][a-z0-9-]{1,63}$") private String code;
    @NotBlank @Pattern(regexp = "FACE|PLATE|POSE") private String libraryType;
    @Size(max = 500) private String description;
    private Long engineModelVersionId;
    @Min(1) @Max(8192) private Integer featureDimension;
    @NotBlank @Pattern(regexp = "ONE_TO_N|EXACT|CLASSIFICATION") private String matchMode;
    @NotNull private Integer status;
}
