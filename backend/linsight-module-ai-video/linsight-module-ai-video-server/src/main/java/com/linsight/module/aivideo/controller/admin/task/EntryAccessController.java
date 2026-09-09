package com.linsight.module.aivideo.controller.admin.task;
import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.admin.task.vo.*;
import com.linsight.module.aivideo.service.task.EntryAccessService;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import java.util.*;
import java.io.IOException;
import static com.linsight.framework.common.pojo.CommonResult.success;
@RestController @Validated @Tag(name="管理后台 - 入口主动刷脸")
@RequestMapping("/ai-video/task/entry-access")
public class EntryAccessController {
    @Resource private EntryAccessService service;
    @GetMapping("/list") @Operation(summary="入口配置列表") @PreAuthorize("@ss.hasPermission('ai-video:task:query')")
    public CommonResult<List<Map<String,Object>>> list(@RequestParam(required=false) Long cameraId,@RequestParam(required=false) Long nodeId){return success(service.listEntries(cameraId,nodeId));}
    @GetMapping("/station-status") @Operation(summary="入口自动值守状态和最近结果") @PreAuthorize("@ss.hasPermission('ai-video:task:query')")
    public CommonResult<Map<String,Object>> stationStatus(@RequestParam Long id,@RequestParam(required=false) Long nodeId){return success(service.stationStatus(id,nodeId));}
    @PostMapping("/save") @Operation(summary="保存版本化入口配置") @PreAuthorize("@ss.hasPermission('ai-video:task:update') and @ss.hasPermission('ai-video:library:query')")
    public CommonResult<Long> save(@Valid @RequestBody EntryAccessSaveReqVO r){return success(service.save(r));}
    @PostMapping("/enable") @Operation(summary="启用摄像头主动刷脸配置") @PreAuthorize("@ss.hasPermission('ai-video:task:start') and @ss.hasPermission('ai-video:library:query')")
    public CommonResult<Boolean> enable(@RequestParam Long id,@RequestParam(required=false) Long nodeId){service.enable(id,nodeId);return success(true);}
    @PostMapping("/stop") @Operation(summary="停用入口并取消核验") @PreAuthorize("@ss.hasPermission('ai-video:task:update')")
    public CommonResult<Boolean> stop(@RequestParam Long id,@RequestParam(required=false) Long nodeId){service.stop(id,nodeId);return success(true);}
    @DeleteMapping("/delete") @Operation(summary="删除已停用入口，保留历史记录") @PreAuthorize("@ss.hasPermission('ai-video:task:delete')")
    public CommonResult<Boolean> delete(@RequestParam Long id,@RequestParam(required=false) Long nodeId){service.delete(id,nodeId);return success(true);}
    @PostMapping("/enroll") @Operation(summary="登记本人授权照片并由网关校验") @PreAuthorize("@ss.hasPermission('ai-video:library:create') and @ss.hasPermission('ai-video:model:test')")
    public CommonResult<Long> enroll(@Valid FaceEnrollmentReqVO r) throws IOException{return success(service.enroll(r));}
    @GetMapping("/extraction-status") @Operation(summary="查询照片提取结果") @PreAuthorize("@ss.hasPermission('ai-video:library:update') and @ss.hasPermission('ai-video:model:test')")
    public CommonResult<Map<String,Object>> extractionStatus(@RequestParam Long id){return success(service.extractionStatus(id));}
    @PostMapping("/extract") @Operation(summary="为已录入人员提取特征，复用原人员档案") @PreAuthorize("@ss.hasPermission('ai-video:library:update') and @ss.hasPermission('ai-video:model:test')")
    public CommonResult<Long> extract(@Valid @RequestBody FaceExtractionReqVO r){return success(service.extract(r));}
    @PostMapping("/start") @Operation(summary="本人主动发起入口核验") @PreAuthorize("@ss.hasPermission('ai-video:task:start') and @ss.hasPermission('ai-video:library:query')")
    public CommonResult<Long> start(@Valid @RequestBody EntryScanCreateReqVO r){return success(service.start(r));}
    @PostMapping("/cancel") @Operation(summary="取消本次入口核验") @PreAuthorize("@ss.hasPermission('ai-video:task:start')")
    public CommonResult<Boolean> cancel(@RequestParam Long id){service.cancel(id);return success(true);}
    @GetMapping("/get") @Operation(summary="查询核验及权限结果") @PreAuthorize("@ss.hasPermission('ai-video:task:query')")
    public CommonResult<Map<String,Object>> get(@RequestParam Long id){return success(service.get(id));}
    @GetMapping("/history") @Operation(summary="查询最近50次核验") @PreAuthorize("@ss.hasPermission('ai-video:task:query')")
    public CommonResult<List<Map<String,Object>>> history(@RequestParam(required=false) Long entryId){return success(service.history(entryId));}
}
