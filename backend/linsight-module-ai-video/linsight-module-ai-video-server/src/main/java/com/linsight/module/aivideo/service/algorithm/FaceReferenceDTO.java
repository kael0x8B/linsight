package com.linsight.module.aivideo.service.algorithm;
import lombok.Data;
@Data public class FaceReferenceDTO {
    private Long id;
    private Long entryId;
    private Long libraryId;
    private Long modelVersionId;
    private String name;
    private String externalCode;
    private String objectRef;
    private String sha256;
    private String validationStatus;
    private java.time.LocalDateTime validUntil;
}
