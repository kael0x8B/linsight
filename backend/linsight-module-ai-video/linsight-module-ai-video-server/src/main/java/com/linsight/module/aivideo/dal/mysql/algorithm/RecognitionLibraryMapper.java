package com.linsight.module.aivideo.dal.mysql.algorithm;

import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface RecognitionLibraryMapper extends BaseMapperX<RecognitionLibraryDO> {
    default PageResult<RecognitionLibraryDO> selectPage(PageParam page, String name, String libraryType,
                                                         Integer status) {
        return selectPage(page, new LambdaQueryWrapperX<RecognitionLibraryDO>()
                .likeIfPresent(RecognitionLibraryDO::getName, name)
                .eqIfPresent(RecognitionLibraryDO::getLibraryType, libraryType)
                .eqIfPresent(RecognitionLibraryDO::getStatus, status)
                .orderByDesc(RecognitionLibraryDO::getId));
    }

    default RecognitionLibraryDO selectByCode(String code) {
        return selectOne(RecognitionLibraryDO::getCode, code);
    }
}
