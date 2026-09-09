package com.linsight.module.aivideo.controller.admin.algorithm;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.*;
import com.linsight.module.aivideo.convert.algorithm.RecognitionLibraryConvert;
import com.linsight.module.aivideo.service.algorithm.RecognitionLibraryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - AI 识别参考库")
@RestController
@RequestMapping("/ai-video/algorithm/library")
@Validated
public class RecognitionLibraryController {
    @Resource private RecognitionLibraryService service;

    @GetMapping("/page")
    @Operation(summary = "获得人脸、车牌或场景姿态库分页")
    @PreAuthorize("@ss.hasPermission('ai-video:library:query')")
    public CommonResult<PageResult<RecognitionLibraryRespVO>> page(@Valid RecognitionLibraryPageReqVO reqVO) {
        var page = service.getLibraryPage(reqVO);
        return success(RecognitionLibraryConvert.convertLibraries(page, service.getEntryCounts(page.getList())));
    }

    @GetMapping("/get")
    @Operation(summary = "获得识别参考库详情")
    @PreAuthorize("@ss.hasPermission('ai-video:library:query')")
    public CommonResult<RecognitionLibraryRespVO> get(@RequestParam Long id) {
        return success(RecognitionLibraryConvert.convertLibrary(service.getLibrary(id), service.getEntryCount(id)));
    }

    @PostMapping("/create")
    @Operation(summary = "创建识别参考库")
    @PreAuthorize("@ss.hasPermission('ai-video:library:create')")
    public CommonResult<Long> create(@Valid @RequestBody RecognitionLibrarySaveReqVO reqVO) {
        return success(service.createLibrary(reqVO));
    }

    @PutMapping("/update")
    @Operation(summary = "更新识别参考库")
    @PreAuthorize("@ss.hasPermission('ai-video:library:update')")
    public CommonResult<Boolean> update(@Valid @RequestBody RecognitionLibrarySaveReqVO reqVO) {
        service.updateLibrary(reqVO);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "删除空识别参考库")
    @PreAuthorize("@ss.hasPermission('ai-video:library:delete')")
    public CommonResult<Boolean> delete(@RequestParam Long id) {
        service.deleteLibrary(id);
        return success(true);
    }

    @GetMapping("/entry/page")
    @Operation(summary = "获得识别参考条目分页")
    @PreAuthorize("@ss.hasPermission('ai-video:library:query')")
    public CommonResult<PageResult<RecognitionLibraryEntryRespVO>> entryPage(
            @Valid RecognitionLibraryEntryPageReqVO reqVO) {
        return success(RecognitionLibraryConvert.convertEntries(service.getEntryPage(reqVO)));
    }

    @PostMapping("/entry/create")
    @Operation(summary = "创建识别参考条目")
    @PreAuthorize("@ss.hasPermission('ai-video:library:create')")
    public CommonResult<Long> createEntry(@Valid @RequestBody RecognitionLibraryEntrySaveReqVO reqVO) {
        return success(service.createEntry(reqVO));
    }

    @PutMapping("/entry/update")
    @Operation(summary = "更新识别参考条目")
    @PreAuthorize("@ss.hasPermission('ai-video:library:update')")
    public CommonResult<Boolean> updateEntry(@Valid @RequestBody RecognitionLibraryEntrySaveReqVO reqVO) {
        service.updateEntry(reqVO);
        return success(true);
    }

    @DeleteMapping("/entry/delete")
    @Operation(summary = "删除识别参考条目")
    @PreAuthorize("@ss.hasPermission('ai-video:library:delete')")
    public CommonResult<Boolean> deleteEntry(@RequestParam Long id) {
        service.deleteEntry(id);
        return success(true);
    }
}
