package com.linsight.module.aivideo.controller.admin.task.vo;
import jakarta.validation.constraints.*;
import lombok.Data;
import org.springframework.web.multipart.MultipartFile;
import java.math.BigDecimal;
@Data
public class FaceVerificationCreateReqVO {
    @NotNull private Long cameraId;
    @NotNull private Long nodeId;
    @NotNull private Long modelVersionId;
    @NotNull @AssertTrue private Boolean consentConfirmed;
    @NotNull @DecimalMin("0.1") @DecimalMax("1") private BigDecimal similarityThreshold;
    @NotNull @DecimalMin("0") @DecimalMax("1") private BigDecimal roiX;
    @NotNull @DecimalMin("0") @DecimalMax("1") private BigDecimal roiY;
    @NotNull @DecimalMin(value="0", inclusive=false) @DecimalMax("1") private BigDecimal roiWidth;
    @NotNull @DecimalMin(value="0", inclusive=false) @DecimalMax("1") private BigDecimal roiHeight;
    @NotNull private MultipartFile file;
}
