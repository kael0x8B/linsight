package com.linsight.module.aivideo.controller.node.node;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.controller.node.node.vo.NodeCommandReportReqVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeCommandRespVO;
import com.linsight.module.aivideo.service.model.ModelExecutionService;
import com.linsight.module.aivideo.service.node.NodeCommandDTO;
import com.linsight.module.aivideo.service.node.NodeCommandService;
import com.linsight.module.aivideo.service.node.NodeUpgradeService;
import com.linsight.module.aivideo.service.task.TaskService;
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

@Tag(name = "节点端 - 耐久命令")
@RestController
@RequestMapping("/ai-video/node/command")
@Validated
public class NodeCommandController {
    @Resource
    private NodeCommandService nodeCommandService;
    @Resource
    private ModelExecutionService modelExecutionService;
    @Resource
    private TaskService taskService;
    @Resource
    private com.linsight.module.aivideo.service.task.FaceVerificationService faceVerificationService;
    @Resource
    private com.linsight.module.aivideo.service.task.EntryAccessService entryAccessService;
    @Resource
    private NodeUpgradeService nodeUpgradeService;

    @PostMapping("/pull")
    @Operation(summary = "拉取一个待执行命令")
    public CommonResult<NodeCommandRespVO> pull(Authentication authentication) {
        NodeCommandDTO command = nodeCommandService.pullCommand((Long) authentication.getPrincipal());
        return success(BeanUtils.toBean(command, NodeCommandRespVO.class));
    }

    @PostMapping("/report")
    @Operation(summary = "幂等上报命令进度或结果")
    public CommonResult<Boolean> report(@Valid @RequestBody NodeCommandReportReqVO reqVO,
                                        Authentication authentication) {
        NodeCommandDTO report = BeanUtils.toBean(reqVO, NodeCommandDTO.class);
        NodeCommandDTO accepted = nodeCommandService.reportCommand((Long) authentication.getPrincipal(), report);
        modelExecutionService.applyCommandReport(accepted);
        taskService.applyCommandReport(accepted);
        faceVerificationService.applyReport(accepted);
        entryAccessService.applyReport(accepted);
        nodeUpgradeService.applyCommandReport(accepted);
        return success(true);
    }
}
