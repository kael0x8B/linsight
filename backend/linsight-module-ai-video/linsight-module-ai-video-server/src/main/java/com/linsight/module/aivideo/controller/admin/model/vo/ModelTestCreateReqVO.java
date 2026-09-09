package com.linsight.module.aivideo.controller.admin.model.vo;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import lombok.Data;
import org.springframework.web.multipart.MultipartFile;

@Data
public class ModelTestCreateReqVO {
    @NotNull @Positive private Long modelVersionId;
    @NotNull @Positive private Long nodeId;
    @NotNull private MultipartFile file;
    @NotNull @DecimalMin("0.01") @DecimalMax("1.0") private Double confidence;
    @NotNull @DecimalMin("0.01") @DecimalMax("1.0") private Double nmsThreshold;
    @NotNull @Min(32) @Max(2048) private Integer inputWidth;
    @NotNull @Min(32) @Max(2048) private Integer inputHeight;
}
