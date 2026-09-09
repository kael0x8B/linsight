package com.linsight.module.aivideo.integration.ssh;

import org.junit.jupiter.api.Test;

import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JschNodeSshClientTest {

    @Test
    void failureSummaryUsesDiagnosticNotTheFirstProgressLine() {
        String output = "LINSIGHT_PROGRESS=58 检查依赖\n" + "long install output\n".repeat(100)
                + "LINSIGHT_ERROR=APT 依赖冲突：python3.12-venv\n[RECOVERY] 原服务未切换\n";
        assertEquals("APT 依赖冲突：python3.12-venv", JschNodeSshClient.JschConnection.failureSummary(output, 1));
        assertEquals("远程命令失败（退出码 42）", JschNodeSshClient.JschConnection.failureSummary("", 42));
        assertEquals("ERROR connection token=***", JschNodeSshClient.JschConnection.failureSummary("ERROR connection token=private", 1));
    }

    @Test
    void deploymentOutputIsPublishedBeforeCompletionAndLargeOutputKeepsBoundedTail() throws Exception {
        var output = new java.io.ByteArrayOutputStream();
        var streamed = new java.util.ArrayList<String>();
        JschNodeSshClient.JschConnection.drain(
                new java.io.ByteArrayInputStream("first stage\n".getBytes()),
                java.io.InputStream.nullInputStream(), output, streamed::add);
        assertEquals(java.util.List.of("first stage\n"), streamed);
        String large = "x".repeat(1024 * 1024) + "last stage\n";
        JschNodeSshClient.JschConnection.drain(
                new java.io.ByteArrayInputStream(large.getBytes()),
                java.io.InputStream.nullInputStream(), output, streamed::add);
        assertEquals(2, streamed.size());
        assertEquals(1024 * 1024, output.size());
        org.junit.jupiter.api.Assertions.assertTrue(output.toString().endsWith("last stage\n"));
    }

    @Test
    void directSocketFactoryMustConnectWithoutAmbientProxySelection() throws Exception {
        try (ServerSocket server = new ServerSocket(0)) {
            CompletableFuture<Void> accepted = CompletableFuture.runAsync(() -> {
                try (Socket peer = server.accept()) {
                    peer.getOutputStream().write(42);
                } catch (Exception error) {
                    throw new IllegalStateException(error);
                }
            });

            JschNodeSshClient.DirectSocketFactory factory =
                    new JschNodeSshClient.DirectSocketFactory(2_000);
            try (Socket socket = factory.createSocket("127.0.0.1", server.getLocalPort())) {
                assertEquals(42, factory.getInputStream(socket).read());
            }
            accepted.get(2, TimeUnit.SECONDS);
        }
    }
}
