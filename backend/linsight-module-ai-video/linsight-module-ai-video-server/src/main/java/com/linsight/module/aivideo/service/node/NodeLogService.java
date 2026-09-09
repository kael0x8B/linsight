package com.linsight.module.aivideo.service.node;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDiagnosticCreateReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDiagnosticRespVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeLogPageReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeLogRespVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeLogEntryReqVO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeDiagnosticBundleDO;

import java.util.List;

public interface NodeLogService {
    int cleanupExpiredLogs();
    void ingest(Long nodeId, List<NodeLogEntryReqVO> entries);

    PageResult<NodeLogRespVO> getPage(NodeLogPageReqVO reqVO);
    Long getSnapshotMaxId(Long nodeId);

    List<NodeLogRespVO> getContext(Long id, int before, int after);

    Long createDiagnostic(NodeDiagnosticCreateReqVO reqVO);

    NodeDiagnosticRespVO getDiagnostic(Long id);

    List<NodeDiagnosticRespVO> getDiagnostics(Long nodeId);

    List<NodeDiagnosticBundleDO> getQueuedDiagnosticsGlobal();

    void buildDiagnostic(Long id);
}
