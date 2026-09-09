package com.linsight.module.aivideo.job;

import com.linsight.framework.tenant.core.util.TenantUtils;
import com.linsight.module.aivideo.service.model.ModelExecutionService;
import com.linsight.module.aivideo.service.node.NodeCommandDTO;
import com.linsight.module.aivideo.service.node.NodeCommandService;
import com.linsight.module.aivideo.service.node.NodeUpgradeService;
import com.linsight.module.aivideo.service.task.TaskService;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@Slf4j
public class NodeCommandExpiryJob {
    @Resource private NodeCommandService nodeCommandService;
    @Resource private ModelExecutionService modelExecutionService;
    @Resource private TaskService taskService;
    @Resource private NodeUpgradeService nodeUpgradeService;

    @Scheduled(fixedDelay = 5000)
    public void expire() {
        nodeCommandService.getExpiredCommandsGlobal().forEach(command -> {
            try {
                TenantUtils.execute(command.getTenantId(), () -> expire(command));
            } catch (RuntimeException error) {
                log.error("Failed to expire node command commandId={} errorType={}",
                        command.getCommandId(), error.getClass().getSimpleName(), error);
            }
        });
    }

    private void expire(NodeCommandDTO candidate) {
        NodeCommandDTO expired = nodeCommandService.expireCommand(candidate.getId());
        if (expired == null) return;
        modelExecutionService.applyCommandReport(expired);
        taskService.applyCommandReport(expired);
        nodeUpgradeService.applyCommandReport(expired);
    }
}
