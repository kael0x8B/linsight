package com.linsight.module.aivideo.service.algorithm;

public record AlgorithmSummaryDTO(Long id, String name, String capabilityKey, String eventType) {
    public AlgorithmSummaryDTO(Long id, String name, String capabilityKey) { this(id, name, capabilityKey, null); }
}
