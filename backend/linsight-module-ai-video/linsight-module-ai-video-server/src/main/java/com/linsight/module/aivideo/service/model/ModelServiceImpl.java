package com.linsight.module.aivideo.service.model;

import cn.hutool.core.util.StrUtil;
import cn.hutool.crypto.digest.DigestUtil;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelPageReqVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelSaveReqVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelVersionUploadReqVO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelVersionDO;
import com.linsight.module.aivideo.dal.mysql.model.ModelMapper;
import com.linsight.module.aivideo.dal.mysql.model.ModelVersionMapper;
import com.linsight.module.aivideo.framework.file.UploadContentValidator;
import com.linsight.module.infra.api.file.FileApi;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import java.io.IOException;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Collection;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.model.ErrorCodeConstants.*;

@Service
@Validated
public class ModelServiceImpl implements ModelService {
    @Override
    public ModelEvaluationSnapshotDTO getEvaluationSnapshot(Long modelVersionId) {
        var version = getVersion(modelVersionId);
        return new ModelEvaluationSnapshotDTO(version.getModelId(), version.getId(), version.getVersion(),
                version.getSha256(), version.getArtifactFormat(), version.getRuntimeManifest());
    }
    @Override
    public java.util.List<java.util.Map<String, Object>> getExecutableOptions() {
        var models = modelMapper.selectList(new com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX<ModelDO>().eq(ModelDO::getStatus, 0));
        var byId = models.stream().collect(java.util.stream.Collectors.toMap(ModelDO::getId, value -> value));
        if (byId.isEmpty()) return java.util.List.of();
        return modelVersionMapper.selectListByModelIds(byId.keySet()).stream()
                .filter(v -> "PUBLISHED".equals(v.getPublishStatus()) && "READY".equals(v.getExecutionStatus()))
                .map(v -> {
                    java.util.Map<String, Object> result = new java.util.LinkedHashMap<>();
                    result.put("id", v.getId()); result.put("modelId", v.getModelId());
                    result.put("name", byId.get(v.getModelId()).getName()); result.put("version", v.getVersion());
                    result.put("defaultVersion", Objects.equals(byId.get(v.getModelId()).getCurrentVersionId(), v.getId()));
                    result.put("format", v.getArtifactFormat()); result.put("manifest", JsonUtils.parseMap(v.getRuntimeManifest()));
                    return result;
                }).toList();
    }

    private static final String STATUS_DRAFT = "DRAFT";
    private static final String STATUS_PUBLISHED = "PUBLISHED";
    private static final String VALIDATION_VERIFIED = "VERIFIED";
    private static final long DIRECT_UPLOAD_MAX_BYTES = 64L * 1024 * 1024;
    private static final Map<String, String> FORMAT_BY_EXTENSION = Map.of(
            "onnx", "ONNX",
            "pt", "PYTORCH",
            "pth", "PYTORCH",
            "jit", "TORCHSCRIPT",
            "torchscript", "TORCHSCRIPT",
            "engine", "TENSORRT",
            "rknn", "RKNN",
            "zip", "ARCHIVE"
    );

    @Resource
    private ModelMapper modelMapper;
    @Resource
    private ModelVersionMapper modelVersionMapper;
    @Resource
    private FileApi fileApi;

    @Override
    public Long createModel(ModelSaveReqVO reqVO) {
        validateCodeUnique(null, reqVO.getCode());
        ModelDO model = BeanUtils.toBean(reqVO, ModelDO.class);
        modelMapper.insert(model);
        return model.getId();
    }

    @Override
    public void updateModel(ModelSaveReqVO reqVO) {
        validateModel(reqVO.getId());
        validateCodeUnique(reqVO.getId(), reqVO.getCode());
        modelMapper.updateById(BeanUtils.toBean(reqVO, ModelDO.class));
    }

    @Override
    public void deleteModel(Long id) {
        validateModel(id);
        if (modelVersionMapper.selectCountByModelId(id) > 0) {
            throw exception(MODEL_HAS_VERSIONS);
        }
        modelMapper.deleteById(id);
    }

    @Override
    public ModelDO getModel(Long id) {
        return validateModel(id);
    }

    /** Batch display projection; tenant filtering stays in the model owner's mappers. */
    @Override
    public java.util.Map<Long, java.util.Map<String, String>> getVersionDisplayNames(
            java.util.Collection<Long> versionIds) {
        if (versionIds == null || versionIds.isEmpty()) return java.util.Map.of();
        var versions = modelVersionMapper.selectByIds(versionIds);
        if (versions.isEmpty()) return java.util.Map.of();
        var models = modelMapper.selectByIds(versions.stream().map(ModelVersionDO::getModelId).distinct().toList());
        var names = models.stream().collect(java.util.stream.Collectors.toMap(ModelDO::getId, ModelDO::getName));
        var result = new java.util.HashMap<Long, java.util.Map<String, String>>();
        for (var version : versions) {
            String name = names.get(version.getModelId());
            if (name != null) result.put(version.getId(), java.util.Map.of(
                    "name", name, "version", java.util.Objects.toString(version.getVersion(), "")));
        }
        return result;
    }

    @Override
    public ModelVersionDO getVersion(Long id) {
        ModelVersionDO version = id == null ? null : modelVersionMapper.selectById(id);
        if (version == null) throw exception(MODEL_VERSION_NOT_FOUND);
        return version;
    }

    @Override
    public PageResult<ModelDO> getModelPage(ModelPageReqVO reqVO) {
        return modelMapper.selectPage(reqVO, reqVO.getName(), reqVO.getCode(), reqVO.getSourceType(),
                reqVO.getArtifactFormat(), reqVO.getPublishStatus(), reqVO.getStatus());
    }

    @Override
    public Long uploadVersion(ModelVersionUploadReqVO reqVO) throws IOException {
        validateModel(reqVO.getModelId());
        if (modelVersionMapper.selectByModelAndVersion(reqVO.getModelId(), reqVO.getVersion()) != null) {
            throw exception(MODEL_VERSION_DUPLICATE);
        }
        byte[] content = reqVO.getFile().getBytes();
        if (content.length == 0) {
            throw exception(MODEL_ARTIFACT_EMPTY);
        }
        if (content.length > DIRECT_UPLOAD_MAX_BYTES) {
            throw exception(MODEL_ARTIFACT_TOO_LARGE);
        }
        String artifactName;
        String format;
        try {
            artifactName = UploadContentValidator.safeFileName(
                    reqVO.getFile().getOriginalFilename(), "model.bin");
            format = detectFormat(artifactName);
        } catch (IllegalArgumentException error) {
            throw exception(MODEL_FORMAT_UNSUPPORTED);
        }
        if (!UploadContentValidator.matchesModelFormat(format, content)) {
            throw exception(MODEL_FORMAT_UNSUPPORTED);
        }
        String sha256 = DigestUtil.sha256Hex(content);
        // The same general-purpose weight may intentionally back several logical models.
        // Only reject duplicate bytes inside the same logical model.
        if (modelVersionMapper.selectByModelAndSha256(reqVO.getModelId(), sha256) != null) {
            throw exception(MODEL_ARTIFACT_DUPLICATE);
        }

        // Object storage is called before the single-row database write, never from a database transaction.
        String artifactRef = fileApi.createFile(content, artifactName,
                "ai-video/model/" + reqVO.getModelId(), reqVO.getFile().getContentType());

        ModelVersionDO version = BeanUtils.toBean(reqVO, ModelVersionDO.class);
        version.setArtifactRef(artifactRef);
        version.setArtifactName(artifactName);
        version.setArtifactFormat(format);
        version.setRuntimeManifest(normalizeRuntimeManifest(reqVO.getRuntimeManifest()));
        version.setArtifactSize((long) content.length);
        version.setSha256(sha256);
        version.setLicenseSpdx(reqVO.getLicenseSpdx().trim());
        version.setValidationStatus(VALIDATION_VERIFIED);
        version.setPublishStatus(STATUS_DRAFT);
        modelVersionMapper.insert(version);
        return version.getId();
    }

    @Override
    public List<ModelVersionDO> getVersionList(Long modelId) {
        validateModel(modelId);
        return modelVersionMapper.selectListByModelId(modelId);
    }

    @Override
    public List<ModelVersionDO> getVersionList(Collection<Long> modelIds) {
        if (modelIds == null || modelIds.isEmpty()) {
            return List.of();
        }
        return modelVersionMapper.selectListByModelIds(modelIds);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void publishVersion(Long versionId) {
        ModelVersionDO version = modelVersionMapper.selectById(versionId);
        if (version == null) {
            throw exception(MODEL_VERSION_NOT_FOUND);
        }
        ModelDO model = validateModel(version.getModelId());
        if (!VALIDATION_VERIFIED.equals(version.getValidationStatus())) {
            throw exception(MODEL_VERSION_VALIDATION_BLOCKED);
        }
        if (StrUtil.isBlank(version.getSourceRepository()) || StrUtil.isBlank(version.getSourceRevision())) {
            throw exception(MODEL_SOURCE_INCOMPLETE);
        }
        validateRuntimeManifest(version.getRuntimeManifest());
        modelVersionMapper.supersedeCurrentPublished(model.getId(), version.getId());
        version.setPublishStatus(STATUS_PUBLISHED);
        version.setPublishedTime(LocalDateTime.now());
        modelVersionMapper.updateById(version);
        model.setCurrentVersionId(version.getId());
        modelMapper.updateById(model);
    }

    private ModelDO validateModel(Long id) {
        ModelDO model = id == null ? null : modelMapper.selectById(id);
        if (model == null) {
            throw exception(MODEL_NOT_FOUND);
        }
        return model;
    }

    private void validateCodeUnique(Long id, String code) {
        ModelDO sameCode = modelMapper.selectByCode(code);
        if (sameCode != null && !Objects.equals(sameCode.getId(), id)) {
            throw exception(MODEL_CODE_DUPLICATE);
        }
    }

    private static String detectFormat(String fileName) {
        String extension = StrUtil.subAfter(fileName, '.', true).toLowerCase(Locale.ROOT);
        String format = FORMAT_BY_EXTENSION.get(extension);
        if (format == null) {
            throw exception(MODEL_FORMAT_UNSUPPORTED);
        }
        return format;
    }

    private static String normalizeRuntimeManifest(String value) {
        if (StrUtil.isBlank(value)) {
            return null;
        }
        validateRuntimeManifest(value);
        return JsonUtils.toJsonString(JsonUtils.parseMap(value));
    }

    static void validateRuntimeManifest(String value) {
        if (StrUtil.isBlank(value)) {
            throw exception(MODEL_RUNTIME_MANIFEST_INVALID);
        }
        final Map<String, Object> manifest;
        try {
            manifest = JsonUtils.parseMap(value);
        } catch (RuntimeException error) {
            throw exception(MODEL_RUNTIME_MANIFEST_INVALID);
        }
        Object preprocessValue = manifest.get("preprocess");
        String targetPlatform = manifest.get("targetPlatform") instanceof String target ? target : null;
        if (manifest.containsKey("targetPlatform") && (targetPlatform == null
                || !targetPlatform.matches("[a-z0-9][a-z0-9._-]{0,63}"))) {
            throw exception(MODEL_RUNTIME_MANIFEST_INVALID);
        }
        if (manifest.containsKey("execution")) {
            if (!(manifest.get("execution") instanceof Map<?, ?> execution)
                    || !(execution.get("provider") instanceof String provider)
                    || !provider.matches("[a-z0-9][a-z0-9._-]{0,63}")
                    || !validExecutionToken(execution, "target")
                    || !validExecutionToken(execution, "runtime")
                    || !validRuntimeVersion(execution, "minRuntimeVersion")
                    || (execution.containsKey("minRuntimeVersion") && !execution.containsKey("runtime"))
                    || (targetPlatform != null && execution.containsKey("target")
                        && !targetPlatform.equals(execution.get("target")))) {
                throw exception(MODEL_RUNTIME_MANIFEST_INVALID);
            }
        }
        Object decoderValue = manifest.get("decoder");
        if (!"1.0".equals(manifest.get("schemaVersion"))
                || !Set.of("OBJECT_DETECTION", "CLASSIFICATION", "OCR", "FACE_VERIFICATION")
                        .contains(manifest.get("taskType"))
                || !(preprocessValue instanceof Map<?, ?> preprocess)
                || !(decoderValue instanceof Map<?, ?> decoder)
                || (preprocess.containsKey("resize") && !"STRETCH".equals(preprocess.get("resize"))
                    && !("LETTERBOX".equals(preprocess.get("resize"))
                        && "YOLO_PLATE".equals(decoder.get("type")))
                    && !("OCR_RIGHT_PAD".equals(preprocess.get("resize"))
                        && "PLATE_OCR_ROUTED".equals(decoder.get("type"))))
                || !Set.of("RGB", "BGR").contains(preprocess.get("color"))
                || !Set.of("NCHW", "NHWC").contains(preprocess.get("layout"))
                || !Set.of("FLOAT32", "UINT8").contains(preprocess.get("dtype"))
                || !Set.of("AUTO_DETECTION", "CLASSIFICATION", "CTC_GREEDY", "LPD_YUNET", "LPRNET",
                        "YOLO_PLATE", "CHINESE_PLATE_CTC", "PLATE_OCR_ROUTED",
                        "FACE_PAIR_SFACE", "FACE_PAIR_SFACE_RKNN")
                        .contains(decoder.get("type"))) {
            throw exception(MODEL_RUNTIME_MANIFEST_INVALID);
        }
        if (("YOLO_PLATE".equals(decoder.get("type"))
                && !"OBJECT_DETECTION".equals(manifest.get("taskType")))
                || (Set.of("CHINESE_PLATE_CTC", "PLATE_OCR_ROUTED").contains(decoder.get("type"))
                && !"OCR".equals(manifest.get("taskType")))) {
            throw exception(MODEL_RUNTIME_MANIFEST_INVALID);
        }
        if ("FACE_VERIFICATION".equals(manifest.get("taskType"))
                != Set.of("FACE_PAIR_SFACE", "FACE_PAIR_SFACE_RKNN").contains(decoder.get("type"))) {
            throw exception(MODEL_RUNTIME_MANIFEST_INVALID);
        }
        Object labels = decoder.get("labels");
        if (Set.of("AUTO_DETECTION", "CLASSIFICATION").contains(decoder.get("type"))
                && (!(labels instanceof List<?> values) || values.isEmpty())) {
            throw exception(MODEL_RUNTIME_MANIFEST_INVALID);
        }
    }

    private static boolean validExecutionToken(Map<?, ?> execution, String key) {
        return !execution.containsKey(key) || (execution.get(key) instanceof String value
                && value.matches("[a-z0-9][a-z0-9._-]{0,63}"));
    }

    private static boolean validRuntimeVersion(Map<?, ?> execution, String key) {
        return !execution.containsKey(key) || (execution.get(key) instanceof String value
                && value.matches("[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}"));
    }

}
