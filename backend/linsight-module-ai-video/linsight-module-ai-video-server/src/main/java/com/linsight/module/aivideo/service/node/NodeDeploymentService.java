package com.linsight.module.aivideo.service.node;

import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentConnectionReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentCreateReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentPreflightRespVO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeDeploymentDO;

import java.util.List;

public interface NodeDeploymentService {
    NodeDeploymentPreflightRespVO preflight(NodeDeploymentConnectionReqVO request);
    Long createDeployment(NodeDeploymentCreateReqVO request);
    NodeDeploymentDO getDeployment(Long id);
    List<NodeDeploymentDO> getRecentDeployments();
    com.linsight.framework.common.pojo.PageResult<NodeDeploymentDO> getPage(
            com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentPageReqVO request);
}
