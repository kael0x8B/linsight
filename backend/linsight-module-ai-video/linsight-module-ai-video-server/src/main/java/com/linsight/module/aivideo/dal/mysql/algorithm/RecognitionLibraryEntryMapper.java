package com.linsight.module.aivideo.dal.mysql.algorithm;

import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryEntryDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface RecognitionLibraryEntryMapper extends BaseMapperX<RecognitionLibraryEntryDO> {
    default PageResult<RecognitionLibraryEntryDO> selectPage(PageParam page, Long libraryId, String name,
                                                              String featureStatus, Integer status) {
        return selectPage(page, new LambdaQueryWrapperX<RecognitionLibraryEntryDO>()
                .eq(RecognitionLibraryEntryDO::getLibraryId, libraryId)
                .likeIfPresent(RecognitionLibraryEntryDO::getName, name)
                .eqIfPresent(RecognitionLibraryEntryDO::getFeatureStatus, featureStatus)
                .eqIfPresent(RecognitionLibraryEntryDO::getStatus, status)
                .orderByDesc(RecognitionLibraryEntryDO::getId));
    }

    default long selectCountByLibraryId(Long libraryId) {
        return selectCount(RecognitionLibraryEntryDO::getLibraryId, libraryId);
    }
}
