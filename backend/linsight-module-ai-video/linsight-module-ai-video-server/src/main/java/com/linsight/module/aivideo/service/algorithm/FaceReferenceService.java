package com.linsight.module.aivideo.service.algorithm;

import cn.hutool.crypto.digest.DigestUtil;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.algorithm.FaceReferenceDO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryEntryDO;
import com.linsight.module.aivideo.dal.mysql.algorithm.FaceReferenceMapper;
import com.linsight.module.aivideo.dal.mysql.algorithm.RecognitionLibraryMapper;
import com.linsight.module.aivideo.dal.mysql.algorithm.RecognitionLibraryEntryMapper;
import com.linsight.module.aivideo.framework.file.UploadContentValidator;
import com.linsight.module.infra.api.file.FileApi;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.time.LocalDateTime;
import java.util.*;
import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.algorithm.ErrorCodeConstants.*;

/** Owns consent-bound reference images and node-validated enrollment state. */
@Service public class FaceReferenceService {
    @Resource private FaceReferenceMapper mapper;
    @Resource private RecognitionLibraryMapper libraryMapper;
    @Resource private RecognitionLibraryEntryMapper entryMapper;
    @Resource private FileApi fileApi;
    @Resource private TransactionTemplate transactionTemplate;

    public Long register(Long libraryId, Long modelVersionId, String name, String code,
                         LocalDateTime validUntil, byte[] image, String commandId) {
        validateLibrary(libraryId);
        if (validUntil == null || !validUntil.isAfter(LocalDateTime.now()) || image.length == 0
                || image.length > 5 * 1024 * 1024 || UploadContentValidator.detectImageContentType(image) == null) {
            throw exception(RECOGNITION_LIBRARY_ENGINE_NOT_READY);
        }
        if (mapper.selectCount(new LambdaQueryWrapperX<FaceReferenceDO>()
                .eq(FaceReferenceDO::getLibraryId, libraryId)
                .in(FaceReferenceDO::getValidationStatus,List.of("READY","PENDING"))
                .gt(FaceReferenceDO::getValidUntil,LocalDateTime.now())) >= 256) {
            throw exception(RECOGNITION_LIBRARY_ENGINE_NOT_READY);
        }
        // Object storage is outside the database transaction.
        String objectRef = fileApi.createFile(image, "face-reference-" + UUID.fromString(commandId), "ai-video/face-reference",
                UploadContentValidator.detectImageContentType(image));
        return transactionTemplate.execute(tx -> {
            var entry = new RecognitionLibraryEntryDO(); entry.setLibraryId(libraryId);
            entry.setName(name); entry.setExternalCode(code); entry.setStatus(0);
            entry.setMediaRef(objectRef); entry.setFeatureStatus("PENDING"); entry.setAttributes("{\"schemaVersion\":\"1.0\",\"consentConfirmed\":true}");
            entryMapper.insert(entry);
            var reference = new FaceReferenceDO(); reference.setLibraryId(libraryId);
            reference.setEntryId(entry.getId()); reference.setModelVersionId(modelVersionId);
            reference.setObjectRef(objectRef); reference.setSha256(DigestUtil.sha256Hex(image));
            reference.setValidationStatus("PENDING"); reference.setValidationCommandId(commandId);
            reference.setValidUntil(validUntil); mapper.insert(reference); return reference.getId();
        });
    }

    public record ExistingPhoto(Long entryId, String objectRef, String sha256) {}

    /** Read and validate storage before starting the command transaction. */
    public ExistingPhoto prepareExistingPhoto(Long entryId) {
        var entry = entryMapper.selectById(entryId);
        if (entry == null) throw exception(RECOGNITION_LIBRARY_ENTRY_NOT_FOUND);
        validateLibrary(entry.getLibraryId());
        if (!Integer.valueOf(0).equals(entry.getStatus())) throw exception(FACE_EXTRACTION_INVALID, "请先启用该人员");
        if (entry.getMediaRef() == null || entry.getMediaRef().isBlank()) throw exception(FACE_EXTRACTION_INVALID, "请先上传人员正面照片");
        byte[] bytes = fileApi.readRegisteredImage(entry.getMediaRef()).getCheckedData();
        if (UploadContentValidator.detectImageContentType(bytes) == null) throw exception(FACE_EXTRACTION_INVALID, "照片格式无效，请重新上传 JPG 或 PNG");
        return new ExistingPhoto(entryId, entry.getMediaRef(), DigestUtil.sha256Hex(bytes));
    }

    /** Called inside the task's transaction, together with its durable ENROLL command. */
    public Long registerExisting(ExistingPhoto photo, Long modelVersionId, LocalDateTime validUntil, String commandId) {
        var entry = entryMapper.selectOne(new LambdaQueryWrapperX<RecognitionLibraryEntryDO>()
                .eq(RecognitionLibraryEntryDO::getId, photo.entryId()).last("FOR UPDATE"));
        if (entry == null) throw exception(RECOGNITION_LIBRARY_ENTRY_NOT_FOUND);
        validateLibrary(entry.getLibraryId());
        if (!Integer.valueOf(0).equals(entry.getStatus()) || !Objects.equals(entry.getMediaRef(), photo.objectRef()))
            throw exception(FACE_EXTRACTION_INVALID, "人员或照片已变更，请刷新后重试");
        if (validUntil == null || !validUntil.isAfter(LocalDateTime.now())) throw exception(FACE_EXTRACTION_INVALID, "请设置未来的参考有效期");
        var previous = mapper.selectList(new LambdaQueryWrapperX<FaceReferenceDO>().eq(FaceReferenceDO::getEntryId, entry.getId()));
        if (previous.stream().anyMatch(v -> "PENDING".equals(v.getValidationStatus()) && v.getCreateTime() != null
                && v.getCreateTime().isAfter(LocalDateTime.now().minusMinutes(3))))
            throw exception(FACE_EXTRACTION_INVALID, "网关正在处理，请稍候；超过 3 分钟可重试");
        if (mapper.selectCount(new LambdaQueryWrapperX<FaceReferenceDO>().eq(FaceReferenceDO::getLibraryId, entry.getLibraryId())
                .ne(FaceReferenceDO::getEntryId, entry.getId()).in(FaceReferenceDO::getValidationStatus,List.of("READY","PENDING"))
                .gt(FaceReferenceDO::getValidUntil,LocalDateTime.now())) >= 256) throw exception(FACE_EXTRACTION_INVALID, "参考库已达到 256 人上限");
        invalidateEntry(entry.getId());
        var reference = new FaceReferenceDO(); reference.setEntryId(entry.getId());reference.setLibraryId(entry.getLibraryId());
        reference.setModelVersionId(modelVersionId);reference.setObjectRef(photo.objectRef());reference.setSha256(photo.sha256());
        reference.setValidationStatus("PENDING");reference.setValidationCommandId(commandId);reference.setValidUntil(validUntil);
        mapper.insert(reference);
        var metadata = new LinkedHashMap<String,Object>();metadata.put("status","PROCESSING");metadata.put("commandId",commandId);
        metadata.put("requestedAt",System.currentTimeMillis());metadata.put("modelVersionId",modelVersionId);
        metadata.put("consentConfirmed",true);metadata.put("validUntil",validUntil.toString());
        var attributes = attributes(entry);attributes.put("faceExtraction",metadata);
        entry.setAttributes(JsonUtils.toJsonString(attributes));entry.setFeatureStatus("PENDING");entryMapper.updateById(entry);
        return reference.getId();
    }

    public void invalidateEntry(Long entryId) {
        for (var reference : mapper.selectList(new LambdaQueryWrapperX<FaceReferenceDO>().eq(FaceReferenceDO::getEntryId,entryId))) {
            if (!"REVOKED".equals(reference.getValidationStatus())) {reference.setValidationStatus("REVOKED");mapper.updateById(reference);}
        }
    }
    private static Map<String,Object> attributes(RecognitionLibraryEntryDO entry) {
        return entry.getAttributes() == null || entry.getAttributes().isBlank() ? new LinkedHashMap<>() : new LinkedHashMap<>(JsonUtils.parseMap(entry.getAttributes()));
    }
    public void applyValidation(Long id, String commandId, boolean valid) {
        applyValidation(id,commandId,valid,Map.of());
    }
    @org.springframework.transaction.annotation.Transactional(rollbackFor=Exception.class)
    public void applyValidation(Long id, String commandId, boolean valid, Map<String,Object> result) {
        var value = mapper.selectById(id);
        if (value == null || !Objects.equals(value.getValidationCommandId(), commandId)) {
            throw exception(RECOGNITION_LIBRARY_ENTRY_NOT_FOUND);
        }
        if (!"PENDING".equals(value.getValidationStatus())) return;
        var entry = entryMapper.selectOne(new LambdaQueryWrapperX<RecognitionLibraryEntryDO>()
                .eq(RecognitionLibraryEntryDO::getId,value.getEntryId()).last("FOR UPDATE"));
        value=mapper.selectById(id);
        if(value==null || !"PENDING".equals(value.getValidationStatus()) || !Objects.equals(value.getValidationCommandId(),commandId)) return;
        value.setValidationStatus(valid ? "READY" : "FAILED"); mapper.updateById(value);
        if (entry != null) {
            var attributes = attributes(entry);
            var metadata = new LinkedHashMap<String,Object>();metadata.put("status",valid ? "READY" : "FAILED");
            metadata.put("commandId",commandId);metadata.put("modelVersionId",value.getModelVersionId());
            metadata.put("completedAt",System.currentTimeMillis());metadata.put("consentConfirmed",true);
            metadata.put("validUntil",value.getValidUntil().toString());
            // Persist only supported result codes, never raw exception text, photo URLs or embeddings.
            for (String key : List.of("reason","device","backend")) {
                Object detail=result.get(key);
                if(detail instanceof String text && text.matches("[A-Z0-9_]{1,80}")) metadata.put(key,text);
            }
            attributes.put("faceExtraction",metadata);entry.setAttributes(JsonUtils.toJsonString(attributes));
            entry.setFeatureStatus(valid ? "READY" : "FAILED"); entryMapper.updateById(entry);
        }
    }

    public FaceReferenceDTO get(Long id) {
        var value = mapper.selectById(id);
        if (value == null) throw exception(RECOGNITION_LIBRARY_ENTRY_NOT_FOUND);
        validateLibrary(value.getLibraryId());
        return project(value);
    }

    public List<FaceReferenceDTO> list(Long libraryId) {
        validateLibrary(libraryId);
        var rows=mapper.selectList(new LambdaQueryWrapperX<FaceReferenceDO>()
                .eq(FaceReferenceDO::getLibraryId, libraryId).orderByAsc(FaceReferenceDO::getId));
        if(rows.isEmpty()) return List.of();
        var entries=entryMapper.selectBatchIds(rows.stream().map(FaceReferenceDO::getEntryId).toList())
                .stream().collect(java.util.stream.Collectors.toMap(RecognitionLibraryEntryDO::getId,v->v));
        return rows.stream().map(v->project(v,entries.get(v.getEntryId()))).filter(Objects::nonNull).toList();
    }

    public List<FaceReferenceDTO> ready(Long libraryId, Long version) {
        return list(libraryId).stream().filter(v -> version.equals(v.getModelVersionId())
                && "READY".equals(v.getValidationStatus()) && v.getValidUntil().isAfter(LocalDateTime.now())).toList();
    }

    public void revoke(Long id) {
        var value = mapper.selectById(id);
        if (value == null) throw exception(RECOGNITION_LIBRARY_ENTRY_NOT_FOUND);
        value.setValidationStatus("REVOKED"); mapper.updateById(value);
        var entry = entryMapper.selectById(value.getEntryId());
        if (entry != null) { entry.setStatus(1); entry.setFeatureStatus("REVOKED"); entryMapper.updateById(entry); }
    }

    private FaceReferenceDTO project(FaceReferenceDO value) {
        return project(value,entryMapper.selectById(value.getEntryId()));
    }
    private FaceReferenceDTO project(FaceReferenceDO value,RecognitionLibraryEntryDO entry) {
        if (entry == null) return null;
        var result = BeanUtils.toBean(value, FaceReferenceDTO.class);
        result.setName(entry.getName()); result.setExternalCode(entry.getExternalCode());
        if (!Integer.valueOf(0).equals(entry.getStatus())) result.setValidationStatus("REVOKED");
        return result;
    }

    private void validateLibrary(Long id) {
        var library = libraryMapper.selectById(id);
        if (library == null || !"FACE".equals(library.getLibraryType()) || !Integer.valueOf(0).equals(library.getStatus())) {
            throw exception(RECOGNITION_LIBRARY_NOT_FOUND);
        }
    }
}
