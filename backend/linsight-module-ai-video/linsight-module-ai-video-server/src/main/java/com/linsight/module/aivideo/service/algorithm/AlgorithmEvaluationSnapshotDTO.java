package com.linsight.module.aivideo.service.algorithm;

import java.util.Map;

/** Immutable selected version, never implicitly switches to the current published version. */
public record AlgorithmEvaluationSnapshotDTO(Long algorithmId, Long pipelineVersionId,
        Integer pipelineVersion, Map<String, Object> dag) {}
