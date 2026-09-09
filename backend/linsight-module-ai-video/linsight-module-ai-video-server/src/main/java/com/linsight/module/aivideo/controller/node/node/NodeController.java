package com.linsight.module.aivideo.controller.node.node;

import com.linsight.framework.apilog.core.annotation.ApiAccessLog;
import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.node.node.vo.NodeHeartbeatReqVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeHeartbeatRespVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeRegisterReqVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeRegistrationRespVO;
import com.linsight.module.aivideo.service.node.NodeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.annotation.security.PermitAll;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "节点端 - Edge Agent")
@RestController("aiVideoNodeController")
@RequestMapping("/ai-video/node")
@Validated
public class NodeController {

    @Resource
    private NodeService nodeService;

    @org.springframework.web.bind.annotation.GetMapping("/ping")
    @PermitAll
    @com.linsight.framework.tenant.core.aop.TenantIgnore
    public CommonResult<String> ping() {
        return success("linsight-control-plane");
    }

    @PostMapping("/register")
    @PermitAll
    @Operation(summary = "使用一次性令牌注册节点")
    @ApiAccessLog(sanitizeKeys = {"bootstrapToken", "credential"})
    public CommonResult<NodeRegistrationRespVO> registerNode(@Valid @RequestBody NodeRegisterReqVO reqVO,
                                                              HttpServletRequest request) {
        return success(nodeService.registerNode(reqVO, request.getRemoteAddr()));
    }

    @PostMapping("/heartbeat")
    @Operation(summary = "上报节点心跳与资源快照")
    public CommonResult<NodeHeartbeatRespVO> reportHeartbeat(@Valid @RequestBody NodeHeartbeatReqVO reqVO,
                                                              Authentication authentication) {
        Long nodeId = (Long) authentication.getPrincipal();
        return success(nodeService.reportHeartbeat(nodeId, reqVO));
    }

}
