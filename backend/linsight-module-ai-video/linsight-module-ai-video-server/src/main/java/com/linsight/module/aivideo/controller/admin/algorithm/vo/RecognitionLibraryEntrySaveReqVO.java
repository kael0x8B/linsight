package com.linsight.module.aivideo.controller.admin.algorithm.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.Map;

@Data
public class RecognitionLibraryEntrySaveReqVO {
    private Long id;
    @NotNull private Long libraryId;
    @NotBlank @Size(max = 100) private String name;
    @Size(max = 100) private String externalCode;
    @Size(max = 1000) private String mediaRef;
    @NotBlank @Pattern(regexp = "PENDING|READY|FAILED") private String featureStatus = "PENDING";
    @NotNull private Map<String, Object> attributes;
    @NotNull private Integer status;
}
