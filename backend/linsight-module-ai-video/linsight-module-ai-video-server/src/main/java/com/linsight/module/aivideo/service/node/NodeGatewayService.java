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
import com.linsight.module.aivideo.service.task.TaskService;
import com.linsight.module.aivideo.service.camera.CameraService;
import com.linsight.module.aivideo.service.model.ModelService;

/** Authorized single-node operations use the same gateway mutation boundary as local users. */
@Service
public class NodeGatewayService {
    @Resource private NodeService nodeService;
    @Resource private NodePreviewTunnelHandler tunnel;
    @Resource private TaskService taskService;
    @Resource private CameraService cameraService;
    @Resource private ModelService modelService;
    @Resource private com.linsight.module.aivideo.service.model.ModelExecutionService modelExecutionService;

    public Map<String, Object> invoke(Long nodeId, String action, Map<String, Object> payload) {
        nodeService.validateNodeExists(nodeId);
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
                return withDisplayNames(reply);
            }
            return reply;
        } catch (NodePreviewTunnelHandler.TunnelRequestException error) {
            return Map.of("ok", false, "code", 503,
                    "message", "网关暂不可达，请检查连接；现场仍可通过网关本地地址管理");
        }
    }

    private Map<String, Object> withDisplayNames(Map<String, Object> reply) {
        if (!(reply.get("data") instanceof Map<?, ?> data)) return reply;
        Set<Long> tasks = new HashSet<>(), cameras = new HashSet<>(), models = new HashSet<>();
        if (data.get("tasks") instanceof List<?> rows) for (Object row : rows) {
            if (!(row instanceof Map<?, ?> task) || Boolean.FALSE.equals(task.get("platformManaged"))) continue;
            if (!(task.get("config") instanceof Map<?, ?> config)) continue;
            addId(tasks, config.get("taskId"));
            addId(cameras, config.get("cameraId"));
            addId(models, config.get("modelVersionId"));
        }
        if (data.get("models") instanceof List<?> rows) for (Object row : rows) {
            if (row instanceof Map<?, ?> model) addId(models, model.get("modelVersionId"));
        }
        Map<String, Object> enriched = new HashMap<>();
        data.forEach((key, value) -> enriched.put(String.valueOf(key), value));
        enriched.put("names", Map.of("tasks", taskService.getTaskNames(tasks),
                "cameras", cameraService.getCameraNames(cameras),
                "models", modelService.getVersionDisplayNames(models)));
        Map<String, Object> result = new HashMap<>(reply);
        result.put("data", enriched);
        return result;
    }

    private static void addId(Set<Long> ids, Object value) {
        if (value instanceof Number number && number.longValue() > 0) ids.add(number.longValue());
    }
}
