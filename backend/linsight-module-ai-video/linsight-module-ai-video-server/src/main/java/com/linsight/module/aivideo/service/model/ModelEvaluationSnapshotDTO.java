package com.linsight.module.aivideo.service.model;

/** Artifact identity only: no storage credentials, paths or download URLs. */
public record ModelEvaluationSnapshotDTO(Long modelId, Long modelVersionId, String version,
        String sha256, String artifactFormat, String runtimeManifest) {}
