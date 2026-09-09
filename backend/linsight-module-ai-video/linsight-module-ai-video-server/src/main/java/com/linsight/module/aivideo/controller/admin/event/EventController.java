package com.linsight.module.aivideo.controller.admin.event;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.event.vo.EventActionReqVO;
import com.linsight.module.aivideo.controller.admin.event.vo.EventPageReqVO;
import com.linsight.module.aivideo.controller.admin.event.vo.EventRespVO;
import com.linsight.module.aivideo.service.event.EventService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static com.linsight.framework.common.pojo.CommonResult.success;
import static com.linsight.framework.web.core.util.WebFrameworkUtils.getLoginUserId;

@Tag(name = "管理后台 - AI 视频事件")
@RestController
@RequestMapping("/ai-video/event")
@Validated
public class EventController {
    @Resource private EventService eventService;

    @GetMapping("/page")
    @Operation(summary = "获得事件分页")
    @PreAuthorize("@ss.hasPermission('ai-video:event:query')")
    public CommonResult<PageResult<EventRespVO>> page(@Valid EventPageReqVO reqVO) {
        return success(eventService.getPageView(reqVO));
    }

    @GetMapping("/get")
    @Operation(summary = "获得事件证据与动作详情")
    @PreAuthorize("@ss.hasPermission('ai-video:event:query')")
    public CommonResult<EventRespVO> get(@RequestParam Long id) {
        return success(eventService.getDetail(id));
    }

    @PostMapping("/assign")
    @Operation(summary = "指派事件")
    @PreAuthorize("@ss.hasPermission('ai-video:event:assign')")
    public CommonResult<Boolean> assign(@RequestParam Long id, @Valid @RequestBody EventActionReqVO reqVO,
                                        HttpServletRequest request) {
        eventService.assign(id, reqVO, getLoginUserId(request));
        return success(true);
    }

    @PostMapping("/handle")
    @Operation(summary = "提交处置结果")
    @PreAuthorize("@ss.hasPermission('ai-video:event:handle')")
    public CommonResult<Boolean> handle(@RequestParam Long id, @Valid @RequestBody EventActionReqVO reqVO,
                                        HttpServletRequest request) {
        eventService.handle(id, reqVO, getLoginUserId(request));
        return success(true);
    }

    @PostMapping("/close")
    @Operation(summary = "关闭事件")
    @PreAuthorize("@ss.hasPermission('ai-video:event:close')")
    public CommonResult<Boolean> close(@RequestParam Long id, @Valid @RequestBody EventActionReqVO reqVO,
                                       HttpServletRequest request) {
        eventService.close(id, reqVO, getLoginUserId(request));
        return success(true);
    }

    @PostMapping("/false-positive")
    @Operation(summary = "标记误报并释放活动去重键")
    @PreAuthorize("@ss.hasPermission('ai-video:event:false-positive')")
    public CommonResult<Boolean> falsePositive(@RequestParam Long id,
                                                @Valid @RequestBody EventActionReqVO reqVO,
                                                HttpServletRequest request) {
        eventService.markFalsePositive(id, reqVO, getLoginUserId(request));
        return success(true);
    }
}
