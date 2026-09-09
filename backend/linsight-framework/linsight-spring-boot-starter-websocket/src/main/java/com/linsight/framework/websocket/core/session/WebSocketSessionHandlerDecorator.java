package com.linsight.framework.websocket.core.session;

import lombok.extern.slf4j.Slf4j;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.WebSocketMessage;
import org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator;
import org.springframework.web.socket.handler.WebSocketHandlerDecorator;

/**
 * {@link WebSocketHandler} 的装饰类，实现了以下功能：
 *
 * 1. {@link WebSocketSession} 连接或关闭时，使用 {@link #sessionManager} 进行管理
 * 2. 封装 {@link WebSocketSession} 支持并发操作
 *
 * @author 芋道源码
 */
@Slf4j
public class WebSocketSessionHandlerDecorator extends WebSocketHandlerDecorator {

    /**
     * 发送时间的限制，单位：毫秒
     */
    private static final Integer SEND_TIME_LIMIT = 1000 * 5;
    /**
     * 发送消息缓冲上线，单位：bytes
     */
    // A preview result may contain a 256 KiB JPEG encoded as Base64. Keep the
    // queue bounded while allowing it to coexist with heartbeat/notification writes.
    private static final Integer BUFFER_SIZE_LIMIT = 1024 * 1024;

    private final WebSocketSessionManager sessionManager;

    public WebSocketSessionHandlerDecorator(WebSocketHandler delegate,
                                            WebSocketSessionManager sessionManager) {
        super(delegate);
        this.sessionManager = sessionManager;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        // 实现 session 支持并发，可参考 https://blog.csdn.net/abu935009066/article/details/131218149
        session = new ConcurrentWebSocketSessionDecorator(session, SEND_TIME_LIMIT, BUFFER_SIZE_LIMIT);
        // 添加到 WebSocketSessionManager 中
        sessionManager.addSession(session);
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus closeStatus) {
        sessionManager.removeSession(session);
    }

    @Override
    public void handleMessage(WebSocketSession session, WebSocketMessage<?> message) {
        WebSocketSession managed = sessionManager.getSession(session.getId());
        if (managed == null) return; // A late heartbeat after session removal.
        try {
            // Pong and listener replies must use the same serialization lock as
            // server pushes; passing the raw session races with preview frames.
            super.handleMessage(managed, message);
        } catch (Exception error) {
            // The framework's raw session string contains the authenticated URI.
            log.warn("[handleMessage][session({}) bytes({}) errorType({})]",
                    session.getId(), message.getPayloadLength(), error.getClass().getSimpleName());
            try {
                managed.close(CloseStatus.SERVER_ERROR);
            } catch (Exception closeError) {
                log.warn("[closeSession][session({}) errorType({})]",
                        session.getId(), closeError.getClass().getSimpleName());
            }
        }
    }

}
