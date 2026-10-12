package com.linsight.module.aivideo.controller.admin.task;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.task.vo.*;
import com.linsight.module.aivideo.convert.task.TaskEvaluationConvert;
import com.linsight.module.aivideo.service.task.TaskEvaluationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Positive;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - 独立视频评测记录")
@RestController
@RequestMapping("/ai-video/task/evaluation")
@Validated
public class TaskEvaluationController {
    @Resource private TaskEvaluationService evaluationService;

    @PostMapping("/create")
    @Operation(summary = "保存不可修改的人工评测及版本快照，不发布算法")
    @PreAuthorize("@ss.hasPermission('ai-video:task:update')")
    public CommonResult<Long> create(@Valid @RequestBody TaskEvaluationCreateReqVO request) {
        return success(evaluationService.create(request));
    }

    @GetMapping("/get")
    @Operation(summary = "读取评测指标、阈值、版本与环境快照")
    @PreAuthorize("@ss.hasPermission('ai-video:task:query')")
    public CommonResult<TaskEvaluationRespVO> get(@RequestParam @Positive Long id) {
        return success(TaskEvaluationConvert.convert(evaluationService.get(id), true));
    }

    @GetMapping("/page")
    @Operation(summary = "分页查询独立评测历史")
    @PreAuthorize("@ss.hasPermission('ai-video:task:query')")
    public CommonResult<PageResult<TaskEvaluationRespVO>> page(@Valid TaskEvaluationPageReqVO request) {
        var result = evaluationService.page(request);
        return success(new PageResult<>(result.getList().stream()
                .map(record -> TaskEvaluationConvert.convert(record, false)).toList(), result.getTotal()));
    }
}
