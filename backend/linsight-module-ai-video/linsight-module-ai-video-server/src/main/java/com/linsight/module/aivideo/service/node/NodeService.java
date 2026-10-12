package com.linsight.module.aivideo.service.node;

import com.linsight.module.aivideo.controller.admin.node.vo.NodeBootstrapTokenRespVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeHeartbeatReqVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeHeartbeatRespVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeRegisterReqVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeRegistrationRespVO;
import com.linsight.module.aivideo.dal.dataobject.node.EdgeNodeDO;

import java.util.List;
import java.time.LocalDateTime;

public interface NodeService {
    NodeEvaluationSnapshotDTO getEvaluationSnapshot(Long nodeId);
    NodeModelEnvironmentDTO getModelEnvironment(Long nodeId);

    boolean supportsAlgorithmPackages(Long nodeId);

    NodeTaskCapacityPreflightDTO preflightTaskCapacity(Long nodeId, Long taskId,
                                                       java.util.Collection<Long> modelVersionIds);

    void removeGatewayTask(Long nodeId, Long taskId, long expectedRevision);
    boolean supportsModelUninstall(Long nodeId);
    List<NodeRuntimeSummaryDTO> getRuntimeSummaries(java.util.Collection<Long> ids);

    NodeBootstrapTokenRespVO createBootstrapToken(String name, Integer ttlMinutes);

    NodeRegistrationRespVO registerNode(NodeRegisterReqVO registerReqVO, String ipAddress);

    boolean authenticateNode(Long nodeId, Long tenantId, String credential);

    NodeHeartbeatRespVO reportHeartbeat(Long nodeId, NodeHeartbeatReqVO heartbeatReqVO);

    void validateNodeAvailable(Long nodeId);

    void validateNodeExists(Long nodeId);

    List<EdgeNodeDO> getEnabledNodes();

    List<EdgeNodeDO> getOnlineNodesGlobal();

    void markOfflineIfHeartbeatExpired(Long nodeId, LocalDateTime cutoff);

}
