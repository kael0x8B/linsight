package com.linsight.module.aivideo.controller.node.task.vo;

import lombok.Data;

import java.util.Map;

@Data
public class TaskCommandDetailRespVO {
    private Long expectedGatewayRevision;
    private String commandId;
    private String commandType;
    private Integer configVersion;
    private Long taskId;
    private String runId;
    private Long cameraId;
    private String streamUrl;
    private Long algorithmId;
    private Long pipelineVersionId;
    private Map<String, Object> pipeline;
    private Long modelVersionId;
    private Map<String, Long> modelBindings;
    private Long ruleId;
    private Long ruleVersionId;
    private Map<String, Object> rule;
    private Map<String, Object> parameters;
    private Integer globalSettingsVersion;
    private Map<String, Object> globalSettings;
}
