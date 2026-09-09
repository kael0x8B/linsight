package com.linsight.module.aivideo.service.node;

import java.util.List;

public interface NodeCommandService {
    String createCommand(String commandId, Long nodeId, String commandType, Long aggregateId,
                         Integer configVersion, String idempotencyKey);
    List<NodeCommandDTO> getRecentCommands(Long nodeId);
    NodeCommandDTO pullCommand(Long nodeId);
    NodeCommandDTO reportCommand(Long nodeId, NodeCommandDTO report);
    NodeCommandDTO getCommandForNode(String commandId, Long nodeId);
    List<NodeCommandDTO> getExpiredCommandsGlobal();
    NodeCommandDTO expireCommand(Long id);
}
