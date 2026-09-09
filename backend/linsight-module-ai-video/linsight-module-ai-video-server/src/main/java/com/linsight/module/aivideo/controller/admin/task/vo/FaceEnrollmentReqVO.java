package com.linsight.module.aivideo.controller.admin.task.vo;
import lombok.Data;
import jakarta.validation.constraints.*;
import org.springframework.web.multipart.MultipartFile;
@Data public class FaceEnrollmentReqVO {
    @NotNull @Positive private Long libraryId;
    @NotNull @Positive private Long modelVersionId;
    @NotNull @Positive private Long nodeId;
    @NotBlank @Size(max=100) private String name;
    @NotBlank @Size(max=100) private String externalCode;
    @NotNull @AssertTrue private Boolean consentConfirmed;
    @NotNull @Future private java.time.LocalDateTime validUntil;
    @NotNull private MultipartFile file;
}
