package com.linsight.module.aivideo.controller.admin.event.vo;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class EventMediaRespVO {
    private Long id;
    private String mediaType;
    private String fileName;
    private String mimeType;
    private Long fileSize;
    private String sha256;
    private String status;
    private String accessUrl;
    private Boolean originalContentAvailable;
    private LocalDateTime captureStartTime;
    private LocalDateTime captureEndTime;
}
