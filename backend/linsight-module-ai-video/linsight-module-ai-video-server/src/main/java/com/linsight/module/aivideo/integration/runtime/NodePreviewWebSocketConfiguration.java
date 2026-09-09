package com.linsight.module.aivideo.integration.runtime;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration(proxyBeanMethods = false)
@EnableWebSocket
public class NodePreviewWebSocketConfiguration implements WebSocketConfigurer {

    public static final String TUNNEL_PATH = "/node-api/ai-video/preview/tunnel";

    private final NodePreviewTunnelHandler tunnelHandler;

    public NodePreviewWebSocketConfiguration(NodePreviewTunnelHandler tunnelHandler) {
        this.tunnelHandler = tunnelHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(tunnelHandler, TUNNEL_PATH)
                .addInterceptors(new NodePreviewHandshakeInterceptor())
                .setAllowedOriginPatterns("*");
    }
}
