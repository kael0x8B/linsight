package com.linsight.module.aivideo.controller.node.node;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.node.node.vo.NodeLogBatchReqVO;
import com.linsight.module.aivideo.service.node.NodeLogService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "节点端 - 结构化日志")
@RestController("nodeSideNodeLogController")
@RequestMapping("/ai-video/node/log")
@Validated
public class NodeLogController {
    @Resource private NodeLogService nodeLogService;

    @PostMapping("/batch")
    @Operation(summary = "幂等批量上报最多 100 条脱敏前结构化日志")
    public CommonResult<Boolean> batch(@Valid @RequestBody NodeLogBatchReqVO reqVO,
                                       Authentication authentication) {
        nodeLogService.ingest((Long) authentication.getPrincipal(), reqVO.getEntries());
        return success(true);
    }
}
