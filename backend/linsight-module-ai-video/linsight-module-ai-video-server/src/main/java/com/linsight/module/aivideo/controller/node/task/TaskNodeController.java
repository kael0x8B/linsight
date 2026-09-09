package com.linsight.module.aivideo.controller.node.task;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.node.task.vo.TaskCommandDetailRespVO;
import com.linsight.module.aivideo.controller.node.task.vo.TaskRuntimeReportReqVO;
import com.linsight.module.aivideo.service.task.TaskService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "节点端 - AI 任务")
@RestController
@RequestMapping("/ai-video/task")
@Validated
public class TaskNodeController {
    @Resource private TaskService taskService;

    @GetMapping("/command/get")
    @Operation(summary = "获得节点所属任务命令详情")
    public CommonResult<TaskCommandDetailRespVO> command(@RequestParam String commandId,
                                                          Authentication authentication) {
        return success(taskService.getCommandDetail(commandId, (Long) authentication.getPrincipal()));
    }

    @PostMapping("/runtime/report")
    @Operation(summary = "上报任务运行状态和短周期指标快照")
    public CommonResult<Boolean> report(@Valid @RequestBody TaskRuntimeReportReqVO reqVO,
                                         Authentication authentication) {
        taskService.reportRuntime((Long) authentication.getPrincipal(), reqVO);
        return success(true);
    }
}
