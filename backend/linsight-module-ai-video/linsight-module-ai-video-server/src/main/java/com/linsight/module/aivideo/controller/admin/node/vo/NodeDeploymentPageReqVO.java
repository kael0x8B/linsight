package com.linsight.module.aivideo.controller.admin.node.vo;
import com.linsight.framework.common.pojo.PageParam;
import jakarta.validation.constraints.Positive;
import lombok.Data;
import lombok.EqualsAndHashCode;
@Data @EqualsAndHashCode(callSuper = true)
public class NodeDeploymentPageReqVO extends PageParam {
    @Positive private Long nodeId;
}
