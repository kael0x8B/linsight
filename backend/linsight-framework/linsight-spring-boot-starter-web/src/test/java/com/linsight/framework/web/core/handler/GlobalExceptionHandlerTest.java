package com.linsight.framework.web.core.handler;

import com.linsight.framework.common.biz.infra.logger.ApiErrorLogCommonApi;
import com.linsight.framework.common.pojo.CommonResult;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.util.ReflectionTestUtils;

import java.sql.SQLSyntaxErrorException;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class GlobalExceptionHandlerTest {
    private final ApiErrorLogCommonApi errorLog = mock(ApiErrorLogCommonApi.class);
    private final GlobalExceptionHandler handler = new GlobalExceptionHandler("linsight", errorLog);

    @Test void missingApplicationReleaseTableExplainsMigrationWithoutMisidentifyingModule() {
        var request = new MockHttpServletRequest("GET", "/admin-api/ai-video/node/application-release/page");
        var failure = new RuntimeException("Mapper failed", new SQLSyntaxErrorException(
                "Table 'linsight.ai_node_application_release' doesn't exist"));
        var result = handler.defaultExceptionHandler(request, failure);
        assertEquals(500, result.getCode());
        assertTrue(result.getMsg().contains("数据库迁移"));
        assertFalse(result.getMsg().contains("大模型"));
        assertFalse(result.getMsg().contains("未启用"));
        assertFalse(result.getMsg().contains("ai_node_application_release"));
        verifyNoInteractions(errorLog);
    }

    @Test void sharedAiPrefixDoesNotClaimSpecificModuleIsDisabled() {
        for (String table : new String[]{"ai_camera", "ai_model", "ai_chat_message", "AI_NODE_UPGRADE"}) {
            CommonResult<?> result = ReflectionTestUtils.invokeMethod(handler, "handleTableNotExists",
                    new SQLSyntaxErrorException("Table 'linsight." + table + "' doesn't exist"));
            assertNotNull(result);
            assertTrue(result.getMsg().contains("数据库迁移"));
            assertEquals(500, result.getCode());
        }
    }

    @Test void databaseNamesAndNonTableErrorsDoNotTriggerAiMigrationHint() {
        for (String message : new String[]{
                "Table 'ai_database.unrelated_table' doesn't exist",
                "FUNCTION ai_function doesn't exist",
                "Unknown column 'ai_node_application_release' in 'field list'"}) {
            assertNull(ReflectionTestUtils.invokeMethod(handler, "handleTableNotExists",
                    new SQLSyntaxErrorException(message)));
        }
    }

    @Test void existingUnrelatedOptionalModuleHintsRemainAvailable() {
        CommonResult<?> result = ReflectionTestUtils.invokeMethod(handler, "handleTableNotExists",
                new SQLSyntaxErrorException("Table 'linsight.bpm_process_instance' doesn't exist"));
        assertNotNull(result);
        assertEquals(501, result.getCode());
        assertTrue(result.getMsg().contains("linsight-module-bpm"));
    }
}
