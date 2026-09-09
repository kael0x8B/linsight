package com.linsight.module.aivideo.dal.mysql.node;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import org.apache.ibatis.annotations.*;

/** Short database critical sections only; never hold this lock during SSH or file upload. */
@Mapper
@InterceptorIgnore(tenantLine = "true")
public interface NodeOperationMutexMapper {
    @Insert("INSERT IGNORE INTO ai_node_operation_mutex (tenant_id, resource_key) VALUES (#{tenantId}, #{key})")
    int ensure(@Param("tenantId") Long tenantId, @Param("key") String key);

    @Select("SELECT resource_key FROM ai_node_operation_mutex WHERE tenant_id=#{tenantId} AND resource_key=#{key} FOR UPDATE")
    String lock(@Param("tenantId") Long tenantId, @Param("key") String key);
}
