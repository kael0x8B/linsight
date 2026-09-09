package com.linsight.module.aivideo.dal.mysql.rule;

import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.rule.RuleDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface RuleMapper extends BaseMapperX<RuleDO> {
    default RuleDO selectByCode(String code) {
        return selectOne(RuleDO::getCode, code);
    }

    default PageResult<RuleDO> selectPage(PageParam pageParam, String name, String code,
                                           String eventType, Integer status) {
        return selectPage(pageParam, new LambdaQueryWrapperX<RuleDO>()
                .likeIfPresent(RuleDO::getName, name)
                .likeIfPresent(RuleDO::getCode, code)
                .eqIfPresent(RuleDO::getEventType, eventType)
                .eqIfPresent(RuleDO::getStatus, status)
                .orderByDesc(RuleDO::getId));
    }

    default List<RuleDO> selectPublishedList() {
        return selectList(new LambdaQueryWrapperX<RuleDO>()
                .eq(RuleDO::getStatus, 0)
                .isNotNull(RuleDO::getCurrentVersionId)
                .orderByAsc(RuleDO::getId));
    }
}
