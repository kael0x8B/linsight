package com.linsight.module.aivideo.dal.mysql.algorithm;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.algorithm.AlgorithmDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface AlgorithmMapper extends BaseMapperX<AlgorithmDO> {
    default AlgorithmDO selectByCode(String code) {
        return selectOne(AlgorithmDO::getCode, code);
    }

    default PageResult<AlgorithmDO> selectPage(PageParam pageParam, String name, String code,
                                                String category, String sceneGroup,
                                                String implementationType, Integer status) {
        return selectPage(pageParam, new LambdaQueryWrapperX<AlgorithmDO>()
                .likeIfPresent(AlgorithmDO::getName, name)
                .likeIfPresent(AlgorithmDO::getCode, code)
                .eqIfPresent(AlgorithmDO::getCategory, category)
                .eqIfPresent(AlgorithmDO::getSceneGroup, sceneGroup)
                .eqIfPresent(AlgorithmDO::getImplementationType, implementationType)
                .eqIfPresent(AlgorithmDO::getStatus, status)
                .orderByAsc(AlgorithmDO::getId));
    }

    default List<AlgorithmDO> selectEnabledList() {
        return selectList(new LambdaQueryWrapperX<AlgorithmDO>()
                .eq(AlgorithmDO::getStatus, 0)
                .isNotNull(AlgorithmDO::getCurrentPipelineVersionId)
                .orderByAsc(AlgorithmDO::getId));
    }
}
