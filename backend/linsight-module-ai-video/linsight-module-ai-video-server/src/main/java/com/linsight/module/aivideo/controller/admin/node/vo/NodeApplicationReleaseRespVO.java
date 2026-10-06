package com.linsight.module.aivideo.controller.admin.node.vo;

import lombok.Data;
import java.time.LocalDateTime;

@Data
public class NodeApplicationReleaseRespVO {
    private Long id;
    private String profileId;
    private String profileLabel;
    private String architecture;
    private String devices;
    private String keyId;
    private String version;
    private String notes;
    private String status;
    private String message;
    private Integer attempt;
    private String fileName;
    private Long size;
    private String sha256;
    private String bootstrapSha256;
    private String sourceSha256;
    private LocalDateTime createTime;
    private LocalDateTime finishTime;
}
