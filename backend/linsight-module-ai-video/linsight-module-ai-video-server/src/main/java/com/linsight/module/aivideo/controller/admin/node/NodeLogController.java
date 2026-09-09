package com.linsight.module.aivideo.controller.admin.node;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDiagnosticCreateReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDiagnosticRespVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeLogPageReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeLogRespVO;
import com.linsight.module.aivideo.service.node.NodeLogService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - 节点与任务日志")
@RestController
@RequestMapping("/ai-video/node-log")
@Validated
public class NodeLogController {
    @Resource private NodeLogService nodeLogService;

    @GetMapping("/page")
    @Operation(summary = "分页查询节点与任务日志")
    @PreAuthorize("@ss.hasPermission('ai-video:node-log:query')")
    public CommonResult<PageResult<NodeLogRespVO>> page(@Valid NodeLogPageReqVO reqVO) {
        return success(nodeLogService.getPage(reqVO));
    }

    @GetMapping("/snapshot")
    @PreAuthorize("@ss.hasPermission('ai-video:node-log:query')")
    public CommonResult<Long> snapshot(@RequestParam @jakarta.validation.constraints.Positive Long nodeId) {
        return success(nodeLogService.getSnapshotMaxId(nodeId));
    }

    @GetMapping("/context")
    @Operation(summary = "查询日志前后文，单侧最多 100 行")
    @PreAuthorize("@ss.hasPermission('ai-video:node-log:query')")
    public CommonResult<List<NodeLogRespVO>> context(@RequestParam Long id,
                                                      @RequestParam(defaultValue = "100") int before,
                                                      @RequestParam(defaultValue = "100") int after) {
        return success(nodeLogService.getContext(id, before, after));
    }

    @PostMapping("/diagnostic/create")
    @Operation(summary = "异步生成带有效期的节点诊断包")
    @PreAuthorize("@ss.hasPermission('ai-video:node-log:diagnostic')")
    public CommonResult<Long> createDiagnostic(
            @Valid @RequestBody NodeDiagnosticCreateReqVO reqVO) {
        return success(nodeLogService.createDiagnostic(reqVO));
    }

    @GetMapping("/diagnostic/get")
    @Operation(summary = "查询诊断包状态并按需生成 5 分钟下载地址")
    @PreAuthorize("@ss.hasPermission('ai-video:node-log:diagnostic')")
    public CommonResult<NodeDiagnosticRespVO> getDiagnostic(@RequestParam Long id) {
        return success(nodeLogService.getDiagnostic(id));
    }

    @GetMapping("/diagnostic/list")
    @Operation(summary = "查询节点最近诊断包")
    @PreAuthorize("@ss.hasPermission('ai-video:node-log:diagnostic')")
    public CommonResult<List<NodeDiagnosticRespVO>> diagnostics(@RequestParam Long nodeId) {
        return success(nodeLogService.getDiagnostics(nodeId));
    }
}
