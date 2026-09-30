package com.linsight.module.aivideo.service.camera;

import com.linsight.module.aivideo.controller.admin.camera.vo.CameraCapabilityRespVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraRespVO;
import com.linsight.module.aivideo.service.algorithm.AlgorithmService;
import com.linsight.module.aivideo.service.algorithm.AlgorithmSummaryDTO;
import com.linsight.module.aivideo.service.node.NodeRuntimeSummaryDTO;
import com.linsight.module.aivideo.service.node.NodeService;
import com.linsight.module.aivideo.service.task.TaskCameraCapabilityDTO;
import com.linsight.module.aivideo.service.task.TaskService;
import com.linsight.module.aivideo.service.task.EntryAccessService;
import com.linsight.module.aivideo.service.task.EntryCameraCapabilityDTO;
import jakarta.annotation.Resource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

/** Read-only composition over owner projections, batched for the current camera page. */
@Service
public class CameraOverviewService {
    @Resource private TaskService taskService;
    @Resource private EntryAccessService entryAccessService;
    @Resource private AlgorithmService algorithmService;
    @Resource private NodeService nodeService;
    @Value("${linsight.ai-video.camera.capability-stale-seconds:60}")
    private long staleSeconds = 60;

    public void enrichCapabilities(List<CameraRespVO> cameras) {
        if (cameras.isEmpty()) return;
        var bindings = taskService.getCameraCapabilities(cameras.stream().map(CameraRespVO::getId).toList());
        var entries = entryAccessService.getCameraCapabilities(cameras.stream().map(CameraRespVO::getId).toList());
        var algorithms = algorithmService.getSummaries(bindings.stream().map(TaskCameraCapabilityDTO::algorithmId)
                .distinct().toList()).stream().collect(Collectors.toMap(AlgorithmSummaryDTO::id, Function.identity()));
        var nodes = nodeService.getRuntimeSummaries(java.util.stream.Stream.concat(bindings.stream().map(TaskCameraCapabilityDTO::nodeId), entries.stream().map(EntryCameraCapabilityDTO::nodeId))
                .distinct().toList()).stream().collect(Collectors.toMap(NodeRuntimeSummaryDTO::id, Function.identity()));
        var grouped = new HashMap<Long, List<CameraCapabilityRespVO>>();
        var cutoff = LocalDateTime.now().minusSeconds(staleSeconds);
        for (var task : bindings) {
            var algorithm = algorithms.get(task.algorithmId());
            var node = nodes.get(task.nodeId());
            grouped.computeIfAbsent(task.cameraId(), ignored -> new ArrayList<>()).add(CameraCapabilityRespVO.builder()
                    .taskId(task.taskId()).taskName(task.taskName()).algorithmId(task.algorithmId())
                    .algorithmName(algorithm == null ? null : algorithm.name())
                    .capabilityKey(algorithm == null ? null : algorithm.capabilityKey())
                    .nodeId(task.nodeId()).nodeName(node == null ? null : node.name())
                    .actualStatus(task.actualStatus()).desiredStatus(task.desiredStatus())
                    .effectiveStatus(effectiveStatus(task, node, cutoff)).activeRunId(task.activeRunId())
                    .lastHeartbeatTime(task.lastHeartbeatTime()).validationOnly(task.validationOnly())
                    .errorCode(task.errorCode()).errorMessage(task.errorMessage())
                    .regions(task.regions())
                    .sampleFps(task.sampleFps()).analysisFps(task.analysisFps())
                    .totalLatencyMillis(task.totalLatencyMillis()).executionBackend(task.executionBackend()).build());
        }
        for (var entry : entries) {
            var node=nodes.get(entry.nodeId());
            String status=!entry.enabled()?"STOPPED":Set.of("WAIT_CLEAR","READY","POSITIONING","TRIGGERED","SCANNING","MULTIPLE_FACES").contains(entry.stationState())?"RUNNING":"STALE";
            if(entry.enabled() && (node==null || !Objects.equals(node.onlineStatus(),1) || !Objects.equals(node.status(),0)
                    || node.lastHeartbeatTime()==null || node.lastHeartbeatTime().isBefore(cutoff))) status="OFFLINE";
            grouped.computeIfAbsent(entry.cameraId(),ignored->new ArrayList<>()).add(CameraCapabilityRespVO.builder()
                    .entryAccessId(entry.entryAccessId()).taskName(entry.name()).capabilityKey("entry.face")
                    .algorithmName("入口主动刷脸").nodeId(entry.nodeId()).nodeName(node==null?null:node.name())
                    .actualStatus(entry.enabled()?"RUNNING":"STOPPED").desiredStatus(entry.enabled()?"RUNNING":"STOPPED")
                    .effectiveStatus(status).stationState(entry.stationState()).build());
        }
        cameras.forEach(camera -> camera.setRecognitionCapabilities(grouped.getOrDefault(camera.getId(), List.of())));
    }

    static String effectiveStatus(TaskCameraCapabilityDTO task, NodeRuntimeSummaryDTO node, LocalDateTime cutoff) {
        if (!Set.of("STARTING", "RUNNING", "STOPPING").contains(task.actualStatus())) return task.actualStatus();
        if (node == null || !Objects.equals(node.status(), 0) || !Objects.equals(node.onlineStatus(), 1)
                || node.lastHeartbeatTime() == null || node.lastHeartbeatTime().isBefore(cutoff)) return "OFFLINE";
        if (task.lastHeartbeatTime() == null || task.lastHeartbeatTime().isBefore(cutoff)) return "STALE";
        return task.actualStatus();
    }
}
