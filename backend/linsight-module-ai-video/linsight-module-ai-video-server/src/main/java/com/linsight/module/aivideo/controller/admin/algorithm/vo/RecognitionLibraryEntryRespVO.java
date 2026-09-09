package com.linsight.module.aivideo.controller.admin.algorithm.vo;

import lombok.Data;

import java.time.LocalDateTime;
import java.util.Map;

@Data
public class RecognitionLibraryEntryRespVO {
    private Long id;
    private Long libraryId;
    private String name;
    private String externalCode;
    private String mediaRef;
    private String featureStatus;
    private Map<String, Object> attributes;
    private Integer status;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
