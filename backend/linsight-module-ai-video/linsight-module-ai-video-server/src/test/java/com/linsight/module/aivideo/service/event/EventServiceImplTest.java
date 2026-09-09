package com.linsight.module.aivideo.service.event;

import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.event.vo.EventActionReqVO;
import com.linsight.module.aivideo.controller.node.event.vo.EventIngestReqVO;
import com.linsight.module.aivideo.dal.dataobject.event.EventActionDO;
import com.linsight.module.aivideo.dal.dataobject.event.EventDO;
import com.linsight.module.aivideo.dal.dataobject.event.EventOutboxDO;
import com.linsight.module.aivideo.dal.mysql.event.EventActionMapper;
import com.linsight.module.aivideo.dal.mysql.event.EventMapper;
import com.linsight.module.aivideo.dal.mysql.event.EventMediaMapper;
import com.linsight.module.aivideo.dal.mysql.event.EventOutboxMapper;
import com.linsight.module.infra.api.file.FileApi;
import com.linsight.module.infra.api.websocket.WebSocketSenderApi;
import com.linsight.module.aivideo.service.integration.WebhookService;
import com.linsight.framework.common.exception.ServiceException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class EventServiceImplTest {
    private EventMapper eventMapper;
    private EventActionMapper actionMapper;
    private EventOutboxMapper outboxMapper;
    private FileApi fileApi;
    private EventServiceImpl service;

    @BeforeEach
    void setUp() {
        eventMapper = mock(EventMapper.class);
        actionMapper = mock(EventActionMapper.class);
        outboxMapper = mock(EventOutboxMapper.class);
        service = new EventServiceImpl();
        ReflectionTestUtils.setField(service, "eventMapper", eventMapper);
        ReflectionTestUtils.setField(service, "eventMediaMapper", mock(EventMediaMapper.class));
        ReflectionTestUtils.setField(service, "eventActionMapper", actionMapper);
        ReflectionTestUtils.setField(service, "eventOutboxMapper", outboxMapper);
        fileApi = mock(FileApi.class);
        ReflectionTestUtils.setField(service, "fileApi", fileApi);
        ReflectionTestUtils.setField(service, "webSocketSenderApi", mock(WebSocketSenderApi.class));
        ReflectionTestUtils.setField(service, "webhookService", mock(WebhookService.class));
        when(eventMapper.updateMutableState(any(EventDO.class))).thenReturn(1);
    }

    @Test void entranceEventHasNoInventedOrdinaryTaskAndRemainsReadable() {
        var camera=mock(com.linsight.module.aivideo.service.camera.CameraService.class);
        var task=mock(com.linsight.module.aivideo.service.task.TaskService.class);
        ReflectionTestUtils.setField(service,"cameraService",camera);ReflectionTestUtils.setField(service,"taskService",task);
        when(camera.getCameraNames(any())).thenReturn(Map.of(3L,"Test camera"));when(task.getTaskNames(any())).thenReturn(Map.of());
        org.mockito.Mockito.doAnswer(call->{((EventDO)call.getArgument(0)).setId(9001L);return 1;}).when(eventMapper).insert(any(EventDO.class));
        var input=new EntryAccessEventDTO();input.setSessionId("fixture-session");input.setEntryId(2L);input.setCameraId(3L);input.setNodeId(4L);input.setModelVersionId(5L);
        input.setResult(Map.of("decision","PERMISSION_DENIED","similarity",.9,"durationMs",700));
        input.setConfiguration(Map.of("name","Test entrance","temporalN",3,"temporalM",5,"similarityThreshold",.6));
        assertEquals(9001L,service.createEntryAccessEvent(input));
        var capture=ArgumentCaptor.forClass(EventDO.class);verify(eventMapper).insert(capture.capture());
        assertNull(capture.getValue().getTaskId());assertEquals("ENTRY_PERMISSION_DENIED",capture.getValue().getEventType());
        when(eventMapper.selectById(9001L)).thenReturn(capture.getValue());
        assertEquals("Test entrance",service.getDetail(9001L).getTaskName());
    }

    @Test
    void ingestCreatesOneEventActionAndDurableOutbox() {
        EventIngestReqVO request = request();
        org.mockito.Mockito.doAnswer(invocation -> {
            ((EventDO) invocation.getArgument(0)).setId(9001L);
            return 1;
        }).when(eventMapper).insert(any(EventDO.class));
        org.mockito.Mockito.doAnswer(invocation -> {
            ((EventOutboxDO) invocation.getArgument(0)).setId(9101L);
            return 1;
        }).when(outboxMapper).insert(any(EventOutboxDO.class));

        assertEquals(9001L, service.ingest(request, 88L));

        ArgumentCaptor<EventDO> eventCaptor = ArgumentCaptor.forClass(EventDO.class);
        verify(eventMapper).insert(eventCaptor.capture());
        assertEquals("ALARM", eventCaptor.getValue().getStatus());
        assertEquals(request.getDedupKey(), eventCaptor.getValue().getActiveDedupKey());
        assertEquals("edge-agent", eventCaptor.getValue().getCreator());
        assertEquals("edge-agent", eventCaptor.getValue().getUpdater());
        ArgumentCaptor<EventActionDO> actionCaptor = ArgumentCaptor.forClass(EventActionDO.class);
        verify(actionMapper).insert(actionCaptor.capture());
        assertEquals("edge-agent", actionCaptor.getValue().getCreator());
        assertEquals("edge-agent", actionCaptor.getValue().getUpdater());
        ArgumentCaptor<EventOutboxDO> outboxCaptor = ArgumentCaptor.forClass(EventOutboxDO.class);
        verify(outboxMapper).insert(outboxCaptor.capture());
        assertEquals("edge-agent", outboxCaptor.getValue().getCreator());
        assertEquals("edge-agent", outboxCaptor.getValue().getUpdater());
        Map<String, Object> payload = JsonUtils.parseMap(outboxCaptor.getValue().getPayload());
        assertEquals("ai-video.event.changed", payload.get("type"));
        assertEquals("1.0", payload.get("version"));
        assertEquals("CREATED", ((Map<?, ?>) payload.get("data")).get("changeType"));

        when(eventMapper.selectBySourceEventId(request.getSourceEventId())).thenReturn(eventCaptor.getValue());
        assertEquals(9001L, service.ingest(request, 88L));
    }

    @Test
    void ingestKeepsDistinctRuntimeActivitiesThatShareADedupKey() {
        EventIngestReqVO first = request();
        EventIngestReqVO second = request();
        second.setSourceEventId("33333333-3333-3333-3333-333333333333");
        second.setActivityId(second.getSourceEventId());
        org.mockito.Mockito.doAnswer(invocation -> {
            EventDO inserted = invocation.getArgument(0);
            inserted.setId(inserted.getSourceEventId().equals(first.getSourceEventId()) ? 9001L : 9002L);
            return 1;
        }).when(eventMapper).insert(any(EventDO.class));

        assertEquals(9001L, service.ingest(first, 88L));
        assertEquals(9002L, service.ingest(second, 88L));
        verify(eventMapper, org.mockito.Mockito.times(2)).insert(any(EventDO.class));
    }

    @Test
    void falsePositiveClosesActivityAndKeepsReason() {
        EventDO event = event();
        when(eventMapper.selectById(9001L)).thenReturn(event);
        EventActionReqVO request = new EventActionReqVO();
        request.setRemark("反光背心被识别为人员");
        request.setReasonCode("OBJECT_MISCLASSIFIED");

        service.markFalsePositive(9001L, request, 7L);

        ArgumentCaptor<EventDO> captor = ArgumentCaptor.forClass(EventDO.class);
        verify(eventMapper).updateMutableState(captor.capture());
        assertEquals("FALSE_POSITIVE", captor.getValue().getStatus());
        assertEquals(request.getRemark(), captor.getValue().getFalsePositiveReason());
        assertNull(captor.getValue().getActiveDedupKey());
        verify(actionMapper).insert(any(EventActionDO.class));
        verify(outboxMapper).insert(any(EventOutboxDO.class));
    }

    @Test
    void dispatchMarksOutboxSentAfterWebSocketAccepts() {
        EventOutboxDO outbox = new EventOutboxDO();
        outbox.setId(1L);
        outbox.setStatus("PENDING");
        outbox.setAttempts(0);
        outbox.setPayload(JsonUtils.toJsonString(Map.of("eventId", 9001)));
        outbox.setMessageType("ai-video-event");
        when(outboxMapper.selectById(1L)).thenReturn(outbox);

        service.dispatchOutbox(1L);

        assertEquals("SENT", outbox.getStatus());
        verify(outboxMapper).updateById(outbox);
        verify(eventMapper, never()).updateById(any(EventDO.class));
    }

    @Test
    void snapshotUploadMustRejectExecutableMimeSpoofingBeforeStorage() {
        EventDO event = event();
        when(eventMapper.selectById(9001L)).thenReturn(event);

        ServiceException error = assertThrows(ServiceException.class, () -> service.uploadMedia(
                9001L, 88L, "SNAPSHOT", "snapshot.jpg", "image/jpeg",
                new byte[]{'M', 'Z', 0, 0}, null, null));

        assertEquals(1_020_005_003, error.getCode());
        verify(fileApi, never()).createFile(any(), any(), any(), any());
    }

    @Test
    void videoUploadMustRejectTraversalNameBeforeStorage() {
        EventDO event = event();
        when(eventMapper.selectById(9001L)).thenReturn(event);

        assertThrows(ServiceException.class, () -> service.uploadMedia(
                9001L, 88L, "VIDEO", "../evidence.mp4", "video/mp4",
                new byte[]{0, 0, 0, 0x18, 'f', 't', 'y', 'p', 'i', 's', 'o', 'm'}, null, null));

        verify(fileApi, never()).createFile(any(), any(), any(), any());
    }

    private static EventIngestReqVO request() {
        EventIngestReqVO value = new EventIngestReqVO();
        value.setSourceEventId("11111111-1111-1111-1111-111111111111");
        value.setActivityId(value.getSourceEventId());
        value.setDedupKey("9:8:AREA_INTRUSION:track-1");
        value.setTaskId(8L);
        value.setTaskRunId("22222222-2222-2222-2222-222222222222");
        value.setCameraId(9L);
        value.setAlgorithmId(10L);
        value.setPipelineVersionId(11L);
        value.setModelVersionId(12L);
        value.setRuleId(13L);
        value.setRuleVersionId(14L);
        value.setEventType("AREA_INTRUSION");
        value.setSeverity("MAJOR");
        value.setOccurredTime(LocalDateTime.now());
        value.setFirstSeenTime(value.getOccurredTime().minusSeconds(2));
        value.setLastSeenTime(value.getOccurredTime());
        value.setDurationMs(2000L);
        value.setMaxConfidence(new BigDecimal("0.92"));
        value.setTrackId("track-1");
        value.setObjectSnapshot(Map.of("class", "person"));
        value.setTaskSnapshot(Map.of("taskId", 8));
        value.setPipelineSnapshot(Map.of("schemaVersion", "1.0"));
        value.setModelSnapshot(Map.of("modelVersionId", 12));
        value.setRuleSnapshot(Map.of("schemaVersion", "1.0"));
        return value;
    }

    @Test
    void pageUsesBatchedOwnerNamesAndFirstSnapshotWithoutPerRowLookups() {
        var cameraService = mock(com.linsight.module.aivideo.service.camera.CameraService.class);
        var taskService = mock(com.linsight.module.aivideo.service.task.TaskService.class);
        var mediaMapper = mock(EventMediaMapper.class);
        ReflectionTestUtils.setField(service, "cameraService", cameraService);
        ReflectionTestUtils.setField(service, "taskService", taskService);
        ReflectionTestUtils.setField(service, "eventMediaMapper", mediaMapper);
        EventDO first = event(); first.setCameraId(2L); first.setTaskId(3L);
        EventDO second = event(); second.setId(9002L); second.setCameraId(2L); second.setTaskId(3L);
        when(eventMapper.selectPage(any(), any(), any(), any(), any(), any(), any(), any(), any()))
                .thenReturn(new com.linsight.framework.common.pojo.PageResult<>(java.util.List.of(first, second), 2L));
        when(cameraService.getCameraNames(java.util.List.of(2L))).thenReturn(Map.of(2L, "车间摄像头"));
        when(taskService.getTaskNames(java.util.List.of(3L))).thenReturn(Map.of(3L, "安全帽检测"));
        var old = new com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO();
        old.setId(1L); old.setEventId(9001L); old.setStatus("READY"); old.setMediaType("SNAPSHOT"); old.setObjectRef("legacy/snapshot.jpg?signature=one"); old.setSha256("old");
        var later = new com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO();
        later.setId(2L); later.setEventId(9001L); later.setStatus("READY"); later.setMediaType("SNAPSHOT"); later.setObjectRef("legacy/snapshot.jpg?signature=two"); later.setSha256("later");
        when(mediaMapper.selectSnapshotsByEventIds(java.util.List.of(9001L, 9002L))).thenReturn(java.util.List.of(old, later));
        when(fileApi.presignGetUrl(any(), any())).thenReturn(com.linsight.framework.common.pojo.CommonResult.success("https://storage.invalid/image"));
        var result = service.getPageView(new com.linsight.module.aivideo.controller.admin.event.vo.EventPageReqVO());
        assertEquals("车间摄像头", result.getList().get(0).getCameraName());
        assertEquals("安全帽检测", result.getList().get(1).getTaskName());
        assertEquals(1L, result.getList().get(0).getMedia().get(0).getId());
        assertEquals(false, result.getList().get(0).getMedia().get(0).getOriginalContentAvailable());
        verify(cameraService).getCameraNames(java.util.List.of(2L));
        verify(taskService).getTaskNames(java.util.List.of(3L));
        verify(mediaMapper, never()).selectByEventId(any());
        verify(mediaMapper, never()).selectById(any(java.io.Serializable.class));
    }

    @Test
    void historicalOverwrittenImageIsExplicitlyUnavailableForOverlay() {
        var camera = mock(com.linsight.module.aivideo.service.camera.CameraService.class);
        var task = mock(com.linsight.module.aivideo.service.task.TaskService.class);
        var mediaMapper = mock(EventMediaMapper.class);
        ReflectionTestUtils.setField(service, "cameraService", camera);
        ReflectionTestUtils.setField(service, "taskService", task);
        ReflectionTestUtils.setField(service, "eventMediaMapper", mediaMapper);
        when(eventMapper.selectById(9001L)).thenReturn(event());
        when(camera.getCameraNames(any())).thenReturn(Map.of());
        when(task.getTaskNames(any())).thenReturn(Map.of());
        var original = new com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO();
        original.setId(1L); original.setObjectRef("https://storage.invalid/legacy/snapshot.jpg?signature=first"); original.setSha256("first");
        var replacement = new com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO();
        replacement.setId(2L); replacement.setObjectRef("https://storage.invalid/legacy/snapshot.jpg?signature=second"); replacement.setSha256("second");
        when(mediaMapper.selectByEventId(9001L)).thenReturn(java.util.List.of(original, replacement));
        var result = service.getDetail(9001L);
        assertEquals(false, result.getMedia().get(0).getOriginalContentAvailable());
        assertEquals(false, result.getMedia().get(1).getOriginalContentAvailable());
    }

    @Test
    void uploadsUseContentAddressedNamesAndRetryAvoidsStorageWrite() throws Exception {
        var mediaMapper = mock(EventMediaMapper.class);
        ReflectionTestUtils.setField(service, "eventMediaMapper", mediaMapper);
        when(eventMapper.selectById(9001L)).thenReturn(event());
        var bytes = new java.io.ByteArrayOutputStream();
        javax.imageio.ImageIO.write(new java.awt.image.BufferedImage(2, 2, java.awt.image.BufferedImage.TYPE_INT_RGB), "png", bytes);
        byte[] content = bytes.toByteArray();
        String sha = cn.hutool.crypto.digest.DigestUtil.sha256Hex(content);
        when(fileApi.createFile(any(byte[].class), any(), any(), any())).thenReturn("stored");
        service.uploadMedia(9001L, 88L, "SNAPSHOT", "snapshot.png", "image/png", content, null, null);
        verify(fileApi).createFile(content, sha + "-snapshot.png", "ai-video/events/EV0001", "image/png");
        var delivered = new com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO();
        delivered.setId(99L); delivered.setStatus("READY"); delivered.setSha256(sha); delivered.setMediaType("SNAPSHOT"); delivered.setObjectRef("stored/" + sha + "-snapshot.png");
        when(mediaMapper.selectByEventId(9001L)).thenReturn(java.util.List.of(delivered));
        assertEquals(99L, service.uploadMedia(9001L, 88L, "SNAPSHOT", "snapshot.png", "image/png", content, null, null));
        org.mockito.Mockito.verifyNoMoreInteractions(fileApi);
    }

    @Test
    void retryRepairsLegacyMediaReferenceBeforeAcknowledging() throws Exception {
        var mediaMapper = mock(EventMediaMapper.class);
        ReflectionTestUtils.setField(service, "eventMediaMapper", mediaMapper);
        when(eventMapper.selectById(9001L)).thenReturn(event());
        var bytes = new java.io.ByteArrayOutputStream();
        javax.imageio.ImageIO.write(new java.awt.image.BufferedImage(2, 2,
                java.awt.image.BufferedImage.TYPE_INT_RGB), "png", bytes);
        byte[] content = bytes.toByteArray();
        String sha = cn.hutool.crypto.digest.DigestUtil.sha256Hex(content);
        var old = new com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO();
        old.setId(99L); old.setMediaType("SNAPSHOT"); old.setStatus("READY");
        old.setSha256(sha); old.setObjectRef("stored/shared/snapshot.png");
        when(mediaMapper.selectByEventId(9001L)).thenReturn(java.util.List.of(old));
        when(mediaMapper.insert(any(com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO.class)))
                .thenThrow(new org.springframework.dao.DuplicateKeyException("same content"));
        when(fileApi.createFile(any(byte[].class), any(), any(), any()))
                .thenReturn("stored/" + sha + "-snapshot.png");
        assertEquals(99L, service.uploadMedia(9001L, 88L, "SNAPSHOT", "snapshot.png",
                "image/png", content, null, null));
        var updated = ArgumentCaptor.forClass(
                com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO.class);
        verify(mediaMapper).updateById(updated.capture());
        assertEquals(99L, updated.getValue().getId());
        assertEquals("stored/" + sha + "-snapshot.png", updated.getValue().getObjectRef());
        assertEquals("READY", updated.getValue().getStatus());
    }

    @Test
    void failedRetryCannotAcknowledgeExistingLegacyRow() throws Exception {
        var mediaMapper = mock(EventMediaMapper.class);
        ReflectionTestUtils.setField(service, "eventMediaMapper", mediaMapper);
        when(eventMapper.selectById(9001L)).thenReturn(event());
        var bytes = new java.io.ByteArrayOutputStream();
        javax.imageio.ImageIO.write(new java.awt.image.BufferedImage(2, 2,
                java.awt.image.BufferedImage.TYPE_INT_RGB), "png", bytes);
        byte[] content = bytes.toByteArray();
        var old = new com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO();
        old.setId(99L); old.setMediaType("SNAPSHOT"); old.setStatus("READY");
        old.setSha256(cn.hutool.crypto.digest.DigestUtil.sha256Hex(content));
        old.setObjectRef("stored/shared/snapshot.png");
        when(mediaMapper.selectByEventId(9001L)).thenReturn(java.util.List.of(old));
        when(mediaMapper.insert(any(com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO.class)))
                .thenThrow(new org.springframework.dao.DuplicateKeyException("same content"));
        when(fileApi.createFile(any(byte[].class), any(), any(), any()))
                .thenThrow(new IllegalStateException("storage unavailable"));
        assertThrows(ServiceException.class, () -> service.uploadMedia(9001L, 88L,
                "SNAPSHOT", "snapshot.png", "image/png", content, null, null));
        verify(mediaMapper, never()).updateById(
                any(com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO.class));
    }

    private static EventDO event() {
        EventDO value = new EventDO();
        value.setId(9001L);
        value.setCameraId(2L);
        value.setTaskId(3L);
        value.setEventNo("EV0001");
        value.setEventType("AREA_INTRUSION");
        value.setSeverity("MAJOR");
        value.setNodeId(88L);
        value.setStatus("ALARM");
        value.setActiveDedupKey("dedup");
        value.setOccurredTime(LocalDateTime.now());
        value.setAssigneeId(3L);
        value.setVersion(0);
        return value;
    }
}
