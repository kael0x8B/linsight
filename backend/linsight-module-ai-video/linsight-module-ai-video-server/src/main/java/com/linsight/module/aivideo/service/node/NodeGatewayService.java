package com.linsight.module.aivideo.service.node;

import com.linsight.framework.tenant.core.context.TenantContextHolder;
import com.linsight.module.aivideo.integration.runtime.NodePreviewTunnelHandler;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.Objects;
import com.linsight.module.aivideo.service.task.TaskService;
import com.linsight.module.aivideo.service.camera.CameraService;
import com.linsight.module.aivideo.service.model.ModelService;
import com.linsight.module.aivideo.service.algorithm.AlgorithmService;

/** Authorized single-node operations use the same gateway mutation boundary as local users. */
@Service
public class NodeGatewayService {
    @Resource private NodeService nodeService;
    @Resource private NodePreviewTunnelHandler tunnel;
    @Resource private TaskService taskService;
    @Resource private CameraService cameraService;
    @Resource private ModelService modelService;
    @Resource private AlgorithmService algorithmService;
    @Resource private com.linsight.module.aivideo.service.model.ModelExecutionService modelExecutionService;

    public Map<String, Object> invoke(Long nodeId, String action, Map<String, Object> payload) {
        nodeService.validateNodeExists(nodeId);
        if (Set.of("task.save", "task.capacity.preflight").contains(action)) {
            boolean streamTypeChanged = Boolean.TRUE.equals(payload.get("streamTypeChanged"));
            boolean syncStreamUrls = Boolean.TRUE.equals(payload.get("syncStreamUrls"));
            Map<String, Object> prepared = new HashMap<>(payload);
            // Browser-only ownership metadata is not part of the gateway task.save contract.
            prepared.remove("platformManaged");
            prepared.remove("streamTypeChanged");
            prepared.remove("syncStreamUrls");
            if ((streamTypeChanged || syncStreamUrls) && (!Boolean.TRUE.equals(payload.get("platformManaged"))
                    || !(payload.get("taskId") instanceof Number taskId)
                    || !(payload.get("configuration") instanceof Map<?, ?> raw)
                    || !(raw.get("parameters") instanceof Map<?, ?> parameters)
                    || !(parameters.get("streamType") instanceof String streamType)
                    || !Set.of("MAIN", "SUB").contains(streamType))) {
                return Map.of("ok", false, "code", 422, "message", "请选择有效的主码流或子码流");
            }
            if (streamTypeChanged || syncStreamUrls) {
                Number taskId = (Number) payload.get("taskId");
                Map<?, ?> raw = (Map<?, ?>) payload.get("configuration");
                String streamType = (String) ((Map<?, ?>) raw.get("parameters")).get("streamType");
                var task = taskService.getTask(taskId.longValue());
                if (!Objects.equals(task.getNodeId(), nodeId)
                        || !(raw.get("cameraId") instanceof Number cameraId)
                        || !Objects.equals(task.getCameraId(), cameraId.longValue())) {
                    return Map.of("ok", false, "code", 409, "message", "任务的网关或摄像头已变更，请刷新后重试");
                }
                if (streamTypeChanged && raw.get("sourceUrl") instanceof String source && !source.isBlank()) {
                    return Map.of("ok", false, "code", 422, "message", "切换码流时请留空自定义 RTSP 地址");
                }
                Map<String, Object> configuration = new HashMap<>();
                raw.forEach((key, value) -> configuration.put(String.valueOf(key), value));
                if (syncStreamUrls) {
                    // Backfill only: a saved local address takes precedence over catalog defaults.
                    configuration.put("streamUrlDefaults", cameraService.getRuntimeStreamUrls(task.getCameraId()));
                }
                if (streamTypeChanged) {
                    configuration.put("sourceUrl", cameraService.getRuntimeStreamUrl(task.getCameraId(), streamType));
                }
                prepared.put("configuration", configuration);
            }
            payload = prepared;
        }
        if ("model.uninstall".equals(action)) {
            if (!(payload.get("modelVersionId") instanceof Number id) || id.longValue() <= 0) {
                return Map.of("ok", false, "code", 400, "message", "模型编号无效");
            }
            if (modelExecutionService.hasDeploymentOnNode(id.longValue(), nodeId)) {
                return Map.of("ok", false, "code", 409, "message", "平台部署的模型须通过模型部署命令卸载，请刷新后重试");
            }
        }
        try {
            var reply = tunnel.request(nodeId, TenantContextHolder.getTenantId(), "gateway.rpc",
                    Map.of("action", action, "payload", payload)).payload();
            if ("snapshot".equals(action) && Boolean.TRUE.equals(reply.get("ok"))) {
                return withDisplayNames(nodeId, reply);
            }
            return reply;
        } catch (NodePreviewTunnelHandler.TunnelRequestException error) {
            return Map.of("ok", false, "code", 503,
                    "message", "网关暂不可达，请检查连接；现场仍可通过网关本地地址管理");
        }
    }

    private Map<String, Object> withDisplayNames(Long nodeId, Map<String, Object> reply) {
        if (!(reply.get("data") instanceof Map<?, ?> data)) return reply;
        Set<Long> tasks = new HashSet<>(), cameras = new HashSet<>(), models = new HashSet<>(),
                installedModels = new HashSet<>(), algorithms = new HashSet<>();
        if (data.get("tasks") instanceof List<?> rows) for (Object row : rows) {
            if (!(row instanceof Map<?, ?> task) || Boolean.FALSE.equals(task.get("platformManaged"))) continue;
            if (!(task.get("config") instanceof Map<?, ?> config)) continue;
            addId(tasks, config.get("taskId"));
            addId(cameras, config.get("cameraId"));
            addId(models, config.get("modelVersionId"));
            addId(algorithms, config.get("algorithmId"));
        }
        if (data.get("models") instanceof List<?> rows) for (Object row : rows) {
            if (row instanceof Map<?, ?> model) {
                addId(models, model.get("modelVersionId"));
                addId(installedModels, model.get("modelVersionId"));
            }
        }
        modelExecutionService.reconcileNodeInventory(nodeId, installedModels);
        Map<String, Object> enriched = new HashMap<>();
        data.forEach((key, value) -> enriched.put(String.valueOf(key), value));
        Map<?, ?> existingNames = data.get("names") instanceof Map<?, ?> value ? value : Map.of();
        Map<Long, String> algorithmNames = new HashMap<>();
        if (!algorithms.isEmpty()) {
            algorithmService.getSummaries(algorithms).forEach(value -> algorithmNames.put(value.id(), value.name()));
        }
        enriched.put("names", Map.of(
                "tasks", mergeNames(existingNames.get("tasks"), taskService.getTaskNames(tasks)),
                "cameras", mergeNames(existingNames.get("cameras"), cameraService.getCameraNames(cameras)),
                "algorithms", mergeNames(existingNames.get("algorithms"), algorithmNames),
                "models", mergeNames(existingNames.get("models"), modelService.getVersionDisplayNames(models))));
        Map<String, Object> result = new HashMap<>(reply);
        result.put("data", enriched);
        return result;
    }

    private static void addId(Set<Long> ids, Object value) {
        if (value instanceof Number number && number.longValue() > 0) ids.add(number.longValue());
    }

    private static Map<Object, Object> mergeNames(Object existing, Map<?, ?> current) {
        Map<Object, Object> result = new HashMap<>();
        if (existing instanceof Map<?, ?> values) values.forEach(result::put);
        current.forEach(result::put);
        return result;
    }
}
