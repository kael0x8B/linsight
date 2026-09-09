package com.linsight.module.aivideo.integration.runtime;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.http.server.ServletServerHttpRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

import java.util.Map;

import static com.linsight.framework.web.core.util.WebFrameworkUtils.getTenantId;

/** Captures the node identity already authenticated by {@code NodeAuthenticationFilter}. */
final class NodePreviewHandshakeInterceptor implements HandshakeInterceptor {

    static final String ATTRIBUTE_NODE_ID = "aiVideoNodeId";
    static final String ATTRIBUTE_TENANT_ID = "aiVideoTenantId";

    @Override
    public boolean beforeHandshake(ServerHttpRequest request, ServerHttpResponse response,
                                   WebSocketHandler wsHandler, Map<String, Object> attributes) {
        if (!(request instanceof ServletServerHttpRequest servletRequest)) {
            return false;
        }
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        HttpServletRequest httpRequest = servletRequest.getServletRequest();
        if (authentication == null || !(authentication.getPrincipal() instanceof Long nodeId)) {
            return false;
        }
        Long tenantId = getTenantId(httpRequest);
        if (tenantId == null) {
            return false;
        }
        attributes.put(ATTRIBUTE_NODE_ID, nodeId);
        attributes.put(ATTRIBUTE_TENANT_ID, tenantId);
        return true;
    }

    @Override
    public void afterHandshake(ServerHttpRequest request, ServerHttpResponse response,
                               WebSocketHandler wsHandler, Exception exception) {
        // no-op
    }
}
