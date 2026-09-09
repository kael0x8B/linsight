package com.linsight.module.aivideo.service.node;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeRespVO;
import com.linsight.module.aivideo.service.task.TaskService;
import com.linsight.module.aivideo.service.model.ModelExecutionService;
import com.linsight.framework.common.util.object.BeanUtils;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import java.util.List;

@Service
public class NodeOverviewService {
    @Resource private NodeService nodeService;
    @Resource private TaskService taskService;
    @Resource private ModelExecutionService modelService;
    public List<NodeRespVO> getNodes() {
        var nodes = BeanUtils.toBean(nodeService.getEnabledNodes(), NodeRespVO.class);
        var ids = nodes.stream().map(NodeRespVO::getId).toList();
        var tasks = taskService.getNodeCounts(ids);
        var models = modelService.getNodeCounts(ids);
        nodes.forEach(node -> { node.setTaskCount(tasks.getOrDefault(node.getId(), 0L)); node.setModelCount(models.getOrDefault(node.getId(), 0L)); });
        return nodes;
    }
}
