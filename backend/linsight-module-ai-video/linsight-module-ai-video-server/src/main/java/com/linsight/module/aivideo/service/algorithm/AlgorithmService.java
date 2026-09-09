package com.linsight.module.aivideo.service.algorithm;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.AlgorithmPageReqVO;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.AlgorithmSaveReqVO;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.PipelineSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.AlgorithmDO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.PipelineVersionDO;

import java.util.List;
import java.util.Map;

public interface AlgorithmService {
    List<AlgorithmSummaryDTO> getSummaries(java.util.Collection<Long> ids);
    Long createAlgorithm(AlgorithmSaveReqVO reqVO);
    void updateAlgorithm(AlgorithmSaveReqVO reqVO);
    AlgorithmDO getAlgorithm(Long id);
    PageResult<AlgorithmDO> getAlgorithmPage(AlgorithmPageReqVO reqVO);
    List<AlgorithmDO> getRunnableAlgorithms();
    Map<Long, List<AlgorithmCapabilityDTO>> getModelCapabilities();
    Long savePipeline(PipelineSaveReqVO reqVO);
    List<String> validatePipeline(Long id);
    void publishPipeline(Long id);
    List<PipelineVersionDO> getPipelineVersions(Long algorithmId);
    PipelineVersionDO getPublishedPipeline(Long algorithmId, Long pipelineVersionId);
    String getPipelineAcceptanceStatus(Long algorithmId);
    Map<Long, String> getPipelineAcceptanceStatuses(List<AlgorithmDO> algorithms);
    void validatePipelineRunnable(PipelineVersionDO pipeline);
    /** Field validation collects real evidence without marking production acceptance as passed. */
    void validatePipelineRunnable(PipelineVersionDO pipeline, boolean validationOnly);
}
