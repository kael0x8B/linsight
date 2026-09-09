package com.linsight.module.aivideo.controller.admin.algorithm.vo;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class RecognitionLibraryRespVO {
    private Long id;
    private String name;
    private String code;
    private String libraryType;
    private String description;
    private Long engineModelVersionId;
    private Integer featureDimension;
    private String matchMode;
    private Integer status;
    private Long entryCount;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
