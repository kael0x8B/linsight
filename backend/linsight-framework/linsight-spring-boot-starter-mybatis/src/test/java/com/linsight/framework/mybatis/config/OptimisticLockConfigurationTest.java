package com.linsight.framework.mybatis.config;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.annotation.Version;
import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import com.baomidou.mybatisplus.core.toolkit.Constants;
import com.baomidou.mybatisplus.extension.plugins.inner.OptimisticLockerInnerInterceptor;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.apache.ibatis.builder.StaticSqlSource;
import org.apache.ibatis.mapping.MappedStatement;
import org.apache.ibatis.mapping.SqlCommandType;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class OptimisticLockConfigurationTest {
    @Test
    void configuredInterceptorSuppliesOriginalVersionForUpdateSql() throws Exception {
        var interceptors = new LinsightMybatisAutoConfiguration().mybatisPlusInterceptor().getInterceptors();
        var optimistic = interceptors.stream().filter(OptimisticLockerInnerInterceptor.class::isInstance)
                .map(OptimisticLockerInnerInterceptor.class::cast).findFirst().orElse(null);
        assertNotNull(optimistic);
        var configuration = new MybatisConfiguration();
        TableInfoHelper.initTableInfo(new MapperBuilderAssistant(configuration, "test"), VersionedRow.class);
        var statement = new MappedStatement.Builder(configuration, "test.updateById",
                new StaticSqlSource(configuration, "UPDATE version_test SET version = ? WHERE id = ? AND version = ?"),
                SqlCommandType.UPDATE).build();
        var row = new VersionedRow();
        row.id = 1L;
        row.version = 3;
        Map<String, Object> parameters = new HashMap<>();
        parameters.put(Constants.ENTITY, row);
        optimistic.beforeUpdate(null, statement, parameters);
        assertEquals(3, parameters.get(Constants.MP_OPTLOCK_VERSION_ORIGINAL));
        assertEquals(4, row.version);
    }

    @TableName("version_test")
    static class VersionedRow {
        @TableId public Long id;
        @Version public Integer version;
    }
}
