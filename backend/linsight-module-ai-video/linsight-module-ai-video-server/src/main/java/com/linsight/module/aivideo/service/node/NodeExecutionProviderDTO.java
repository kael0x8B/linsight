package com.linsight.module.aivideo.service.node;

import java.util.List;

/** A concrete inference backend reported by Runtime, including its exact target artifacts. */
public record NodeExecutionProviderDTO(
        String code,
        String deviceType,
        String vendor,
        List<String> targets,
        List<String> formats,
        String runtime,
        String runtimeVersion) {

    public NodeExecutionProviderDTO {
        targets = targets == null ? List.of() : List.copyOf(targets);
        formats = formats == null ? List.of() : List.copyOf(formats);
    }
}
