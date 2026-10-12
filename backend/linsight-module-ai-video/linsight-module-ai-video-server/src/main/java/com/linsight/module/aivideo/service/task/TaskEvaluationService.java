package com.linsight.module.aivideo.service.task;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskEvaluationCreateReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskEvaluationPageReqVO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskEvaluationDO;

public interface TaskEvaluationService {
    Long create(@jakarta.validation.Valid TaskEvaluationCreateReqVO request);
    TaskEvaluationDO get(Long id);
    PageResult<TaskEvaluationDO> page(TaskEvaluationPageReqVO request);
}
