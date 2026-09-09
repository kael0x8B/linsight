package com.linsight.module.aivideo.controller.admin.task.vo;

/** Each camera commits independently. CREATED also identifies a replay of this request. */
public record TaskBatchResultRespVO(Long cameraId, Long taskId, String status, String actualStatus,
                                    Integer errorCode, String message) { }
