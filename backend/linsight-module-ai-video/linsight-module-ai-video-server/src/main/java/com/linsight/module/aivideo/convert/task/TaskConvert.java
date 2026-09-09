package com.linsight.module.aivideo.convert.task;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskRespVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskRunRespVO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskRunDO;

import java.util.List;
import java.util.Map;

public final class TaskConvert {
    private TaskConvert() {}

    public static TaskRespVO convert(TaskDO source) {
        TaskRespVO target = new TaskRespVO();
        target.setId(source.getId());
        target.setName(source.getName());
        target.setCode(source.getCode());
        target.setCameraId(source.getCameraId());
        target.setAlgorithmId(source.getAlgorithmId());
        target.setPipelineVersionId(source.getPipelineVersionId());
        target.setModelVersionId(source.getModelVersionId());
        target.setModelBindings(parseModelBindings(source.getModelBindings(), source.getModelVersionId()));
        target.setNodeId(source.getNodeId());
        target.setRuleId(source.getRuleId());
        target.setRuleVersionId(source.getRuleVersionId());
        target.setParameters(JsonUtils.parseMap(source.getParameters()));
        target.setDesiredStatus(source.getDesiredStatus());
        target.setActualStatus(source.getActualStatus());
        target.setConfigVersion(source.getConfigVersion());
        target.setActiveRunId(source.getActiveRunId());
        target.setLastCommandId(source.getLastCommandId());
        target.setLastHeartbeatTime(source.getLastHeartbeatTime());
        Map<String, Object> metrics = JsonUtils.parseMap(source.getMetricsSnapshot());
        target.setMetricsSnapshot(metrics);
        if (metrics != null && metrics.get("gatewayRevision") instanceof Number revision) {
            target.setGatewayRevision(revision.longValue());
            Object configuration = metrics.get("gatewayConfiguration");
            if (configuration instanceof Map<?, ?>) {
                target.setGatewayConfiguration(JsonUtils.parseMap(JsonUtils.toJsonString(configuration)));
            }
        }
        target.setDiagnosticId(source.getDiagnosticId());
        target.setErrorCode(source.getErrorCode());
        target.setErrorMessage(source.getErrorMessage());
        target.setCreateTime(source.getCreateTime());
        target.setUpdateTime(source.getUpdateTime());
        return target;
    }

    public static Map<String, Long> parseModelBindings(String json, Long fallbackVersionId) {
        if (json == null || json.isBlank()) return fallbackVersionId == null ? Map.of() : Map.of("primary", fallbackVersionId);
        Map<?, ?> raw = JsonUtils.parseMap(json);
        if (raw == null) return fallbackVersionId == null ? Map.of() : Map.of("primary", fallbackVersionId);
        java.util.LinkedHashMap<String, Long> result = new java.util.LinkedHashMap<>();
        raw.forEach((key, value) -> {
            if (key instanceof String name && value instanceof Number number) result.put(name, number.longValue());
        });
        return result;
    }

    public static PageResult<TaskRespVO> convertPage(PageResult<TaskDO> page) {
        return new PageResult<>(page.getList().stream().map(TaskConvert::convert).toList(), page.getTotal());
    }

    public static List<TaskRunRespVO> convertRuns(List<TaskRunDO> runs) {
        return runs.stream().map(source -> {
            TaskRunRespVO target = new TaskRunRespVO();
            target.setId(source.getId());
            target.setTaskId(source.getTaskId());
            target.setRunId(source.getRunId());
            target.setConfigVersion(source.getConfigVersion());
            target.setCommandId(source.getCommandId());
            target.setStatus(source.getStatus());
            target.setStartTime(source.getStartTime());
            target.setFinishTime(source.getFinishTime());
                target.setMetricsSnapshot(JsonUtils.parseMap(source.getMetricsSnapshot()));
            target.setDiagnosticId(source.getDiagnosticId());
            target.setErrorCode(source.getErrorCode());
            target.setErrorMessage(source.getErrorMessage());
            target.setCreateTime(source.getCreateTime());
            return target;
        }).toList();
    }
}
