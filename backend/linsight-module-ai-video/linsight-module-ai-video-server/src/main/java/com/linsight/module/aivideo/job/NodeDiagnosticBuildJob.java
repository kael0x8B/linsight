package com.linsight.module.aivideo.job;

import com.linsight.framework.tenant.core.util.TenantUtils;
import com.linsight.module.aivideo.service.node.NodeLogService;
import jakarta.annotation.Resource;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class NodeDiagnosticBuildJob {
    @Resource private NodeLogService nodeLogService;

    @Scheduled(fixedDelay = 3000)
    public void build() {
        nodeLogService.getQueuedDiagnosticsGlobal().forEach(bundle ->
                TenantUtils.execute(bundle.getTenantId(),
                        () -> nodeLogService.buildDiagnostic(bundle.getId())));
    }
}
