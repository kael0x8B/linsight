package com.linsight.module.aivideo.framework.security;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration(proxyBeanMethods = false)
public class NodeSecurityConfiguration {

    /**
     * NodeAuthenticationFilter 只属于节点 SecurityFilterChain，禁止 Servlet 容器再次全局注册。
     */
    @Bean
    public FilterRegistrationBean<NodeAuthenticationFilter> nodeAuthenticationFilterRegistration(
            NodeAuthenticationFilter nodeAuthenticationFilter) {
        FilterRegistrationBean<NodeAuthenticationFilter> registration =
                new FilterRegistrationBean<>(nodeAuthenticationFilter);
        registration.setEnabled(false);
        return registration;
    }

    @Bean("aiVideoNodeSecurityFilterChain")
    @Order(1)
    public SecurityFilterChain aiVideoNodeSecurityFilterChain(
            HttpSecurity httpSecurity,
            NodeAuthenticationFilter nodeAuthenticationFilter,
            @Qualifier("authenticationEntryPoint") AuthenticationEntryPoint authenticationEntryPoint,
            @Qualifier("accessDeniedHandler") AccessDeniedHandler accessDeniedHandler) throws Exception {
        return httpSecurity
                // Node API 使用固定前缀，不依赖 MVC HandlerMapping 推导匹配范围。
                .securityMatcher(new AntPathRequestMatcher("/node-api/ai-video/**"))
                .cors(Customizer.withDefaults())
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(c -> c.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .exceptionHandling(c -> c.authenticationEntryPoint(authenticationEntryPoint)
                        .accessDeniedHandler(accessDeniedHandler))
                .authorizeHttpRequests(c -> c
                        .requestMatchers(new AntPathRequestMatcher("/node-api/ai-video/node/ping", "GET")).permitAll()
                        .requestMatchers(new AntPathRequestMatcher(
                                "/node-api/ai-video/node/register", "POST")).permitAll()
                        .anyRequest().authenticated())
                .addFilterBefore(nodeAuthenticationFilter, UsernamePasswordAuthenticationFilter.class)
                .build();
    }

}
