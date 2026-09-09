package com.linsight.module.aivideo.convert.algorithm;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.AlgorithmRespVO;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.PipelineVersionRespVO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.AlgorithmDO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.PipelineVersionDO;

import java.util.List;

public final class AlgorithmConvert {
    private AlgorithmConvert() {}

    public static AlgorithmRespVO convert(AlgorithmDO source) {
        AlgorithmRespVO target = new AlgorithmRespVO();
        target.setId(source.getId());
        target.setName(source.getName());
        target.setCode(source.getCode());
        target.setCategory(source.getCategory());
        target.setSceneGroup(source.getSceneGroup());
        target.setImplementationType(source.getImplementationType());
        target.setDescription(source.getDescription());
        target.setCapabilityKey(source.getCapabilityKey());
        target.setRequiredCapabilities(source.getRequiredCapabilities() == null
                ? List.of() : JsonUtils.parseArray(source.getRequiredCapabilities(), String.class));
        target.setEventType(source.getEventType());
        target.setDefaultModelId(source.getDefaultModelId());
        target.setCurrentPipelineVersionId(source.getCurrentPipelineVersionId());
        target.setParameterSchema(JsonUtils.parseMap(source.getParameterSchema()));
        target.setDefaultParameters(JsonUtils.parseMap(source.getDefaultParameters()));
        target.setStatus(source.getStatus());
        target.setCreateTime(source.getCreateTime());
        return target;
    }

    public static PageResult<AlgorithmRespVO> convertPage(PageResult<AlgorithmDO> page) {
        return new PageResult<>(page.getList().stream().map(AlgorithmConvert::convert).toList(), page.getTotal());
    }

    public static PipelineVersionRespVO convert(PipelineVersionDO source) {
        PipelineVersionRespVO target = new PipelineVersionRespVO();
        target.setId(source.getId());
        target.setAlgorithmId(source.getAlgorithmId());
        target.setVersion(source.getVersion());
        target.setDag(JsonUtils.parseMap(source.getDag()));
        target.setValidationStatus(source.getValidationStatus());
        target.setValidationErrors(JsonUtils.parseArray(source.getValidationErrors(), String.class));
        target.setPublishedTime(source.getPublishedTime());
        target.setCreateTime(source.getCreateTime());
        return target;
    }

    public static List<PipelineVersionRespVO> convertPipelines(List<PipelineVersionDO> source) {
        return source.stream().map(AlgorithmConvert::convert).toList();
    }
}
