package com.linsight.module.aivideo.service.model;

import com.linsight.module.aivideo.controller.admin.model.vo.ModelTestCreateReqVO;
import com.linsight.module.aivideo.controller.node.model.vo.ModelCommandDetailRespVO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelDeploymentDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelTestDO;
import com.linsight.module.aivideo.service.node.NodeCommandDTO;

import java.io.IOException;
import java.util.List;
import java.util.Collection;

public interface ModelExecutionService {
    void validateFaceVerificationReady(Long modelVersionId, Long nodeId);
    java.util.Map<Long, Long> getNodeCounts(java.util.Collection<Long> nodeIds);
    boolean hasDeploymentOnNode(Long modelVersionId, Long nodeId);
    Long uninstallModel(Long modelVersionId, Long nodeId);
    List<ModelDeploymentDO> getNodeDeployments(Long nodeId);
    Long deployModel(Long modelVersionId, Long nodeId);
    List<ModelDeploymentDO> getDeployments(Long modelVersionId);
    List<ModelDeploymentDO> getDeployments(Collection<Long> modelVersionIds);
    Long createTest(ModelTestCreateReqVO reqVO) throws IOException;
    ModelTestDO getTest(Long id);
    List<ModelTestDO> getTests(Long modelVersionId);
    ModelCommandDetailRespVO getCommandDetail(String commandId, Long nodeId);
    void validateDeploymentReady(Long modelVersionId, Long nodeId);
    void applyCommandReport(NodeCommandDTO report);
}
