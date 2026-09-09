package com.linsight.module.aivideo.service.event;
import lombok.Data;
import java.util.Map;
@Data public class EntryAccessEventDTO {
    private String sessionId;
    private Long entryId;
    private Long cameraId;
    private Long nodeId;
    private Long modelVersionId;
    private Map<String,Object> result;
    private Map<String,Object> configuration;
}
