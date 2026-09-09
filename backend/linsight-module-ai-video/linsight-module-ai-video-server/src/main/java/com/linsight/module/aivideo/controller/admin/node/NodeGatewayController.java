package com.linsight.module.aivideo.controller.admin.node;

import com.linsight.framework.apilog.core.annotation.ApiAccessLog;
import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.service.node.NodeGatewayService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import lombok.Data;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.Set;

import static com.linsight.framework.common.pojo.CommonResult.success;

@RestController
@RequestMapping("/ai-video/node/gateway")
@Validated
public class NodeGatewayController {
    @Resource private NodeGatewayService service;

    @Data
    public static class RequestVO {
        @NotNull @Positive private Long nodeId;
        @NotBlank @Size(max = 40) private String action;
        @NotNull @Size(max = 30) private Map<String, Object> payload;
    }

    @PostMapping("/query")
    @Operation(summary = "读取网关实际配置和本地识别结果")
    @PreAuthorize("@ss.hasPermission('ai-video:node:query')")
    @ApiAccessLog(requestEnable = false, responseEnable = false)
    public CommonResult<Map<String, Object>> query(@Valid @RequestBody RequestVO request) {
        if (!Set.of("snapshot", "overlay", "events", "event.snapshot", "event.video").contains(request.getAction())) {
            return success(Map.of("ok", false, "code", 403, "message", "只读入口不允许修改配置"));
        }
        return success(service.invoke(request.getNodeId(), request.getAction(), request.getPayload()));
    }

    @PostMapping("/model-update")
    @Operation(summary = "卸载没有平台部署记录的网关本地模型")
    @PreAuthorize("@ss.hasPermission('ai-video:node:operate') and @ss.hasPermission('ai-video:model:deploy')")
    @ApiAccessLog(requestEnable = false, responseEnable = false)
    public CommonResult<Map<String, Object>> updateLocalModel(@Valid @RequestBody RequestVO request) {
        if (!"model.uninstall".equals(request.getAction())) {
            return success(Map.of("ok", false, "code", 400, "message", "不支持的模型操作"));
        }
        return success(service.invoke(request.getNodeId(), request.getAction(), request.getPayload()));
    }

    @PostMapping("/preview")
    @Operation(summary = "网关识别任务 WebRTC 预览与同步元数据")
    @PreAuthorize("@ss.hasPermission('ai-video:node:query') and @ss.hasPermission('ai-video:camera:preview')")
    @ApiAccessLog(requestEnable = false, responseEnable = false)
    public CommonResult<Map<String, Object>> preview(@Valid @RequestBody RequestVO request) {
        if (!Set.of("preview.open", "preview.status", "preview.close", "preview.frame", "preview.frames").contains(request.getAction())) {
            return success(Map.of("ok", false, "code", 400, "message", "不支持的预览操作"));
        }
        return success(service.invoke(request.getNodeId(), request.getAction(), request.getPayload()));
    }

    @PostMapping("/update")
    @Operation(summary = "通过网关版本校验保存执行配置")
    @PreAuthorize("@ss.hasPermission('ai-video:node:operate') and @ss.hasPermission('ai-video:task:update')")
    @ApiAccessLog(requestEnable = false, responseEnable = false)
    public CommonResult<Map<String, Object>> update(@Valid @RequestBody RequestVO request) {
        if (!Set.of("task.save", "access.password").contains(request.getAction())) {
            return success(Map.of("ok", false, "code", 400, "message", "不支持的修改操作"));
        }
        return success(service.invoke(request.getNodeId(), request.getAction(), request.getPayload()));
    }
}
