/*
 * Copyright © 2018 organization baomidou
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 */
package com.baomidou.dynamic.datasource.processor;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.context.expression.MethodBasedEvaluationContext;
import org.springframework.core.DefaultParameterNameDiscoverer;
import org.springframework.core.ParameterNameDiscoverer;
import org.springframework.expression.BeanResolver;
import org.springframework.expression.EvaluationException;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.ParserContext;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

import java.lang.reflect.Method;
import java.util.Collections;

/**
 * Security backport of upstream commit 273fced for dynamic-datasource 4.5.0.
 * Type references and constructors are disabled by default to prevent DS SpEL injection.
 */
public class DsSpelExpressionProcessor extends DsProcessor {

    private static final ParameterNameDiscoverer NAME_DISCOVERER = new DefaultParameterNameDiscoverer();
    private static final ExpressionParser PARSER = new SpelExpressionParser();

    private ParserContext parserContext = new ParserContext() {
        @Override
        public boolean isTemplate() {
            return false;
        }

        @Override
        public String getExpressionPrefix() {
            return null;
        }

        @Override
        public String getExpressionSuffix() {
            return null;
        }
    };
    private BeanResolver beanResolver;
    private boolean allowedSpelTypeAccess;

    @Override
    public boolean matches(String key) {
        return true;
    }

    @Override
    public String doDetermineDatasource(MethodInvocation invocation, String key) {
        Method method = invocation.getMethod();
        Object[] arguments = invocation.getArguments();
        ExpressionRootObject rootObject = new ExpressionRootObject(method, arguments, invocation.getThis());
        StandardEvaluationContext context =
                new MethodBasedEvaluationContext(rootObject, method, arguments, NAME_DISCOVERER);
        context.setBeanResolver(beanResolver);
        if (!allowedSpelTypeAccess) {
            context.setTypeLocator(typeName -> {
                throw new EvaluationException(
                        "Type access is not allowed in DS SpEL expressions: " + typeName);
            });
            context.setConstructorResolvers(Collections.emptyList());
        }
        Object value = PARSER.parseExpression(key, parserContext).getValue(context);
        return value == null ? null : value.toString();
    }

    public void setAllowedSpelTypeAccess(boolean allowedSpelTypeAccess) {
        this.allowedSpelTypeAccess = allowedSpelTypeAccess;
    }

    public void setParserContext(ParserContext parserContext) {
        this.parserContext = parserContext;
    }

    public void setBeanResolver(BeanResolver beanResolver) {
        this.beanResolver = beanResolver;
    }

    @Getter
    @RequiredArgsConstructor
    public static class ExpressionRootObject {
        private final Method method;
        private final Object[] args;
        private final Object target;
    }
}
