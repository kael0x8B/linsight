package com.linsight.module.aivideo.framework.security;

import com.linsight.module.aivideo.service.node.NodeService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class NodeAuthenticationFilterTest {

    private final NodeService nodeService = mock(NodeService.class);
    private final NodeAuthenticationFilter filter = new NodeAuthenticationFilter(nodeService);

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldSkipNonNodeApi() throws Exception {
        MockHttpServletRequest request = request("/admin-api/system/auth/login");
        MockFilterChain chain = new MockFilterChain();

        filter.doFilter(request, new MockHttpServletResponse(), chain);

        assertSame(request, chain.getRequest());
        verifyNoInteractions(nodeService);
    }

    @Test
    void shouldSkipNodeRegistration() throws Exception {
        MockHttpServletRequest request = request("/node-api/ai-video/node/register");
        MockFilterChain chain = new MockFilterChain();

        filter.doFilter(request, new MockHttpServletResponse(), chain);

        assertSame(request, chain.getRequest());
        verifyNoInteractions(nodeService);
    }

    @Test
    void shouldRejectInvalidProtectedNodeRequest() throws Exception {
        MockHttpServletRequest request = protectedRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();
        when(nodeService.authenticateNode(2L, 1L, "invalid")).thenReturn(false);

        filter.doFilter(request, response, chain);

        assertNull(chain.getRequest());
        assertTrue(response.getContentAsString().contains("401"));
    }

    @Test
    void shouldAuthenticateValidProtectedNodeRequest() throws Exception {
        MockHttpServletRequest request = protectedRequest();
        MockFilterChain chain = new MockFilterChain();
        when(nodeService.authenticateNode(2L, 1L, "invalid")).thenReturn(true);

        filter.doFilter(request, new MockHttpServletResponse(), chain);

        assertSame(request, chain.getRequest());
        assertEquals(2L, SecurityContextHolder.getContext().getAuthentication().getPrincipal());
    }

    @Test
    void shouldDisableServletContainerRegistration() {
        FilterRegistrationBean<NodeAuthenticationFilter> registration =
                new NodeSecurityConfiguration().nodeAuthenticationFilterRegistration(filter);

        assertFalse(registration.isEnabled());
        assertSame(filter, registration.getFilter());
    }

    private static MockHttpServletRequest request(String uri) {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", uri);
        request.setRequestURI(uri);
        return request;
    }

    private static MockHttpServletRequest protectedRequest() {
        MockHttpServletRequest request = request("/node-api/ai-video/node/heartbeat");
        request.addHeader("tenant-id", "1");
        request.addHeader(NodeAuthenticationFilter.HEADER_NODE_ID, "2");
        request.addHeader(NodeAuthenticationFilter.HEADER_NODE_CREDENTIAL, "invalid");
        return request;
    }

}
