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
        Object decoderValue = manifest.get("decoder");
        if (!"1.0".equals(manifest.get("schemaVersion"))
                || !Set.of("OBJECT_DETECTION", "CLASSIFICATION", "OCR", "FACE_VERIFICATION")
                        .contains(manifest.get("taskType"))
                || !(preprocessValue instanceof Map<?, ?> preprocess)
                || !(decoderValue instanceof Map<?, ?> decoder)
                || (preprocess.containsKey("resize") && !"STRETCH".equals(preprocess.get("resize")))
                || !Set.of("RGB", "BGR").contains(preprocess.get("color"))
                || !Set.of("NCHW", "NHWC").contains(preprocess.get("layout"))
                || !Set.of("FLOAT32", "UINT8").contains(preprocess.get("dtype"))
                || !Set.of("AUTO_DETECTION", "CLASSIFICATION", "CTC_GREEDY", "LPD_YUNET", "LPRNET", "FACE_PAIR_SFACE", "FACE_PAIR_SFACE_RKNN")
                        .contains(decoder.get("type"))) {
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

}
