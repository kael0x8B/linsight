package com.linsight.module.aivideo.controller.admin.task.vo;
import lombok.Data;
import jakarta.validation.constraints.*;
@Data public class FaceExtractionReqVO {
    @NotNull @Positive private Long entryId;
    @NotNull @Positive private Long modelVersionId;
    @NotNull @Positive private Long nodeId;
    @NotNull @AssertTrue private Boolean consentConfirmed;
    @NotNull @Future private java.time.LocalDateTime validUntil;
}
