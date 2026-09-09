package com.linsight.module.aivideo.controller.admin.node;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.apilog.core.annotation.ApiAccessLog;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentConnectionReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentCreateReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentPreflightRespVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentRespVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeBootstrapTokenCreateReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeBootstrapTokenRespVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeSimpleRespVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeRespVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeUpgradeCreateReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeUpgradeRespVO;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.service.node.NodeService;
import com.linsight.module.aivideo.integration.runtime.RuntimePreviewClient;
import com.linsight.framework.tenant.core.context.TenantContextHolder;
import com.linsight.module.aivideo.service.node.NodeDeploymentService;
import com.linsight.module.aivideo.service.node.NodeLifecycleService;
import com.linsight.module.aivideo.service.node.NodeUpgradeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static com.linsight.framework.common.pojo.CommonResult.success;

import java.util.List;

@Tag(name = "管理后台 - 边缘节点")
@RestController
@RequestMapping("/ai-video/node")
@Validated
public class NodeController {

    @Resource
    private NodeService nodeService;
    @Resource
    private NodeUpgradeService nodeUpgradeService;
    @Resource
    private NodeDeploymentService nodeDeploymentService;
    @Resource
    private NodeLifecycleService nodeLifecycleService;
    @Resource private com.linsight.module.aivideo.service.node.NodeOverviewService nodeOverviewService;
    @Resource
    private RuntimePreviewClient runtimePreviewClient;

    @PostMapping("/deployment/preflight")
    @Operation(summary = "预检 SSH 节点部署环境", description = "SSH 密码只用于本次请求且不会持久化")
    @ApiAccessLog(sanitizeKeys = {"password"})
    @PreAuthorize("@ss.hasPermission('ai-video:node:deploy')")
    public CommonResult<NodeDeploymentPreflightRespVO> preflightDeployment(
            @Valid @RequestBody NodeDeploymentConnectionReqVO reqVO) {
        return success(nodeDeploymentService.preflight(reqVO));
    }

    @PostMapping("/deployment/create")
    @Operation(summary = "创建控制台节点部署任务", description = "SSH 密码仅传递给内存中的异步执行器")
    @ApiAccessLog(sanitizeKeys = {"password", "hostKey"})
    @PreAuthorize("@ss.hasPermission('ai-video:node:deploy')")
    public CommonResult<Long> createDeployment(@Valid @RequestBody NodeDeploymentCreateReqVO reqVO) {
        return success(nodeDeploymentService.createDeployment(reqVO));
    }

    @GetMapping("/deployment/get")
    @Operation(summary = "获取节点部署进度")
    @PreAuthorize("@ss.hasPermission('ai-video:node:query')")
    public CommonResult<NodeDeploymentRespVO> getDeployment(@RequestParam("id") Long id) {
        return success(BeanUtils.toBean(nodeDeploymentService.getDeployment(id), NodeDeploymentRespVO.class));
    }

    @GetMapping("/deployment/list")
    @Operation(summary = "获取最近节点部署记录")
    @PreAuthorize("@ss.hasPermission('ai-video:node:query')")
    public CommonResult<List<NodeDeploymentRespVO>> getDeploymentList() {
        return success(BeanUtils.toBean(nodeDeploymentService.getRecentDeployments(), NodeDeploymentRespVO.class));
    }

    @GetMapping("/deployment/page")
    @PreAuthorize("@ss.hasPermission('ai-video:node:query')")
    public CommonResult<com.linsight.framework.common.pojo.PageResult<NodeDeploymentRespVO>> deploymentPage(
            @Valid com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentPageReqVO request) {
        var page = nodeDeploymentService.getPage(request);
        return success(new com.linsight.framework.common.pojo.PageResult<>(
                BeanUtils.toBean(page.getList(), NodeDeploymentRespVO.class), page.getTotal()));
    }

    @PostMapping("/create-bootstrap-token")
    @Operation(summary = "创建一次性节点注册令牌", description = "明文令牌只在本次响应中返回")
    @PreAuthorize("@ss.hasPermission('ai-video:node:create')")
    public CommonResult<NodeBootstrapTokenRespVO> createBootstrapToken(
            @Valid @RequestBody NodeBootstrapTokenCreateReqVO reqVO) {
        return success(nodeService.createBootstrapToken(reqVO.getName(), reqVO.getTtlMinutes()));
    }

    @GetMapping("/simple-list")
    @Operation(summary = "获取可选节点精简列表")
    @PreAuthorize("@ss.hasAnyPermissions('ai-video:node:query', 'ai-video:camera:preview')")
    public CommonResult<List<NodeSimpleRespVO>> getSimpleList() {
        List<NodeSimpleRespVO> nodes = BeanUtils.toBean(nodeService.getEnabledNodes(), NodeSimpleRespVO.class);
        Long tenantId = TenantContextHolder.getRequiredTenantId();
        nodes.forEach(node -> node.setPreviewTunnelConnected(
                runtimePreviewClient.isNodeConnected(node.getId(), tenantId)));
        return success(nodes);
    }

    @GetMapping("/list")
    @Operation(summary = "获取边缘节点列表")
    @PreAuthorize("@ss.hasPermission('ai-video:node:query')")
    public CommonResult<List<NodeRespVO>> getList() {
        List<NodeRespVO> nodes = nodeOverviewService.getNodes();
        Long tenantId = TenantContextHolder.getRequiredTenantId();
        nodes.forEach(node -> node.setPreviewTunnelConnected(
                runtimePreviewClient.isNodeConnected(node.getId(), tenantId)));
        return success(nodes);
    }

    @PostMapping(value = "/upgrade", consumes = "multipart/form-data")
    @Operation(summary = "下发签名 Edge Agent 升级包")
    @PreAuthorize("@ss.hasPermission('ai-video:node:upgrade')")
    public CommonResult<Long> upgrade(@Valid NodeUpgradeCreateReqVO reqVO) throws java.io.IOException {
        return success(nodeUpgradeService.createUpgrade(reqVO));
    }

    @PostMapping("/rollback")
    @Operation(summary = "回滚到节点上一已验证版本")
    @PreAuthorize("@ss.hasPermission('ai-video:node:rollback')")
    public CommonResult<Long> rollback(@RequestParam("nodeId") Long nodeId) {
        return success(nodeUpgradeService.createRollback(nodeId));
    }

    @GetMapping("/upgrade/list")
    @Operation(summary = "获取节点升级与回滚记录")
    @PreAuthorize("@ss.hasPermission('ai-video:node:query')")
    public CommonResult<List<NodeUpgradeRespVO>> getUpgradeList(@RequestParam("nodeId") Long nodeId) {
        return success(BeanUtils.toBean(nodeUpgradeService.getUpgradeList(nodeId),
                NodeUpgradeRespVO.class));
    }

    @Resource
    private com.linsight.module.aivideo.service.node.NodeCommandService nodeCommandService;

    @GetMapping("/command/list")
    @Operation(summary = "获取节点最近 50 条命令与执行结果")
    @PreAuthorize("@ss.hasPermission('ai-video:node:query')")
    public CommonResult<List<com.linsight.module.aivideo.service.node.NodeCommandDTO>> getCommandList(
            @RequestParam("nodeId") Long nodeId) {
        return success(nodeCommandService.getRecentCommands(nodeId));
    }

    @PostMapping("/restart")
    @Operation(summary = "重启边缘计算节点")
    @PreAuthorize("@ss.hasPermission('ai-video:node:operate')")
    public CommonResult<String> restart(@RequestParam("nodeId") Long nodeId) {
        return success(nodeLifecycleService.restartNode(nodeId));
    }

    @PostMapping("/shutdown")
    @Operation(summary = "关闭边缘计算节点")
    @PreAuthorize("@ss.hasPermission('ai-video:node:operate')")
    public CommonResult<String> shutdown(@RequestParam("nodeId") Long nodeId) {
        return success(nodeLifecycleService.shutdownNode(nodeId));
    }

    @DeleteMapping("/delete")
    @Operation(summary = "删除已离线且没有关联任务的边缘节点")
    @PreAuthorize("@ss.hasPermission('ai-video:node:delete')")
    public CommonResult<Boolean> delete(@RequestParam("id") Long id) {
        nodeLifecycleService.deleteNode(id);
        return success(true);
    }

}
