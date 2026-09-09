package com.linsight.module.aivideo.dal.mysql.integration;

import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.integration.WebhookEndpointDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface WebhookEndpointMapper extends BaseMapperX<WebhookEndpointDO> {
    default PageResult<WebhookEndpointDO> selectPage(PageParam pageParam, String name, Integer status) {
        return selectPage(pageParam, new LambdaQueryWrapperX<WebhookEndpointDO>()
                .likeIfPresent(WebhookEndpointDO::getName, name)
                .eqIfPresent(WebhookEndpointDO::getStatus, status)
                .orderByDesc(WebhookEndpointDO::getId));
    }

    default List<WebhookEndpointDO> selectEnabled() {
        return selectList(new LambdaQueryWrapperX<WebhookEndpointDO>()
                .eq(WebhookEndpointDO::getStatus, 0)
                .orderByAsc(WebhookEndpointDO::getId));
    }

    @Update("""
            UPDATE ai_webhook_endpoint
            SET success_count = success_count + 1, last_success_time = CURRENT_TIMESTAMP(3),
                last_error = NULL, update_time = CURRENT_TIMESTAMP
            WHERE id = #{id} AND deleted = b'0'
            """)
    int recordSuccess(Long id);

    @Update("""
            UPDATE ai_webhook_endpoint
            SET failure_count = failure_count + 1, last_failure_time = CURRENT_TIMESTAMP(3),
                last_error = #{error}, update_time = CURRENT_TIMESTAMP
            WHERE id = #{id} AND deleted = b'0'
            """)
    int recordFailure(Long id, String error);
}
