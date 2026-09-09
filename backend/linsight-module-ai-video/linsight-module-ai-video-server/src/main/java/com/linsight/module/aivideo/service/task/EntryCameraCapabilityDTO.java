package com.linsight.module.aivideo.service.task;

/** Task-owned entrance projection for the camera capability list; no synthetic task identifiers. */
public record EntryCameraCapabilityDTO(Long entryAccessId, Long cameraId, Long nodeId,
                                      String name, boolean enabled, String stationState) {}
