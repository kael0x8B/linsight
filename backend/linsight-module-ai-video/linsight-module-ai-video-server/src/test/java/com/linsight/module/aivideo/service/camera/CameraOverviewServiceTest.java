package com.linsight.module.aivideo.service.camera;

import com.linsight.module.aivideo.controller.admin.camera.vo.CameraRespVO;
import com.linsight.module.aivideo.service.algorithm.AlgorithmService;
import com.linsight.module.aivideo.service.algorithm.AlgorithmSummaryDTO;
import com.linsight.module.aivideo.service.node.NodeRuntimeSummaryDTO;
import com.linsight.module.aivideo.service.node.NodeService;
import com.linsight.module.aivideo.service.task.TaskCameraCapabilityDTO;
import com.linsight.module.aivideo.service.task.TaskService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import java.time.LocalDateTime;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class CameraOverviewServiceTest {
    @InjectMocks private CameraOverviewService service;
    @Mock private TaskService tasks;
    @Mock private com.linsight.module.aivideo.service.task.EntryAccessService entries;
    @Mock private AlgorithmService algorithms;
    @Mock private NodeService nodes;

    private TaskCameraCapabilityDTO task(Long id, String status, LocalDateTime heartbeat) {
        return new TaskCameraCapabilityDTO(id, "Helmet", 2L, 10L, 1L, status, "RUNNING", "run",
                heartbeat, true, 1.0, 0.7, 1400.0, "CPU", null, null);
    }

    @Test
    void batchesOnlyRequestedCamerasAndKeepsStaleTaskDistinctFromLiveTask() {
        var now = LocalDateTime.now();
        var camera = new CameraRespVO(); camera.setId(2L);
        var empty = new CameraRespVO(); empty.setId(5L);
        when(tasks.getCameraCapabilities(List.of(2L, 5L))).thenReturn(List.of(
                task(2L, "RUNNING", now), task(1L, "RUNNING", now.minusDays(1))));
        when(algorithms.getSummaries(List.of(10L))).thenReturn(List.of(new AlgorithmSummaryDTO(10L, "安全帽", "ppe.helmet")));
        when(nodes.getRuntimeSummaries(List.of(1L))).thenReturn(List.of(new NodeRuntimeSummaryDTO(1L, "Edge", 0, 1, now)));
        service.enrichCapabilities(List.of(camera, empty));
        assertEquals(List.of("RUNNING", "STALE"), camera.getRecognitionCapabilities().stream().map(value -> value.getEffectiveStatus()).toList());
        assertTrue(camera.getRecognitionCapabilities().get(0).isValidationOnly());
        assertTrue(empty.getRecognitionCapabilities().isEmpty());
        verify(tasks).getCameraCapabilities(List.of(2L, 5L));
        verify(algorithms).getSummaries(List.of(10L));
        verify(nodes).getRuntimeSummaries(List.of(1L));
        verifyNoMoreInteractions(tasks, algorithms, nodes);
    }

    @Test
    void offlineNodeDoesNotTurnStoppedTaskIntoRunningAndMissingNodeIsExplicit() {
        var now = LocalDateTime.now(); var cutoff = now.minusSeconds(60);
        var offline = new NodeRuntimeSummaryDTO(1L, "Edge", 0, 2, now);
        assertEquals("OFFLINE", CameraOverviewService.effectiveStatus(task(1L, "RUNNING", now), offline, cutoff));
        assertEquals("OFFLINE", CameraOverviewService.effectiveStatus(task(1L, "RUNNING", now), null, cutoff));
        assertEquals("STOPPED", CameraOverviewService.effectiveStatus(task(1L, "STOPPED", now), offline, cutoff));
        assertEquals("STALE", CameraOverviewService.effectiveStatus(task(1L, "RUNNING", null),
                new NodeRuntimeSummaryDTO(1L, "Edge", 0, 1, now), cutoff));
    }

    @Test
    void entranceAppearsWithItsOwnIdentifierAndRealStationState() {
        var camera=new CameraRespVO();camera.setId(2L);
        when(entries.getCameraCapabilities(List.of(2L))).thenReturn(List.of(
                new com.linsight.module.aivideo.service.task.EntryCameraCapabilityDTO(8L,2L,1L,"入口",false,"DISABLED")));
        service.enrichCapabilities(List.of(camera));
        var capability=camera.getRecognitionCapabilities().get(0);
        assertEquals(8L,capability.getEntryAccessId());assertNull(capability.getTaskId());
        assertEquals("STOPPED",capability.getEffectiveStatus());assertEquals("DISABLED",capability.getStationState());
        assertEquals("entry.face",capability.getCapabilityKey());
    }

    @Test
    void emptyPageDoesNotQueryOtherDomains() {
        service.enrichCapabilities(List.of());
        verifyNoInteractions(tasks, algorithms, nodes);
    }
}
