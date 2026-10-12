package com.linsight.module.aivideo.controller.admin.task.vo;

import lombok.Data;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@Data
public class TaskEvaluationRespVO {
    private Long id;
    private Long taskId;
    private String taskName;
    private Integer configVersion;
    private String source;
    private String status;
    private String datasetVersion;
    private String datasetSha256;
    private Long measuredAtMillis;
    private String evidenceRef;
    private Map<String, Object> measurement;
    private Map<String, Object> configurationSnapshot;
    private List<String> failedChecks;
    private String creator;
    private LocalDateTime createTime;
}
