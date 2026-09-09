package com.linsight.module.aivideo.controller.node.event;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.node.event.vo.EventIngestReqVO;
import com.linsight.module.aivideo.controller.node.event.vo.EventTransitionReqVO;
import com.linsight.module.aivideo.service.event.EventService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.core.Authentication;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.time.LocalDateTime;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "节点 API - AI 视频事件")
@RestController
@RequestMapping("/ai-video/event")
@Validated
public class EventNodeController {
    @Resource private EventService eventService;

    @PostMapping("/ingest")
    @Operation(summary = "幂等写入规则确认事件")
    public CommonResult<Long> ingest(@Valid @RequestBody EventIngestReqVO reqVO, Authentication authentication) {
        return success(eventService.ingest(reqVO, (Long) authentication.getPrincipal()));
    }

    @PostMapping("/transition")
    @Operation(summary = "上报规则恢复或关闭状态")
    public CommonResult<Boolean> transition(@Valid @RequestBody EventTransitionReqVO reqVO,
                                             Authentication authentication) {
        eventService.applyRuntimeTransition(reqVO, (Long) authentication.getPrincipal());
        return success(true);
    }

    @PostMapping("/{eventId}/media")
    @Operation(summary = "上传事件截图或前后视频证据")
    public CommonResult<Long> uploadMedia(
            @PathVariable Long eventId,
            @RequestParam @NotBlank String mediaType,
            @RequestPart("file") MultipartFile file,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            LocalDateTime captureStartTime,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            LocalDateTime captureEndTime,
            Authentication authentication) throws IOException {
        return success(eventService.uploadMedia(eventId, (Long) authentication.getPrincipal(), mediaType,
                file.getOriginalFilename(), file.getContentType(), file.getBytes(), captureStartTime, captureEndTime));
    }
}
