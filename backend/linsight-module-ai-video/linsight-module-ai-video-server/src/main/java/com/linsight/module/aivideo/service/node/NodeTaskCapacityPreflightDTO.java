package com.linsight.module.aivideo.service.node;

import java.util.Map;

/** Node-owned read projection used by Task before creating a start command. */
public record NodeTaskCapacityPreflightDTO(boolean allowed, String code, String message,
                                           Map<String, Object> report) {
}
