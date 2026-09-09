package com.linsight.module.aivideo.dal.mysql.integration;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.integration.WebhookDeliveryDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface WebhookDeliveryMapper extends BaseMapperX<WebhookDeliveryDO> {
    default PageResult<WebhookDeliveryDO> selectPage(PageParam pageParam, Long endpointId,
                                                      String status, Boolean isTest) {
        return selectPage(pageParam, new LambdaQueryWrapperX<WebhookDeliveryDO>()
                .eqIfPresent(WebhookDeliveryDO::getEndpointId, endpointId)
                .eqIfPresent(WebhookDeliveryDO::getStatus, status)
                .eqIfPresent(WebhookDeliveryDO::getIsTest, isTest)
                .orderByDesc(WebhookDeliveryDO::getId));
    }

    @InterceptorIgnore(tenantLine = "true")
    @Select("""
            SELECT * FROM ai_webhook_delivery
            WHERE deleted = b'0' AND status IN ('PENDING', 'RETRY')
              AND next_attempt_time <= CURRENT_TIMESTAMP(3)
            ORDER BY next_attempt_time, id LIMIT 100
            """)
    List<WebhookDeliveryDO> selectReadyGlobal();
}
