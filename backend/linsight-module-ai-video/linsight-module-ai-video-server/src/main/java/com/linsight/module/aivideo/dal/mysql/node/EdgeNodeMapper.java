package com.linsight.module.aivideo.dal.mysql.node;

import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.tenant.core.aop.TenantIgnore;
import com.linsight.module.aivideo.dal.dataobject.node.EdgeNodeDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface EdgeNodeMapper extends BaseMapperX<EdgeNodeDO> {

    @TenantIgnore
    default EdgeNodeDO selectForAuthentication(Long id) {
        return selectById(id);
    }

    @TenantIgnore
    default EdgeNodeDO selectByTenantIdAndCode(Long tenantId, String code) {
        return selectOne(EdgeNodeDO::getTenantId, tenantId, EdgeNodeDO::getCode, code);
    }

    default EdgeNodeDO selectByIpAddress(String ipAddress) {
        return selectOne(EdgeNodeDO::getIpAddress, ipAddress);
    }

    default int updateHeartbeatIfNotOlder(EdgeNodeDO update, Long sequence) {
        return update(update, new LambdaUpdateWrapper<EdgeNodeDO>()
                .eq(EdgeNodeDO::getId, update.getId())
                // A heartbeat can be committed by the control plane immediately before the
                // node loses power and fsyncs its local sequence. Accepting the same sequence
                // makes that retry idempotent while still rejecting genuinely older reports.
                .le(EdgeNodeDO::getHeartbeatSequence, sequence));
    }

    default List<EdgeNodeDO> selectEnabledList() {
        return selectList(new com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX<EdgeNodeDO>()
                .eq(EdgeNodeDO::getStatus, 0)
                .orderByDesc(EdgeNodeDO::getOnlineStatus)
                .orderByAsc(EdgeNodeDO::getName));
    }

    @InterceptorIgnore(tenantLine = "true")
    @Select("""
            SELECT * FROM ai_edge_node
            WHERE deleted = b'0' AND status = 0 AND online_status = 1
            ORDER BY id LIMIT 1000
            """)
    List<EdgeNodeDO> selectOnlineGlobal();

}
