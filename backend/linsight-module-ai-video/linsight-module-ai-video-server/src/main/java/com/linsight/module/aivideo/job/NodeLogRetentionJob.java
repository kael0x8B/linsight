package com.linsight.module.aivideo.job;

import com.linsight.module.aivideo.service.node.NodeLogService;
import jakarta.annotation.Resource;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class NodeLogRetentionJob {
    @Resource private NodeLogService nodeLogService;

    @Scheduled(fixedDelayString = "${linsight.ai-video.node-log.cleanup-interval-ms:60000}")
    public void clean() {
        nodeLogService.cleanupExpiredLogs();
    }
}
