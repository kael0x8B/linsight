package com.linsight.module.aivideo.framework.security;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.util.servlet.ServletUtils;
import com.linsight.framework.web.core.util.WebFrameworkUtils;
import com.linsight.module.aivideo.service.node.NodeService;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;

import static com.linsight.framework.common.exception.enums.GlobalErrorCodeConstants.UNAUTHORIZED;

@Component
public class NodeAuthenticationFilter extends OncePerRequestFilter {

    public static final String HEADER_NODE_ID = "X-Node-Id";
    public static final String HEADER_NODE_CREDENTIAL = "X-Node-Credential";

    private final NodeService nodeService;

    public NodeAuthenticationFilter(NodeService nodeService) {
        this.nodeService = nodeService;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String requestUri = request.getRequestURI().substring(request.getContextPath().length());
        return !requestUri.startsWith("/node-api/ai-video/")
                || "/node-api/ai-video/node/register".equals(requestUri)
                || "/node-api/ai-video/node/ping".equals(requestUri);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        Long nodeId = parseLong(request.getHeader(HEADER_NODE_ID));
        Long tenantId = WebFrameworkUtils.getTenantId(request);
        String credential = request.getHeader(HEADER_NODE_CREDENTIAL);
        if (!nodeService.authenticateNode(nodeId, tenantId, credential)) {
            ServletUtils.writeJSON(response, CommonResult.error(UNAUTHORIZED));
            return;
        }
        UsernamePasswordAuthenticationToken authentication = UsernamePasswordAuthenticationToken.authenticated(
                nodeId, null, List.of(new SimpleGrantedAuthority("ROLE_AI_VIDEO_NODE")));
        SecurityContextHolder.getContext().setAuthentication(authentication);
        filterChain.doFilter(request, response);
    }

    private static Long parseLong(String value) {
        if (value == null) {
            return null;
        }
        try {
            return Long.valueOf(value);
        } catch (NumberFormatException ignored) {
            return null;
        }
    }

}
