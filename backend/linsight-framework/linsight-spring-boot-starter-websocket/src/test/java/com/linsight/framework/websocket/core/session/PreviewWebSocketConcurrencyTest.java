package com.linsight.framework.websocket.core.session;

import com.linsight.framework.websocket.core.handler.JsonWebSocketMessageHandler;
import com.linsight.framework.websocket.core.session.WebSocketSessionHandlerDecorator;
import com.linsight.framework.websocket.core.session.WebSocketSessionManager;
import org.junit.jupiter.api.Test;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketMessage;
import org.springframework.web.socket.WebSocketSession;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class PreviewWebSocketConcurrencyTest {
    @Test
    void heartbeatAndLargePreviewPushesShareOneSerializationLock() throws Exception {
        var raw = mock(WebSocketSession.class);
        when(raw.getId()).thenReturn("preview-session");
        when(raw.isOpen()).thenReturn(true);
        var manager = mock(WebSocketSessionManager.class);
        var wrapped = new AtomicReference<WebSocketSession>();
        doAnswer(call -> { wrapped.set(call.getArgument(0)); return null; })
                .when(manager).addSession(any());
        when(manager.getSession("preview-session")).thenAnswer(call -> wrapped.get());
        var decorator = new WebSocketSessionHandlerDecorator(new JsonWebSocketMessageHandler(List.of()), manager);
        decorator.afterConnectionEstablished(raw);
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        var writing = new AtomicBoolean(false);
        var sent = new CopyOnWriteArrayList<String>();
        doAnswer(call -> {
            assertTrue(writing.compareAndSet(false, true), "Concurrent raw socket write");
            try {
                var message = (WebSocketMessage<?>) call.getArgument(0);
                String payload = message.getPayload().toString();
                if (sent.isEmpty()) { entered.countDown(); assertTrue(release.await(2, TimeUnit.SECONDS)); }
                sent.add(payload);
            } finally { writing.set(false); }
            return null;
        }).when(raw).sendMessage(any());
        var executor = Executors.newSingleThreadExecutor();
        try {
            var first = executor.submit(() -> {
                wrapped.get().sendMessage(new TextMessage("a".repeat(150_000))); return null;
            });
            assertTrue(entered.await(2, TimeUnit.SECONDS));
            decorator.handleMessage(raw, new TextMessage("ping"));
            wrapped.get().sendMessage(new TextMessage("b".repeat(150_000)));
            release.countDown(); first.get(2, TimeUnit.SECONDS);
            assertEquals(List.of(150_000, 4, 150_000), sent.stream().map(String::length).toList());
            assertEquals("pong", sent.get(1));
            verify(raw, never()).close(any());
        } finally { release.countDown(); executor.shutdownNow(); }
    }

    @Test
    void lateHeartbeatDoesNotWriteToAnUnmanagedSession() throws Exception {
        var raw = mock(WebSocketSession.class);
        when(raw.getId()).thenReturn("closed-session");
        var decorator = new WebSocketSessionHandlerDecorator(new JsonWebSocketMessageHandler(List.of()),
                mock(WebSocketSessionManager.class));
        decorator.handleMessage(raw, new TextMessage("ping"));
        verify(raw, never()).sendMessage(any());
    }
}
