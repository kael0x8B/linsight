package com.linsight.module.aivideo.dal.mysql.node;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.module.aivideo.dal.dataobject.node.NodeApplicationReleaseDO;
import org.apache.ibatis.annotations.*;
import java.util.List;

@Mapper
public interface NodeApplicationReleaseMapper extends BaseMapperX<NodeApplicationReleaseDO> {
    default PageResult<NodeApplicationReleaseDO> page(PageParam page) {
        return selectPage(page, new LambdaQueryWrapper<NodeApplicationReleaseDO>()
                .orderByDesc(NodeApplicationReleaseDO::getId));
    }
    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM ai_node_application_release WHERE deleted=b'0' AND status='QUEUED' ORDER BY id LIMIT 10")
    List<NodeApplicationReleaseDO> queued();

    @Update("UPDATE ai_node_application_release SET status='BUILDING', message='正在校验并构建签名升级包', executor_owner=#{owner}, lease_until=DATE_ADD(NOW(), INTERVAL 120 SECOND), update_time=NOW() WHERE id=#{id} AND deleted=b'0' AND status='QUEUED'")
    int claim(@Param("id") Long id, @Param("owner") String owner);

    @Update("UPDATE ai_node_application_release SET lease_until=DATE_ADD(NOW(), INTERVAL 120 SECOND) WHERE id=#{id} AND executor_owner=#{owner} AND status IN ('BUILDING','STORING') AND lease_until > NOW() AND deleted=b'0'")
    int heartbeat(@Param("id") Long id, @Param("owner") String owner);

    @InterceptorIgnore(tenantLine = "true")
    @Update("UPDATE ai_node_application_release SET status='FAILED', message='构建服务中断，制品未发布；可重试', finish_time=NOW(), update_time=NOW() WHERE deleted=b'0' AND status IN ('BUILDING','STORING') AND lease_until < NOW()")
    int expireLeases();
}
