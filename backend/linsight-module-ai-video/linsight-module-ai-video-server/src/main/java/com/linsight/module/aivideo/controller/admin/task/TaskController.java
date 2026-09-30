package com.linsight.module.aivideo.controller.admin.task;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskBatchCreateReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskBatchResultRespVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskPageReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskRespVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskRunRespVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskSaveReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskRuleUpdateReqVO;
import com.linsight.module.aivideo.convert.task.TaskConvert;
import com.linsight.module.aivideo.service.task.TaskService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.List;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - AI 视频任务")
@RestController
@RequestMapping("/ai-video/task")
@Validated
public class TaskController {
    @Resource private TaskService taskService;

    @GetMapping("/page")
    @Operation(summary = "获得任务分页")
    @PreAuthorize("@ss.hasPermission('ai-video:task:query')")
    public CommonResult<PageResult<TaskRespVO>> page(@Valid TaskPageReqVO reqVO) {
        return success(TaskConvert.convertPage(taskService.getTaskPage(reqVO)));
    }

    @GetMapping("/get")
    @Operation(summary = "获得任务详情与最近指标")
    @PreAuthorize("@ss.hasPermission('ai-video:task:query')")
    public CommonResult<TaskRespVO> get(@RequestParam Long id) {
        return success(TaskConvert.convert(taskService.getTask(id)));
    }

    @GetMapping("/run/list")
    @Operation(summary = "获得任务运行历史")
    @PreAuthorize("@ss.hasPermission('ai-video:task:query')")
    public CommonResult<List<TaskRunRespVO>> runs(@RequestParam Long taskId) {
        return success(TaskConvert.convertRuns(taskService.getRuns(taskId)));
    }

    @PostMapping("/create")
    @Operation(summary = "保存任务草稿")
    @PreAuthorize("@ss.hasPermission('ai-video:task:create')")
    public CommonResult<Long> create(@Valid @RequestBody TaskSaveReqVO reqVO) {
        return success(taskService.createTask(reqVO));
    }

    @PostMapping("/batch-create")
    @Operation(summary = "为多台摄像头配置算法，逐台保存草稿并跳过已有配置")
    @PreAuthorize("@ss.hasPermission('ai-video:task:create')")
    public CommonResult<List<TaskBatchResultRespVO>> batchCreate(@Valid @RequestBody TaskBatchCreateReqVO reqVO) {
        return success(taskService.batchCreateTasks(reqVO));
    }

    @PutMapping("/update")
    @Operation(summary = "更新已停止任务并递增配置版本")
    @PreAuthorize("@ss.hasPermission('ai-video:task:update')")
    public CommonResult<Boolean> update(@Valid @RequestBody TaskSaveReqVO reqVO) {
        taskService.updateTask(reqVO);
        return success(true);
    }

    @PutMapping("/update-rule")
    @Operation(summary = "切换已停止任务的规则版本，保留模型和算法快照")
    @PreAuthorize("@ss.hasPermission('ai-video:task:update')")
    public CommonResult<Boolean> updateRule(@Valid @RequestBody TaskRuleUpdateReqVO reqVO) {
        taskService.updateTaskRule(reqVO);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "删除草稿或已停止任务")
    @PreAuthorize("@ss.hasPermission('ai-video:task:delete')")
    public CommonResult<Boolean> delete(@RequestParam Long id) {
        taskService.deleteTask(id);
        return success(true);
    }

    @PostMapping("/start")
    @Operation(summary = "幂等下发任务启动命令")
    @PreAuthorize("@ss.hasPermission('ai-video:task:start')")
    public CommonResult<String> start(@RequestParam Long id) {
        return success(taskService.startTask(id));
    }

    @PostMapping("/stop")
    @Operation(summary = "停止任务；网关已停止时同步平台期望状态")
    @PreAuthorize("@ss.hasPermission('ai-video:task:stop')")
    public CommonResult<String> stop(@RequestParam Long id) {
        return success(taskService.stopTask(id));
    }
}
