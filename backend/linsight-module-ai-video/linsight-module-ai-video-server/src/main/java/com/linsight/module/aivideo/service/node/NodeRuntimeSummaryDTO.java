package com.linsight.module.aivideo.service.node;

import java.time.LocalDateTime;

public record NodeRuntimeSummaryDTO(Long id, String name, Integer status, Integer onlineStatus,
        LocalDateTime lastHeartbeatTime) {
}
