package com.linsight.module.aivideo.controller.node.node;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.node.node.vo.NodeUpgradeCommandDetailRespVO;
import com.linsight.module.aivideo.service.node.NodeUpgradeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import org.springframework.security.core.Authentication;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "节点端 - Agent 升级命令")
@RestController
@RequestMapping("/ai-video/node/upgrade/command")
@Validated
public class NodeUpgradeController {
    @Resource private NodeUpgradeService nodeUpgradeService;

    @GetMapping("/get")
    @Operation(summary = "获取升级或回滚命令详情")
    public CommonResult<NodeUpgradeCommandDetailRespVO> get(
            @RequestParam("commandId") String commandId, Authentication authentication) {
        return success(nodeUpgradeService.getCommandDetail(commandId,
                (Long) authentication.getPrincipal()));
    }
}
