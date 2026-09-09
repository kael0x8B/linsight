package com.linsight.module.aivideo.service.event;

import cn.hutool.crypto.digest.DigestUtil;
import com.linsight.framework.common.enums.UserTypeEnum;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.event.vo.EventActionReqVO;
import com.linsight.module.aivideo.controller.admin.event.vo.EventMediaRespVO;
import com.linsight.module.aivideo.controller.admin.event.vo.EventPageReqVO;
import com.linsight.module.aivideo.controller.admin.event.vo.EventRespVO;
import com.linsight.module.aivideo.controller.node.event.vo.EventIngestReqVO;
import com.linsight.module.aivideo.controller.node.event.vo.EventTransitionReqVO;
import com.linsight.module.aivideo.convert.event.EventConvert;
import com.linsight.module.aivideo.dal.dataobject.event.EventActionDO;
import com.linsight.module.aivideo.dal.dataobject.event.EventDO;
import com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO;
import com.linsight.module.aivideo.dal.dataobject.event.EventOutboxDO;
import com.linsight.module.aivideo.dal.mysql.event.EventActionMapper;
import com.linsight.module.aivideo.dal.mysql.event.EventMapper;
import com.linsight.module.aivideo.dal.mysql.event.EventMediaMapper;
import com.linsight.module.aivideo.dal.mysql.event.EventOutboxMapper;
import com.linsight.module.aivideo.framework.file.UploadContentValidator;
import com.linsight.module.aivideo.service.integration.WebhookService;
import com.linsight.module.infra.api.file.FileApi;
import com.linsight.module.infra.api.websocket.WebSocketSenderApi;
import jakarta.annotation.Resource;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.event.ErrorCodeConstants.EVENT_MEDIA_INVALID;
import static com.linsight.module.aivideo.enums.event.ErrorCodeConstants.EVENT_NODE_MISMATCH;
import static com.linsight.module.aivideo.enums.event.ErrorCodeConstants.EVENT_NOT_FOUND;
import static com.linsight.module.aivideo.enums.event.ErrorCodeConstants.EVENT_STATUS_INVALID;

@Service
public class EventServiceImpl implements EventService {
    private static final String EDGE_AGENT_ACTOR = "edge-agent";
    private static final Set<String> TERMINAL_STATUSES = Set.of("CLOSED", "FALSE_POSITIVE");
    private static final Set<String> MEDIA_TYPES = Set.of("SNAPSHOT", "VIDEO");

    @Resource private com.linsight.module.aivideo.service.camera.CameraService cameraService;
    @Resource private com.linsight.module.aivideo.service.task.TaskService taskService;
    @Resource private EventMapper eventMapper;
    @Resource private EventMediaMapper eventMediaMapper;
    @Resource private EventActionMapper eventActionMapper;
    @Resource private EventOutboxMapper eventOutboxMapper;
    @Resource private FileApi fileApi;
    @Resource private WebSocketSenderApi webSocketSenderApi;
    @Resource private WebhookService webhookService;

    @Override
    public PageResult<EventDO> getPage(EventPageReqVO reqVO) {
        return eventMapper.selectPage(reqVO, reqVO.getEventNo(), reqVO.getTaskId(), reqVO.getAlgorithmId(),
                reqVO.getCameraId(), reqVO.getEventType(),
                reqVO.getSeverity(), reqVO.getStatus(), reqVO.getOccurredTime());
    }

    @Override
    public PageResult<EventRespVO> getPageView(EventPageReqVO reqVO) {
        PageResult<EventRespVO> result = EventConvert.convertPage(getPage(reqVO));
        fillDisplayNames(result.getList());
        Map<Long, List<EventMediaDO>> snapshots = eventMediaMapper.selectSnapshotsByEventIds(
                result.getList().stream().map(EventRespVO::getId).toList()).stream()
                .collect(java.util.stream.Collectors.groupingBy(EventMediaDO::getEventId));
        result.getList().forEach(event -> {
            List<EventMediaDO> versions = snapshots.get(event.getId());
            if (versions != null && !versions.isEmpty()) event.setMedia(mediaView(List.of(versions.get(0)), versions));
        });
        return result;
    }

    private void fillDisplayNames(List<EventRespVO> events) {
        if (events.isEmpty()) return;
        Map<Long, String> cameras = cameraService.getCameraNames(events.stream().map(EventRespVO::getCameraId).distinct().toList());
        Map<Long, String> tasks = taskService.getTaskNames(events.stream().map(EventRespVO::getTaskId).filter(java.util.Objects::nonNull).distinct().toList());
        events.forEach(event -> { event.setCameraName(cameras.get(event.getCameraId())); event.setTaskName(event.getTaskId()==null ? String.valueOf(event.getTaskSnapshot().getOrDefault("name","主动入口核验")) : tasks.get(event.getTaskId())); });
    }

    private List<EventMediaRespVO> mediaView(List<EventMediaDO> sources) {
        return mediaView(sources, sources);
    }

    private List<EventMediaRespVO> mediaView(List<EventMediaDO> sources, List<EventMediaDO> versions) {
        List<EventMediaRespVO> media = EventConvert.convertMedia(sources);
        Map<Long, EventMediaDO> byId = sources.stream().collect(java.util.stream.Collectors.toMap(EventMediaDO::getId, value -> value));
        media.forEach(value -> {
            EventMediaDO source = byId.get(value.getId());
            // Legacy uploads reused one object path even when the content changed.
            // Do not offer a misleading overlay for a trigger image that was overwritten.
            value.setOriginalContentAvailable(versions.stream().noneMatch(other ->
                    !java.util.Objects.equals(other.getSha256(), source.getSha256())
                    && java.util.Objects.equals(mediaObjectKey(other.getObjectRef()), mediaObjectKey(source.getObjectRef()))));
            if (source.getObjectRef() != null && "READY".equals(source.getStatus())) {
                value.setAccessUrl(fileApi.presignGetUrl(source.getObjectRef(), 600).getCheckedData());
            }
        });
        return media;
    }

    private static String mediaObjectKey(String reference) {
        if (reference == null) return null;
        try {
            java.net.URI uri = java.net.URI.create(reference);
            return String.valueOf(uri.getScheme()) + ":" + String.valueOf(uri.getAuthority()) + uri.getRawPath();
        } catch (IllegalArgumentException ignored) {
            return reference;
        }
    }

    @Override
    public EventRespVO getDetail(Long id) {
        EventDO event = requireEvent(id);
        EventRespVO result = EventConvert.convert(event);
        fillDisplayNames(List.of(result));
        result.setMedia(mediaView(eventMediaMapper.selectByEventId(id)));
        result.setActions(EventConvert.convertActions(eventActionMapper.selectByEventId(id)));
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createEntryAccessEvent(EntryAccessEventDTO source) {
        String decision=String.valueOf(source.getResult().get("decision"));
        if (!Set.of("PERMISSION_DENIED","IDENTITY_UNCONFIRMED").contains(decision)) {
            throw exception(EVENT_STATUS_INVALID);
        }
        var request=new EventIngestReqVO();
        request.setSourceEventId("entry:"+source.getSessionId());request.setActivityId(source.getSessionId());
        request.setDedupKey("entry:"+source.getEntryId()+":"+source.getSessionId());
        request.setTaskRunId(source.getSessionId());request.setCameraId(source.getCameraId());
        request.setModelVersionId(source.getModelVersionId());
        request.setEventType("PERMISSION_DENIED".equals(decision)?"ENTRY_PERMISSION_DENIED":"ENTRY_IDENTITY_UNCONFIRMED");
        request.setSeverity("MINOR");
        long nowMillis=System.currentTimeMillis();
        long first=source.getResult().get("firstSeenMillis") instanceof Number n?n.longValue():nowMillis;
        long last=source.getResult().get("lastSeenMillis") instanceof Number n?n.longValue():nowMillis;
        request.setOccurredTime(LocalDateTime.ofInstant(java.time.Instant.ofEpochMilli(last),java.time.ZoneId.systemDefault()));
        request.setFirstSeenTime(LocalDateTime.ofInstant(java.time.Instant.ofEpochMilli(first),java.time.ZoneId.systemDefault()));
        request.setLastSeenTime(request.getOccurredTime());
        request.setDurationMs(((Number)source.getResult().getOrDefault("durationMs",0)).longValue());
        Object similarity=source.getResult().get("similarity");
        if(similarity instanceof Number n) request.setMaxConfidence(java.math.BigDecimal.valueOf(Math.max(0,Math.min(1,n.doubleValue()))));
        var object=new java.util.LinkedHashMap<String,Object>(source.getResult());
        object.put("class","face");object.put("confidence",request.getMaxConfidence());
        request.setObjectSnapshot(object);request.setTaskSnapshot(source.getConfiguration());
        request.setPipelineSnapshot(Map.of("schemaVersion","1.0","mode","ACTIVE_ENTRY","liveness","NOT_VERIFIED"));
        request.setModelSnapshot(Map.of("schemaVersion","1.0","modelVersionId",source.getModelVersionId()));
        request.setRuleSnapshot(Map.of("schemaVersion","1.0","temporalN",source.getConfiguration().get("temporalN"),
                "temporalM",source.getConfiguration().get("temporalM"),"similarityThreshold",source.getConfiguration().get("similarityThreshold")));
        return ingest(request,source.getNodeId());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long ingest(EventIngestReqVO reqVO, Long nodeId) {
        EventDO existing = eventMapper.selectBySourceEventId(reqVO.getSourceEventId());
        if (existing != null) return existing.getId();

        // Runtime owns rule-window/track deduplication. The control plane only uses the
        // immutable source event id for idempotency: after a disconnect, several sequential
        // activities can legitimately share one dedup key before their close transitions replay.

        EventDO event = new EventDO();
        event.setEventNo("EV" + UUID.randomUUID().toString().replace("-", "").substring(0, 20).toUpperCase());
        event.setSourceEventId(reqVO.getSourceEventId());
        event.setActivityId(reqVO.getActivityId());
        event.setDedupKey(reqVO.getDedupKey());
        event.setActiveDedupKey(reqVO.getDedupKey());
        event.setTaskId(reqVO.getTaskId());
        event.setTaskRunId(reqVO.getTaskRunId());
        event.setCameraId(reqVO.getCameraId());
        event.setNodeId(nodeId);
        event.setAlgorithmId(reqVO.getAlgorithmId());
        event.setPipelineVersionId(reqVO.getPipelineVersionId());
        event.setModelVersionId(reqVO.getModelVersionId());
        event.setRuleId(reqVO.getRuleId());
        event.setRuleVersionId(reqVO.getRuleVersionId());
        event.setEventType(reqVO.getEventType());
        event.setSeverity(reqVO.getSeverity());
        event.setStatus("ALARM");
        event.setEvidenceStatus("PENDING");
        event.setOccurredTime(reqVO.getOccurredTime());
        event.setFirstSeenTime(reqVO.getFirstSeenTime());
        event.setLastSeenTime(reqVO.getLastSeenTime());
        event.setDurationMs(reqVO.getDurationMs());
        event.setMaxConfidence(reqVO.getMaxConfidence());
        event.setTrackId(reqVO.getTrackId());
        event.setObjectSnapshot(JsonUtils.toJsonString(reqVO.getObjectSnapshot()));
        event.setTaskSnapshot(JsonUtils.toJsonString(reqVO.getTaskSnapshot()));
        event.setPipelineSnapshot(JsonUtils.toJsonString(reqVO.getPipelineSnapshot()));
        event.setModelSnapshot(JsonUtils.toJsonString(reqVO.getModelSnapshot()));
        event.setRuleSnapshot(JsonUtils.toJsonString(reqVO.getRuleSnapshot()));
        event.setVersion(0);
        event.setCreator(EDGE_AGENT_ACTOR);
        event.setUpdater(EDGE_AGENT_ACTOR);
        try {
            eventMapper.insert(event);
        } catch (DuplicateKeyException ignored) {
            EventDO duplicate = eventMapper.selectBySourceEventId(reqVO.getSourceEventId());
            if (duplicate != null) return duplicate.getId();
            throw ignored;
        }
        insertAction(event.getId(), "CREATED", null, "ALARM", null, null,
                "Runtime 规则状态机确认告警", null);
        enqueue(event, "CREATED", EDGE_AGENT_ACTOR);
        return event.getId();
    }

    @Override
    public Long uploadMedia(Long eventId, Long nodeId, String mediaType, String fileName, String contentType,
                            byte[] content, LocalDateTime captureStartTime, LocalDateTime captureEndTime) {
        EventDO event = requireEvent(eventId);
        requireNode(event, nodeId);
        if (!MEDIA_TYPES.contains(mediaType) || content.length == 0 || content.length > 100 * 1024 * 1024) {
            throw exception(EVENT_MEDIA_INVALID);
        }
        String safeFileName;
        String verifiedContentType;
        try {
            safeFileName = UploadContentValidator.safeFileName(fileName,
                    "SNAPSHOT".equals(mediaType) ? "snapshot.jpg" : "evidence.mp4");
        } catch (IllegalArgumentException error) {
            throw exception(EVENT_MEDIA_INVALID);
        }
        if ("SNAPSHOT".equals(mediaType)) {
            verifiedContentType = UploadContentValidator.detectImageContentType(content);
        } else {
            verifiedContentType = UploadContentValidator.isMp4(content) ? "video/mp4" : null;
        }
        if (verifiedContentType == null || !verifiedContentType.equals(contentType)) {
            throw exception(EVENT_MEDIA_INVALID);
        }
        String sha256 = DigestUtil.sha256Hex(content);
        EventMediaDO delivered = eventMediaMapper.selectByEventId(eventId).stream()
                .filter(value -> "READY".equals(value.getStatus()) && mediaType.equals(value.getMediaType())
                        && sha256.equals(value.getSha256()) && value.getObjectRef() != null
                        && value.getObjectRef().contains(sha256 + "-"))
                .findFirst().orElse(null);
        if (delivered != null) return delivered.getId();
        EventMediaDO media = new EventMediaDO();
        media.setEventId(eventId);
        media.setMediaType(mediaType);
        media.setFileName(safeFileName);
        media.setMimeType(verifiedContentType);
        media.setFileSize((long) content.length);
        media.setSha256(sha256);
        media.setCaptureStartTime(captureStartTime);
        media.setCaptureEndTime(captureEndTime);
        media.setCreator(EDGE_AGENT_ACTOR);
        media.setUpdater(EDGE_AGENT_ACTOR);
        try {
            media.setObjectRef(fileApi.createFile(content, sha256 + "-" + safeFileName, "ai-video/events/" + event.getEventNo(),
                    media.getMimeType()));
            media.setStatus("READY");
        } catch (RuntimeException error) {
            media.setStatus("FAILED");
            media.setErrorMessage(shortMessage(error));
        }
        try {
            eventMediaMapper.insert(media);
        } catch (DuplicateKeyException ignored) {
            EventMediaDO existing = eventMediaMapper.selectByEventId(eventId).stream()
                    .filter(value -> sha256.equals(value.getSha256()) && mediaType.equals(value.getMediaType()))
                    .findFirst().orElseThrow(() -> ignored);
            if (!"READY".equals(media.getStatus())) throw exception(EVENT_MEDIA_INVALID);
            // Legacy rows can still reference a shared, overwritten object path.
            // A successful retry must attach the newly stored immutable object to
            // that row before the Agent receives an ACK and releases its copy.
            media.setId(existing.getId());
            media.setCreator(null);
            media.setErrorMessage("");
            eventMediaMapper.updateById(media);
        }
        refreshEvidenceStatus(event);
        enqueue(event, "EVIDENCE_UPDATED", EDGE_AGENT_ACTOR);
        if ("FAILED".equals(media.getStatus())) throw exception(EVENT_MEDIA_INVALID);
        return media.getId();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void applyRuntimeTransition(EventTransitionReqVO reqVO, Long nodeId) {
        EventDO event = eventMapper.selectBySourceEventId(reqVO.getSourceEventId());
        if (event == null) throw exception(EVENT_NOT_FOUND);
        requireNode(event, nodeId);
        String from = event.getStatus();
        String target = from;
        if ("CLOSED".equals(reqVO.getState())) {
            event.setActiveDedupKey(null);
            event.setCloseTime(reqVO.getOccurredTime());
            event.setUpdater(EDGE_AGENT_ACTOR);
            if ("ALARM".equals(from)) {
                target = "CLOSED";
                event.setStatus(target);
            }
            updateMutableState(event);
        }
        insertAction(event.getId(), reqVO.getState(), from, target, null, event.getAssigneeId(),
                "Runtime 规则状态变更", null);
        enqueue(event, reqVO.getState(), EDGE_AGENT_ACTOR);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void assign(Long id, EventActionReqVO reqVO, Long operatorId) {
        if (reqVO.getAssigneeId() == null) throw exception(EVENT_STATUS_INVALID);
        EventDO event = requireMutableEvent(id);
        String from = event.getStatus();
        event.setAssigneeId(reqVO.getAssigneeId());
        event.setStatus("ASSIGNED");
        event.setUpdater(String.valueOf(operatorId));
        updateMutableState(event);
        insertAction(id, "ASSIGNED", from, "ASSIGNED", operatorId, reqVO.getAssigneeId(),
                reqVO.getRemark(), reqVO.getReasonCode());
        enqueue(event, "ASSIGNED", String.valueOf(operatorId));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void handle(Long id, EventActionReqVO reqVO, Long operatorId) {
        EventDO event = requireMutableEvent(id);
        String from = event.getStatus();
        event.setHandlingResult(reqVO.getRemark());
        event.setStatus("RESOLVED");
        event.setUpdater(String.valueOf(operatorId));
        updateMutableState(event);
        insertAction(id, "HANDLED", from, "RESOLVED", operatorId, event.getAssigneeId(),
                reqVO.getRemark(), reqVO.getReasonCode());
        enqueue(event, "RESOLVED", String.valueOf(operatorId));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void close(Long id, EventActionReqVO reqVO, Long operatorId) {
        EventDO event = requireMutableEvent(id);
        String from = event.getStatus();
        event.setStatus("CLOSED");
        event.setActiveDedupKey(null);
        event.setCloseTime(LocalDateTime.now());
        event.setUpdater(String.valueOf(operatorId));
        updateMutableState(event);
        insertAction(id, "CLOSED", from, "CLOSED", operatorId, event.getAssigneeId(),
                reqVO.getRemark(), reqVO.getReasonCode());
        enqueue(event, "CLOSED", String.valueOf(operatorId));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void markFalsePositive(Long id, EventActionReqVO reqVO, Long operatorId) {
        EventDO event = requireMutableEvent(id);
        String from = event.getStatus();
        event.setStatus("FALSE_POSITIVE");
        event.setFalsePositiveReason(reqVO.getRemark());
        event.setActiveDedupKey(null);
        event.setCloseTime(LocalDateTime.now());
        event.setUpdater(String.valueOf(operatorId));
        updateMutableState(event);
        insertAction(id, "FALSE_POSITIVE", from, "FALSE_POSITIVE", operatorId, event.getAssigneeId(),
                reqVO.getRemark(), reqVO.getReasonCode());
        enqueue(event, "FALSE_POSITIVE", String.valueOf(operatorId));
    }

    @Override
    public List<EventOutboxDO> getReadyOutboxGlobal() {
        return eventOutboxMapper.selectReadyGlobal();
    }

    @Override
    public void dispatchOutbox(Long outboxId) {
        EventOutboxDO outbox = eventOutboxMapper.selectById(outboxId);
        if (outbox == null || "SENT".equals(outbox.getStatus())) return;
        try {
            webSocketSenderApi.sendObject(UserTypeEnum.ADMIN.getValue(), outbox.getMessageType(),
                    JsonUtils.parseMap(outbox.getPayload()));
            webhookService.enqueueEvent(outbox.getEventId(), outbox.getPayload());
            outbox.setStatus("SENT");
            outbox.setSentTime(LocalDateTime.now());
            outbox.setLastError(null);
        } catch (RuntimeException error) {
            int attempts = outbox.getAttempts() + 1;
            outbox.setAttempts(attempts);
            outbox.setNextAttemptTime(LocalDateTime.now().plusSeconds(Math.min(60, 1L << Math.min(attempts, 5))));
            outbox.setLastError(shortMessage(error));
        }
        eventOutboxMapper.updateById(outbox);
    }

    private EventDO requireEvent(Long id) {
        EventDO event = eventMapper.selectById(id);
        if (event == null) throw exception(EVENT_NOT_FOUND);
        return event;
    }

    private EventDO requireMutableEvent(Long id) {
        EventDO event = requireEvent(id);
        if (TERMINAL_STATUSES.contains(event.getStatus())) throw exception(EVENT_STATUS_INVALID);
        return event;
    }

    private static void requireNode(EventDO event, Long nodeId) {
        if (!event.getNodeId().equals(nodeId)) throw exception(EVENT_NODE_MISMATCH);
    }

    private void refreshEvidenceStatus(EventDO event) {
        List<EventMediaDO> media = eventMediaMapper.selectByEventId(event.getId());
        boolean snapshot = media.stream().anyMatch(value -> "SNAPSHOT".equals(value.getMediaType())
                && "READY".equals(value.getStatus()));
        boolean video = media.stream().anyMatch(value -> "VIDEO".equals(value.getMediaType())
                && "READY".equals(value.getStatus()));
        boolean failed = media.stream().anyMatch(value -> "FAILED".equals(value.getStatus()));
        event.setEvidenceStatus(snapshot && video ? "READY" : failed ? "FAILED" : "PARTIAL");
        event.setUpdater(EDGE_AGENT_ACTOR);
        updateMutableState(event);
    }

    private void updateMutableState(EventDO event) {
        if (eventMapper.updateMutableState(event) != 1) {
            throw exception(EVENT_STATUS_INVALID);
        }
    }

    private void insertAction(Long eventId, String actionType, String from, String to, Long operatorId,
                              Long assigneeId, String remark, String reasonCode) {
        EventActionDO action = new EventActionDO();
        action.setEventId(eventId);
        action.setActionType(actionType);
        action.setFromStatus(from);
        action.setToStatus(to);
        action.setOperatorId(operatorId);
        action.setAssigneeId(assigneeId);
        action.setRemark(remark);
        action.setReasonCode(reasonCode);
        String actor = operatorId == null ? EDGE_AGENT_ACTOR : String.valueOf(operatorId);
        action.setCreator(actor);
        action.setUpdater(actor);
        eventActionMapper.insert(action);
    }

    private void enqueue(EventDO event, String changeType, String actor) {
        EventOutboxDO outbox = new EventOutboxDO();
        outbox.setEventId(event.getId());
        outbox.setMessageType("ai-video-event");
        outbox.setPayload(JsonUtils.toJsonString(Map.of(
                "type", "ai-video.event.changed",
                "version", "1.0",
                "messageId", UUID.randomUUID().toString(),
                "occurredAt", LocalDateTime.now(),
                "data", Map.of(
                        "changeType", changeType,
                        "eventId", event.getId(),
                        "eventNo", event.getEventNo(),
                        "eventType", event.getEventType(),
                        "severity", event.getSeverity(),
                        "status", event.getStatus(),
                        "occurredTime", event.getOccurredTime()))));
        outbox.setStatus("PENDING");
        outbox.setAttempts(0);
        outbox.setNextAttemptTime(LocalDateTime.now());
        outbox.setCreator(actor);
        outbox.setUpdater(actor);
        eventOutboxMapper.insert(outbox);
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    dispatchOutbox(outbox.getId());
                }
            });
        }
    }

    private static String shortMessage(RuntimeException error) {
        String value = error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
        return value.length() > 500 ? value.substring(0, 500) : value;
    }
}
