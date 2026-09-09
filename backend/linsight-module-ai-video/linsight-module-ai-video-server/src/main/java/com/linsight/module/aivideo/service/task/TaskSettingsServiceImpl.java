package com.linsight.module.aivideo.service.task;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import com.linsight.module.aivideo.dal.mysql.task.TaskMapper;
import com.linsight.module.aivideo.service.node.NodeCommandService;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.UUID;

@Service
public class TaskSettingsServiceImpl implements TaskSettingsService {
    @Resource private TaskMapper taskMapper;
    @Resource private NodeCommandService nodeCommandService;

    @Override
    public ApplyResult apply(Integer versionNo, String settingsJson, String scope, List<Long> grayTaskIds) {
        if ("NEW_TASKS".equals(scope)) return new ApplyResult(0, 0);
        List<TaskDO> tasks = taskMapper.selectRunning("GRAY".equals(scope) ? grayTaskIds : null);
        int commands = 0;
        for (TaskDO task : tasks) {
            task.setGlobalSettingsVersion(versionNo);
            task.setGlobalSettingsSnapshot(settingsJson);
            taskMapper.updateRuntimeState(task);
            try {
                nodeCommandService.createCommand(UUID.randomUUID().toString(), task.getNodeId(),
                        "APPLY_TASK_SETTINGS", task.getId(), task.getConfigVersion(),
                        "global-settings:" + versionNo + ":task:" + task.getId());
                commands++;
            } catch (ServiceException ignored) {
                // Offline tasks keep the desired snapshot and surface as PARTIAL for later operator action.
            }
        }
        return new ApplyResult(tasks.size(), commands);
    }
}
