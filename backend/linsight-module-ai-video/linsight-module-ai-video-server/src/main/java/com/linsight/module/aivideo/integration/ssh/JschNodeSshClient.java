package com.linsight.module.aivideo.integration.ssh;

import com.jcraft.jsch.ChannelExec;
import com.jcraft.jsch.ChannelSftp;
import com.jcraft.jsch.HostKey;
import com.jcraft.jsch.JSch;
import com.jcraft.jsch.Session;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentConnectionReqVO;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.function.Consumer;

@Component
@Slf4j
public class JschNodeSshClient implements NodeSshClient {
    private static final int COMMAND_TIMEOUT_MILLIS = 15 * 60_000;
    private static final int MAX_OUTPUT_BYTES = 1024 * 1024;

    @Resource private NodeDeploymentProperties properties;

    @Override
    public Connection connect(NodeDeploymentConnectionReqVO request, String trustedHostKey) throws Exception {
        JSch jsch = new JSch();
        if (trustedHostKey != null && !trustedHostKey.isBlank()) {
            String host = request.getPort() == 22 ? request.getHost()
                    : "[" + request.getHost() + "]:" + request.getPort();
            String knownHosts = host + " " + trustedHostKey + System.lineSeparator();
            jsch.setKnownHosts(new ByteArrayInputStream(knownHosts.getBytes(StandardCharsets.UTF_8)));
        }
        Session session = jsch.getSession(request.getUsername(), request.getHost(), request.getPort());
        int connectTimeoutMillis = Math.toIntExact(properties.getConnectTimeout().toMillis());
        // The control plane may use JVM-wide HTTP/SOCKS proxy properties for outbound APIs.
        // Initial provisioning targets an explicitly supplied LAN host and must never tunnel SSH
        // credentials through that ambient proxy configuration.
        session.setSocketFactory(new DirectSocketFactory(connectTimeoutMillis));
        session.setPassword(request.getPassword());
        session.setConfig("PreferredAuthentications", "password,keyboard-interactive");
        session.setConfig("StrictHostKeyChecking", trustedHostKey == null ? "no" : "yes");
        session.setServerAliveInterval((int) Duration.ofSeconds(15).toMillis());
        session.connect(connectTimeoutMillis);
        return new JschConnection(jsch, session, connectTimeoutMillis);
    }

    static final class DirectSocketFactory implements com.jcraft.jsch.SocketFactory {
        private final int connectTimeoutMillis;

        DirectSocketFactory(int connectTimeoutMillis) {
            this.connectTimeoutMillis = connectTimeoutMillis;
        }

        @Override
        public Socket createSocket(String host, int port) throws IOException {
            Socket socket = new Socket(Proxy.NO_PROXY);
            socket.connect(new InetSocketAddress(host, port), connectTimeoutMillis);
            return socket;
        }

        @Override
        public InputStream getInputStream(Socket socket) throws IOException {
            return socket.getInputStream();
        }

        @Override
        public OutputStream getOutputStream(Socket socket) throws IOException {
            return socket.getOutputStream();
        }
    }

    static final class JschConnection implements Connection {
        private final JSch jsch;
        private final Session session;
        private final int connectTimeoutMillis;

        private JschConnection(JSch jsch, Session session, int connectTimeoutMillis) {
            this.jsch = jsch;
            this.session = session;
            this.connectTimeoutMillis = connectTimeoutMillis;
        }

        @Override
        public String execute(String command, String stdin) throws Exception {
            return execute(command, stdin, null);
        }

        @Override
        public String execute(String command, String stdin, Consumer<String> outputConsumer) throws Exception {
            ChannelExec channel = (ChannelExec) session.openChannel("exec");
            channel.setCommand(command);
            channel.setPty(false);
            if (stdin != null) {
                channel.setInputStream(new ByteArrayInputStream(stdin.getBytes(StandardCharsets.UTF_8)));
            }
            InputStream stdout = channel.getInputStream();
            InputStream stderr = channel.getExtInputStream();
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            channel.connect(connectTimeoutMillis);
            try {
            long deadline = System.currentTimeMillis() + COMMAND_TIMEOUT_MILLIS;
            while (!channel.isClosed() && System.currentTimeMillis() < deadline) {
                drain(stdout, stderr, output, outputConsumer);
                Thread.sleep(100);
            }
            drain(stdout, stderr, output, outputConsumer);
            if (!channel.isClosed()) {
                channel.disconnect();
                throw new IllegalStateException("远程命令执行超时");
            }
            int exitStatus = channel.getExitStatus();
            channel.disconnect();
            String result = output.toString(StandardCharsets.UTF_8);
            if (exitStatus != 0) {
                throw new IllegalStateException(failureSummary(result, exitStatus));
            }
            return result;
            } finally {
                channel.disconnect();
            }
        }

        static void drain(InputStream stdout, InputStream stderr,
                                  ByteArrayOutputStream output, Consumer<String> outputConsumer)
                throws IOException {
            ByteArrayOutputStream chunk = new ByteArrayOutputStream();
            drainStream(stdout, output, chunk);
            drainStream(stderr, output, chunk);
            if (output.size() > MAX_OUTPUT_BYTES) {
                byte[] tail = output.toByteArray();
                output.reset();
                output.write(tail, tail.length - MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES);
            }
            if (outputConsumer != null && chunk.size() > 0) {
                try {
                    outputConsumer.accept(chunk.toString(StandardCharsets.UTF_8));
                } catch (RuntimeException error) {
                    log.warn("Unable to persist streamed SSH output", error);
                    throw new IllegalStateException("SSH 日志持久化失败，部署已中止", error);
                }
            }
        }

        private static void drainStream(InputStream input, ByteArrayOutputStream output,
                                        ByteArrayOutputStream chunk) throws IOException {
            byte[] buffer = new byte[8192];
            while (input.available() > 0) {
                int read = input.read(buffer, 0, Math.min(buffer.length, input.available()));
                if (read <= 0) {
                    return;
                }
                output.write(buffer, 0, read);
                chunk.write(buffer, 0, read);
            }
        }

        @Override
        public void upload(byte[] content, String remotePath) throws Exception {
            ChannelSftp channel = (ChannelSftp) session.openChannel("sftp");
            channel.connect(connectTimeoutMillis);
            try (ByteArrayInputStream input = new ByteArrayInputStream(content)) {
                channel.put(input, remotePath, ChannelSftp.OVERWRITE);
            } finally {
                channel.disconnect();
            }
        }

        @Override public String hostKey() { return session.getHostKey().getKey(); }
        @Override public String hostKeyType() { return session.getHostKey().getType(); }
        @Override public String hostKeyFingerprint() {
            HostKey key = session.getHostKey();
            return key.getFingerPrint(jsch);
        }
        @Override public void close() { session.disconnect(); }

        static String failureSummary(String value, int exitStatus) {
            var lines = (value == null ? "" : value).lines().map(String::trim)
                    .filter(line -> !line.isBlank() && !line.startsWith("LINSIGHT_PROGRESS="))
                    .toList();
            String summary = lines.stream().filter(line -> line.startsWith("LINSIGHT_ERROR="))
                    .reduce((first, last) -> last).map(line -> line.substring("LINSIGHT_ERROR=".length()))
                    .orElseGet(() -> String.join(" ", lines.subList(Math.max(0, lines.size() - 5), lines.size())));
            if (summary.isBlank()) summary = "远程命令失败（退出码 " + exitStatus + "）";
            summary = com.linsight.module.aivideo.framework.security.SensitiveTextRedactor.redactText(summary);
            return summary.length() > 500 ? summary.substring(0, 500) : summary;
        }
    }
}
