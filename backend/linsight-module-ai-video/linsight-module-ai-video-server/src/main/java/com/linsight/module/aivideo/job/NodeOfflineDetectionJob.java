package com.linsight.module.aivideo.job;

import com.linsight.framework.tenant.core.util.TenantUtils;
import com.linsight.module.aivideo.service.node.NodeService;
import com.linsight.module.aivideo.service.settings.GlobalSettingsService;
import jakarta.annotation.Resource;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;

@Component
public class NodeOfflineDetectionJob {
    @Resource private NodeService nodeService;
    @Resource private GlobalSettingsService globalSettingsService;

    @Scheduled(fixedDelay = 5000)
    public void detect() {
        nodeService.getOnlineNodesGlobal().forEach(node -> TenantUtils.execute(node.getTenantId(), () -> {
            int threshold = globalSettingsService.getCurrent().getSettings().getNodeOfflineThresholdSeconds();
            nodeService.markOfflineIfHeartbeatExpired(node.getId(), LocalDateTime.now().minusSeconds(threshold));
        }));
    }
}
