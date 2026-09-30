package com.linsight.module.aivideo.service.node;

import java.util.List;

/** Runtime prerequisites reported by the authenticated node; no model is loaded by this query. */
public record NodeModelEnvironmentDTO(
        boolean reported,
        List<String> formats,
        List<String> rknnTargets,
        List<NodeExecutionProviderDTO> providers) {

    public NodeModelEnvironmentDTO {
        formats = formats == null ? List.of() : List.copyOf(formats);
        rknnTargets = rknnTargets == null ? List.of() : List.copyOf(rknnTargets);
        var normalizedProviders = new java.util.ArrayList<>(
                providers == null ? List.<NodeExecutionProviderDTO>of() : providers);
        if (!rknnTargets.isEmpty() && normalizedProviders.stream()
                .noneMatch(provider -> "rknpu2".equals(provider.code()))) {
            var acceleratedFormats = new java.util.ArrayList<String>();
            acceleratedFormats.add("RKNN");
            if (formats.contains("ARCHIVE")) acceleratedFormats.add("ARCHIVE");
            normalizedProviders.add(new NodeExecutionProviderDTO(
                    "rknpu2", "NPU", "rockchip", rknnTargets, acceleratedFormats,
                    "rknn-toolkit-lite2", "2.3.2"));
        }
        providers = List.copyOf(normalizedProviders);
    }

    /** Compatibility constructor for stored schema 1.0 heartbeats without provider details. */
    public NodeModelEnvironmentDTO(boolean reported, List<String> formats, List<String> rknnTargets) {
        this(reported, formats, rknnTargets, List.of());
    }

    public static NodeModelEnvironmentDTO unknown() {
        return new NodeModelEnvironmentDTO(false, List.of(), List.of(), List.of());
    }
}
