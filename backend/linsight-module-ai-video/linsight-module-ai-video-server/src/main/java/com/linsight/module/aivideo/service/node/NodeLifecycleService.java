package com.linsight.module.aivideo.service.node;

public interface NodeLifecycleService {
    String restartNode(Long nodeId);
    String shutdownNode(Long nodeId);
    void deleteNode(Long nodeId);
}
