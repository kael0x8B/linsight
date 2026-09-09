package com.linsight.module.aivideo.dal.mysql.algorithm;

import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.algorithm.PipelineVersionDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface PipelineVersionMapper extends BaseMapperX<PipelineVersionDO> {
    default List<PipelineVersionDO> selectListByAlgorithm(Long algorithmId) {
        return selectList(new LambdaQueryWrapperX<PipelineVersionDO>()
                .eq(PipelineVersionDO::getAlgorithmId, algorithmId)
                .orderByDesc(PipelineVersionDO::getVersion));
    }

    default PipelineVersionDO selectLatestByAlgorithm(Long algorithmId) {
        return selectOne(new LambdaQueryWrapperX<PipelineVersionDO>()
                .eq(PipelineVersionDO::getAlgorithmId, algorithmId)
                .orderByDesc(PipelineVersionDO::getVersion)
                .last("LIMIT 1"));
    }
}
