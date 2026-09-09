package com.linsight.module.aivideo.controller.admin.algorithm;
import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.service.algorithm.FaceReferenceService;
import jakarta.annotation.Resource;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import java.util.*;
import static com.linsight.framework.common.pojo.CommonResult.success;
@RestController @Validated @Tag(name="管理后台 - 授权人脸参考")
@RequestMapping("/ai-video/algorithm/face-reference")
public class FaceReferenceController {
    @Resource private FaceReferenceService service;
    @GetMapping("/list") @Operation(summary="列出授权参考，不返回照片或模板") @PreAuthorize("@ss.hasPermission('ai-video:library:query')")
    public CommonResult<List<Map<String,Object>>> list(@RequestParam Long libraryId){
        return success(service.list(libraryId).stream().map(v->{Map<String,Object> r=new LinkedHashMap<>();
            r.put("id",v.getId());r.put("entryId",v.getEntryId());r.put("name",v.getName());r.put("externalCode",v.getExternalCode());
            r.put("modelVersionId",v.getModelVersionId());r.put("status",v.getValidUntil().isBefore(java.time.LocalDateTime.now())?"EXPIRED":v.getValidationStatus());r.put("validUntil",v.getValidUntil());return r;}).toList());
    }
    @PostMapping("/revoke") @Operation(summary="撤回参考授权，立即停止后续比对") @PreAuthorize("@ss.hasPermission('ai-video:library:update')")
    public CommonResult<Boolean> revoke(@RequestParam Long id){service.revoke(id);return success(true);}
}
