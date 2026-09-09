package com.linsight.module.aivideo.service.task;

import java.time.LocalDateTime;

/** Safe task projection for camera capability views; excludes configuration and credentials. */
public record TaskCameraCapabilityDTO(Long taskId, String taskName, Long cameraId, Long algorithmId,
        Long nodeId, String actualStatus, String desiredStatus, String activeRunId,
        LocalDateTime lastHeartbeatTime, boolean validationOnly, Double sampleFps,
        Double analysisFps, Double totalLatencyMillis, String executionBackend, String errorCode, String errorMessage) {
}
