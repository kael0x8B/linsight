package com.baomidou.dynamic.datasource.processor;

import org.aopalliance.intercept.MethodInvocation;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.expression.EvaluationException;

import java.lang.reflect.AccessibleObject;
import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
class DsSpelExpressionProcessorSecurityTest {

    private DsSpelExpressionProcessor processor;
    private MethodInvocation invocation;

    @BeforeEach
    void setUp() throws Exception {
        processor = new DsSpelExpressionProcessor();
        Method method = SampleService.class.getMethod("getByTenant", String.class);
        invocation = new MethodInvocation() {
            @Override
            public Method getMethod() {
                return method;
            }

            @Override
            public Object[] getArguments() {
                return new Object[]{"tenant1"};
            }

            @Override
            public Object proceed() {
                throw new UnsupportedOperationException("not required by this test");
            }

            @Override
            public Object getThis() {
                return new SampleService();
            }

            @Override
            public AccessibleObject getStaticPart() {
                return method;
            }
        };
    }

    @Test
    void keepsParameterLookupButRejectsTypeAndConstructorAccess() {
        assertEquals("tenant1", processor.doDetermineDatasource(invocation, "#p0"));
        assertThrows(EvaluationException.class, () -> processor.doDetermineDatasource(
                invocation, "T(java.lang.Runtime).getRuntime().exec('id')"));
        assertThrows(EvaluationException.class, () -> processor.doDetermineDatasource(
                invocation, "new java.lang.ProcessBuilder('id').start()"));
    }

    static class SampleService {
        public String getByTenant(String tenant) {
            return tenant;
        }
    }
}
