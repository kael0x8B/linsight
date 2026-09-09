package com.linsight.module.aivideo.dal.mysql.settings;

import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.settings.GlobalSettingsVersionDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface GlobalSettingsVersionMapper extends BaseMapperX<GlobalSettingsVersionDO> {
    default GlobalSettingsVersionDO selectLatest() {
        return selectOne(new LambdaQueryWrapperX<GlobalSettingsVersionDO>()
                .orderByDesc(GlobalSettingsVersionDO::getVersionNo)
                .last("LIMIT 1"));
    }

    default List<GlobalSettingsVersionDO> selectRecent() {
        return selectList(new LambdaQueryWrapperX<GlobalSettingsVersionDO>()
                .orderByDesc(GlobalSettingsVersionDO::getVersionNo)
                .last("LIMIT 50"));
    }
}
