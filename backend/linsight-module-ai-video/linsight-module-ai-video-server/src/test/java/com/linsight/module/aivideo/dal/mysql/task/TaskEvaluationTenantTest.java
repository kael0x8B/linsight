package com.linsight.module.aivideo.dal.mysql.task;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import com.baomidou.mybatisplus.extension.plugins.inner.TenantLineInnerInterceptor;
import com.linsight.framework.tenant.config.TenantProperties;
import com.linsight.framework.tenant.core.context.TenantContextHolder;
import com.linsight.framework.tenant.core.db.TenantDatabaseInterceptor;
import com.linsight.module.aivideo.controller.admin.task.TaskEvaluationController;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskEvaluationCreateReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskEvaluationPageReqVO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskEvaluationDO;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.prepost.PreAuthorize;

import static org.assertj.core.api.Assertions.*;

class TaskEvaluationTenantTest {
    @Test void realTenantPluginScopesGetPageAndIdempotencyQueries() {
        TableInfoHelper.initTableInfo(new MapperBuilderAssistant(new MybatisConfiguration(), "evaluation-test"), TaskEvaluationDO.class);
        var handler = new TenantDatabaseInterceptor(new TenantProperties());
        var interceptor = new TenantLineInnerInterceptor(handler);
        try {
            for (long tenant : new long[]{11, 22}) {
                TenantContextHolder.setTenantId(tenant);
                assertThat(handler.ignoreTable("ai_task_evaluation")).isFalse();
                for (String where : new String[]{"id = 42", "task_id = 1 ORDER BY id DESC LIMIT 20",
                        "task_id = 1 AND request_id = 'evaluation-request-0001'"}) {
                    assertThat(interceptor.parserSingle("SELECT * FROM ai_task_evaluation WHERE " + where, null))
                            .contains("tenant_id = " + tenant);
                }
                assertThat(interceptor.parserSingle("INSERT INTO ai_task_evaluation (task_id) VALUES (1)", null))
                        .contains("tenant_id").contains("1, " + tenant);
            }
        } finally { TenantContextHolder.clear(); }
    }

    @Test void endpointPermissionsMatchExistingTaskOwnership() throws Exception {
        var controller = TaskEvaluationController.class;
        assertThat(controller.getMethod("create", TaskEvaluationCreateReqVO.class).getAnnotation(PreAuthorize.class).value())
                .contains("ai-video:task:update");
        assertThat(controller.getMethod("get", Long.class).getAnnotation(PreAuthorize.class).value())
                .contains("ai-video:task:query");
        assertThat(controller.getMethod("page", TaskEvaluationPageReqVO.class).getAnnotation(PreAuthorize.class).value())
                .contains("ai-video:task:query");
    }
}
