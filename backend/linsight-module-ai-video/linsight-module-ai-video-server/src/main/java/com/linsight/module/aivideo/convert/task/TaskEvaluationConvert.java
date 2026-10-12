package com.linsight.module.aivideo.convert.task;

import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskEvaluationRespVO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskEvaluationDO;

public final class TaskEvaluationConvert {
    private TaskEvaluationConvert() {}

    public static TaskEvaluationRespVO convert(TaskEvaluationDO source, boolean detail) {
        var target = new TaskEvaluationRespVO();
        target.setId(source.getId());
        target.setTaskId(source.getTaskId());
        target.setTaskName(source.getTaskName());
        target.setConfigVersion(source.getConfigVersion());
        target.setSource(source.getSource());
        target.setStatus(source.getStatus());
        target.setDatasetVersion(source.getDatasetVersion());
        target.setDatasetSha256(source.getDatasetSha256());
        target.setMeasuredAtMillis(source.getMeasuredAtMillis());
        target.setEvidenceRef(source.getEvidenceRef());
        target.setFailedChecks(JsonUtils.parseArray(source.getFailedChecks(), String.class));
        target.setCreator(source.getCreator());
        target.setCreateTime(source.getCreateTime());
        if (detail) {
            target.setMeasurement(JsonUtils.parseMap(source.getMeasurement()));
            target.setConfigurationSnapshot(JsonUtils.parseMap(source.getConfigurationSnapshot()));
        }
        return target;
    }
}
