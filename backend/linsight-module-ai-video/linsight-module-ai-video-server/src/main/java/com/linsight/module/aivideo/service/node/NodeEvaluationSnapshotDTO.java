package com.linsight.module.aivideo.service.node;

import java.time.LocalDateTime;

/** Last reported environment at recording time; it is not a measured-run attestation. */
public record NodeEvaluationSnapshotDTO(Long nodeId, String name, String agentVersion,
        Integer onlineStatus, LocalDateTime lastHeartbeatTime, NodeModelEnvironmentDTO modelEnvironment) {}
