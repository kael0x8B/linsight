package com.linsight.module.aivideo.service.node;

import com.linsight.module.aivideo.controller.admin.node.vo.NodeUpgradeCreateReqVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeUpgradeCommandDetailRespVO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeUpgradeDO;

import java.io.IOException;
import java.util.List;

public interface NodeUpgradeService {
    Long createUpgrade(NodeUpgradeCreateReqVO reqVO) throws IOException;

    Long createRollback(Long nodeId);

    List<NodeUpgradeDO> getUpgradeList(Long nodeId);

    NodeUpgradeCommandDetailRespVO getCommandDetail(String commandId, Long nodeId);

    void applyCommandReport(NodeCommandDTO report);
}
