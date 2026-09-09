package com.linsight.module.aivideo.controller.admin.settings.vo;

import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@Data
public class GlobalSettingsVersionRespVO {
    private Long id;
    private Integer versionNo;
    private AiGlobalSettingsVO settings;
    private Map<String, Object> diff;
    private String applyScope;
    private List<Long> grayTaskIds;
    private String status;
    private Integer affectedTaskCount;
    private Integer commandCount;
    private LocalDateTime appliedAt;
    private String creator;
}
