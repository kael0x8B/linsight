package com.linsight.module.aivideo.dal.mysql.node;

import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.tenant.core.aop.TenantIgnore;
import com.linsight.module.aivideo.dal.dataobject.node.NodeBootstrapTokenDO;
import org.apache.ibatis.annotations.Mapper;

import java.time.LocalDateTime;

@Mapper
public interface NodeBootstrapTokenMapper extends BaseMapperX<NodeBootstrapTokenDO> {

    @TenantIgnore
    default NodeBootstrapTokenDO selectByTokenDigest(String tokenDigest) {
        return selectOne(NodeBootstrapTokenDO::getTokenDigest, tokenDigest);
    }

    @TenantIgnore
    default int markUsedIfAvailable(Long id, LocalDateTime usedTime) {
        NodeBootstrapTokenDO update = new NodeBootstrapTokenDO();
        update.setId(id);
        update.setUsedTime(usedTime);
        update.setUpdater("node-bootstrap");
        return update(update, new LambdaUpdateWrapper<NodeBootstrapTokenDO>()
                .eq(NodeBootstrapTokenDO::getId, id)
                .isNull(NodeBootstrapTokenDO::getUsedTime));
    }

}
