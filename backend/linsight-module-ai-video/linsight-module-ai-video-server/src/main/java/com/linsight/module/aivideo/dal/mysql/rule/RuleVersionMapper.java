package com.linsight.module.aivideo.dal.mysql.rule;

import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.rule.RuleVersionDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface RuleVersionMapper extends BaseMapperX<RuleVersionDO> {
    default List<RuleVersionDO> selectListByRule(Long ruleId) {
        return selectList(new LambdaQueryWrapperX<RuleVersionDO>()
                .eq(RuleVersionDO::getRuleId, ruleId)
                .orderByDesc(RuleVersionDO::getVersion));
    }

    default RuleVersionDO selectLatestByRule(Long ruleId) {
        return selectOne(new LambdaQueryWrapperX<RuleVersionDO>()
                .eq(RuleVersionDO::getRuleId, ruleId)
                .orderByDesc(RuleVersionDO::getVersion)
                .last("LIMIT 1"));
    }
}
