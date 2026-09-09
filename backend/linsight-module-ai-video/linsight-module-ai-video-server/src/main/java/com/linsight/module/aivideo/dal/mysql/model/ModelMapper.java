package com.linsight.module.aivideo.dal.mysql.model;

import cn.hutool.core.util.StrUtil;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.model.ModelDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface ModelMapper extends BaseMapperX<ModelDO> {

    default ModelDO selectByCode(String code) {
        return selectOne(ModelDO::getCode, code);
    }

    default PageResult<ModelDO> selectPage(PageParam pageParam, String name, String code,
                                            String sourceType, String artifactFormat,
                                            String publishStatus, Integer status) {
        LambdaQueryWrapperX<ModelDO> query = new LambdaQueryWrapperX<>();
        query.likeIfPresent(ModelDO::getName, name);
        query.likeIfPresent(ModelDO::getCode, code);
        query.eqIfPresent(ModelDO::getSourceType, sourceType);
        query.apply(StrUtil.isNotBlank(artifactFormat),
                "EXISTS (SELECT 1 FROM ai_model_version mv WHERE mv.model_id = ai_model.id " +
                        "AND mv.tenant_id = ai_model.tenant_id AND mv.deleted = 0 AND mv.artifact_format = {0})",
                artifactFormat);
        query.apply(StrUtil.isNotBlank(publishStatus),
                "EXISTS (SELECT 1 FROM ai_model_version mv WHERE mv.model_id = ai_model.id " +
                        "AND mv.tenant_id = ai_model.tenant_id AND mv.deleted = 0 AND mv.publish_status = {0})",
                publishStatus);
        query.eqIfPresent(ModelDO::getStatus, status);
        query.orderByDesc(ModelDO::getId);
        return selectPage(pageParam, query);
    }

}
