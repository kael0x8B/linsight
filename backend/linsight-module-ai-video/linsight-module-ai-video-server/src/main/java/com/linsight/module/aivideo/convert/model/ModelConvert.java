package com.linsight.module.aivideo.convert.model;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelRespVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelDeploymentRespVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelTestRespVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelVersionRespVO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelDeploymentDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelTestDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelVersionDO;

import java.util.Collection;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public final class ModelConvert {

    private ModelConvert() {
    }

    public static ModelRespVO convert(ModelDO model) {
        return BeanUtils.toBean(model, ModelRespVO.class);
    }

    public static Collection<Long> collectSummaryVersionIds(PageResult<ModelDO> page,
                                                             List<ModelVersionDO> versions) {
        Map<Long, ModelVersionDO> latestByModel = latestVersionByModel(versions);
        return page.getList().stream()
                .map(model -> model.getCurrentVersionId() != null
                        ? model.getCurrentVersionId()
                        : latestByModel.get(model.getId()) == null
                                ? null : latestByModel.get(model.getId()).getId())
                .filter(Objects::nonNull)
                .toList();
    }

    public static PageResult<ModelRespVO> convertPage(PageResult<ModelDO> page,
                                                       List<ModelVersionDO> versions,
                                                       List<ModelDeploymentDO> deployments) {
        Map<Long, ModelVersionDO> versionsById = versions.stream()
                .collect(Collectors.toMap(ModelVersionDO::getId, item -> item));
        Map<Long, ModelVersionDO> latestByModel = latestVersionByModel(versions);
        Map<Long, Map<Long, ModelDeploymentDO>> latestDeploymentByVersionAndNode = new HashMap<>();
        Map<Long, Long> versionCounts = versions.stream()
                .collect(Collectors.groupingBy(ModelVersionDO::getModelId, Collectors.counting()));
        for (ModelDeploymentDO deployment : deployments) {
            latestDeploymentByVersionAndNode
                    .computeIfAbsent(deployment.getModelVersionId(), ignored -> new LinkedHashMap<>())
                    .putIfAbsent(deployment.getNodeId(), deployment);
        }

        List<ModelRespVO> result = page.getList().stream().map(model -> {
            ModelRespVO response = convert(model);
            response.setVersionCount(versionCounts.getOrDefault(model.getId(), 0L).intValue());
            ModelVersionDO summaryVersion = model.getCurrentVersionId() == null
                    ? latestByModel.get(model.getId()) : versionsById.get(model.getCurrentVersionId());
            if (summaryVersion == null) {
                response.setDeployedNodeCount(0);
                response.setReadyNodeCount(0);
                return response;
            }
            response.setLatestVersionId(summaryVersion.getId());
            response.setLatestVersion(summaryVersion.getVersion());
            response.setArtifactFormat(summaryVersion.getArtifactFormat());
            response.setArtifactSize(summaryVersion.getArtifactSize());
            response.setLicenseSpdx(summaryVersion.getLicenseSpdx());
            response.setValidationStatus(summaryVersion.getValidationStatus());
            response.setPublishStatus(summaryVersion.getPublishStatus());
            response.setOutputLabels(outputLabels(summaryVersion.getRuntimeManifest()));

            Collection<ModelDeploymentDO> currentDeployments = latestDeploymentByVersionAndNode
                    .getOrDefault(summaryVersion.getId(), Map.of()).values();
            response.setDeployedNodeCount(currentDeployments.size());
            response.setReadyNodeCount((int) currentDeployments.stream()
                    .filter(item -> "READY".equals(item.getActualStatus()))
                    .count());
            return response;
        }).toList();
        return new PageResult<>(result, page.getTotal());
    }

    private static List<String> outputLabels(String manifestJson) {
        if (manifestJson == null || manifestJson.isBlank()) return List.of();
        try {
            Map<String, Object> manifest = JsonUtils.parseMap(manifestJson);
            if (manifest == null || !(manifest.get("decoder") instanceof Map<?, ?> decoder)
                    || !(decoder.get("labels") instanceof List<?> labels)) return List.of();
            return labels.stream().filter(String.class::isInstance).map(String.class::cast)
                    .filter(label -> !label.isBlank()).distinct().toList();
        } catch (RuntimeException error) {
            // Legacy metadata must not break the catalog or imply capabilities it cannot prove.
            return List.of();
        }
    }

    private static Map<Long, ModelVersionDO> latestVersionByModel(List<ModelVersionDO> versions) {
        Map<Long, ModelVersionDO> latestByModel = new HashMap<>();
        for (ModelVersionDO version : versions) {
            latestByModel.putIfAbsent(version.getModelId(), version);
        }
        return latestByModel;
    }

    public static List<ModelVersionRespVO> convertVersions(List<ModelVersionDO> versions) {
        // artifactRef is deliberately absent from the response contract; downloads will use short-lived signed URLs.
        return versions.stream().map(item -> BeanUtils.toBean(item, ModelVersionRespVO.class)).toList();
    }

    public static List<ModelDeploymentRespVO> convertDeployments(List<ModelDeploymentDO> deployments) {
        return BeanUtils.toBean(deployments, ModelDeploymentRespVO.class);
    }

    public static ModelTestRespVO convertTest(ModelTestDO test) {
        return BeanUtils.toBean(test, ModelTestRespVO.class);
    }

    public static List<ModelTestRespVO> convertTests(List<ModelTestDO> tests) {
        return BeanUtils.toBean(tests, ModelTestRespVO.class);
    }
}
