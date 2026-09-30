package com.linsight.examples.gateway;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.netty.bootstrap.Bootstrap;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.ChannelInitializer;
import io.netty.channel.ChannelOption;
import io.netty.channel.SimpleChannelInboundHandler;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioSocketChannel;
import io.netty.handler.codec.LineBasedFrameDecoder;
import io.netty.handler.codec.string.StringDecoder;
import io.netty.handler.codec.string.StringEncoder;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import io.netty.handler.timeout.ReadTimeoutHandler;
import io.netty.util.concurrent.DefaultEventExecutorGroup;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.Console;
import java.io.IOException;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.SocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/**
 * 盒子事件 TCP V3 订阅客户端。每条协议消息是一行 UTF-8 JSON，以换行符结尾。
 * 连接后依次完成 challenge → auth → authenticated → subscribe → subscribed，再接收事件和心跳。
 * 订阅只接收连接建立后的实时事件，断线期间的事件不会补发。图片通过事件中的限时 HTTP URL 下载。
 */
public final class GatewayEventClient {
    // 事件帧仅包含元数据和图片 URL；超限帧由 Netty 直接拒绝。
    private static final int MAX_FRAME_BYTES = 64 * 1024;
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private GatewayEventClient() {
    }

    public static void main(String[] args) throws Exception {
        // 直接运行 main 时使用的盒子配置；接入其他盒子可修改这里。
        String defaultHost = "192.168.2.14";
        int defaultPort = 48902;
        // 本地默认密钥；GATEWAY_EVENT_KEY 环境变量可覆盖，二者都为空时从终端输入。
        String subscriberKey = "XbDQ28XNydt2t50IGxItgUMx994sAMil533nTeCYPo4";

        Settings settings;
        try {
            settings = Settings.fromArguments(args, defaultHost, defaultPort, subscriberKey);
        } catch (IllegalArgumentException error) {
            // 配置错误在建立网络连接前给出用法，不向使用者显示 Java 堆栈或密钥。
            System.err.println("启动参数错误：" + error.getMessage());
            System.err.println("直接运行 main 使用代码中的默认盒子配置；也可传入盒子 IP 覆盖默认地址。");
            System.exit(2);
            return;
        }
        EventSink sink = new FileEventSink(settings.outputDirectory(), MAPPER);
        // 图片地址指向盒子本机。显式直连，避免系统代理把局域网 HTTP 请求转发出去并导致超时。
        HttpClient imageClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .proxy(new ProxySelector() {
                    @Override
                    public List<Proxy> select(URI uri) {
                        return List.of(Proxy.NO_PROXY);
                    }

                    @Override
                    public void connectFailed(URI uri, SocketAddress address, IOException error) {
                        // 直连时不会选择代理；HTTP 请求失败由调用处报告。
                    }
                })
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        AtomicBoolean finished = new AtomicBoolean();
        AtomicReference<String> terminalError = new AtomicReference<>();
        AtomicInteger received = new AtomicInteger();
        NioEventLoopGroup io = new NioEventLoopGroup(1);
        // 图片下载、校验和文件写入放到独立线程，避免占用 Netty 的网络 IO 线程。
        DefaultEventExecutorGroup processing = new DefaultEventExecutorGroup(1);
        SslContext tls = settings.tls() ? SslContextBuilder.forClient().build() : null;
        try {
            Bootstrap bootstrap = new Bootstrap().group(io).channel(NioSocketChannel.class)
                    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
                    .handler(new ChannelInitializer<SocketChannel>() {
                        @Override
                        protected void initChannel(SocketChannel channel) {
                            if (tls != null) {
                                channel.pipeline().addLast(tls.newHandler(channel.alloc(),
                                        settings.host(), settings.port()));
                            }
                            // 服务端每 30 秒发一次心跳；留出网络抖动余量，避免空闲时误判断线。
                            channel.pipeline().addLast(new ReadTimeoutHandler(75));
                            channel.pipeline().addLast(new LineBasedFrameDecoder(MAX_FRAME_BYTES, true, true));
                            channel.pipeline().addLast(new StringDecoder(StandardCharsets.UTF_8));
                            channel.pipeline().addLast(new StringEncoder(StandardCharsets.UTF_8));
                            channel.pipeline().addLast(processing,
                                    new ProtocolHandler(settings, imageClient, sink, finished,
                                            terminalError, received));
                        }
                    });
            int delaySeconds = 1;
            // 每次新建连接都会重新鉴权和订阅；短暂断线采用最多 30 秒的指数退避。
            while (!finished.get() && terminalError.get() == null && !Thread.currentThread().isInterrupted()) {
                try {
                    System.out.printf("Connecting to %s:%d (live events only)%n",
                            settings.host(), settings.port());
                    bootstrap.connect(settings.host(), settings.port()).sync().channel()
                            .closeFuture().sync();
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    break;
                } catch (Exception error) {
                    System.err.println("Connection ended: " + error.getClass().getSimpleName());
                }
                if (!finished.get() && terminalError.get() == null) {
                    Thread.sleep(delaySeconds * 1_000L);
                    delaySeconds = Math.min(delaySeconds * 2, 30);
                }
            }
            if (terminalError.get() != null) {
                throw new IllegalStateException(terminalError.get());
            }
        } finally {
            Arrays.fill(settings.key(), (byte) 0);
            processing.shutdownGracefully().sync();
            io.shutdownGracefully().sync();
        }
    }

    // 状态表示下一条预期收到的服务端消息；不允许跳过鉴权直接进入事件流。
    private enum State { CHALLENGE, AUTHENTICATED, SUBSCRIBED, STREAMING }

    private static final class ProtocolHandler extends SimpleChannelInboundHandler<String> {
        private final Settings settings;
        private final HttpClient imageClient;
        private final EventSink sink;
        private final AtomicBoolean finished;
        private final AtomicReference<String> terminalError;
        private final AtomicInteger received;
        private State state = State.CHALLENGE;
        private long lastHeartbeatLogNanos;

        private ProtocolHandler(Settings settings, HttpClient imageClient, EventSink sink,
                                AtomicBoolean finished, AtomicReference<String> terminalError,
                                AtomicInteger received) {
            this.settings = settings;
            this.imageClient = imageClient;
            this.sink = sink;
            this.finished = finished;
            this.terminalError = terminalError;
            this.received = received;
        }

        @Override
        protected void channelRead0(ChannelHandlerContext context, String line) {
            if (finished.get()) {
                context.close();
                return;
            }
            try {
                JsonNode frame = MAPPER.readTree(line);
                String type = frame.path("type").asText("");
                if ("error".equals(type)) {
                    String code = frame.path("code").asText("UNKNOWN");
                    // 服务端配置变更或暂时停用允许重连；其他协议错误需要人工修正配置。
                    if (!"DISABLED".equals(code) && !"CONFIG_CHANGED".equals(code)) {
                        terminalError.compareAndSet(null, "Gateway rejected subscription: " + code
                                + ("SNAPSHOT_UNAVAILABLE".equals(code)
                                ? ", sourceEventId=" + frame.path("sourceEventId").asText() : ""));
                    }
                    System.err.println("Gateway status: " + code);
                    context.close();
                    return;
                }
                switch (state) {
                    case CHALLENGE -> onChallenge(context, frame, type);
                    case AUTHENTICATED -> onAuthenticated(context, type);
                    case SUBSCRIBED -> onSubscribed(type);
                    case STREAMING -> onStream(context, frame, type);
                }
            } catch (Exception error) {
                // 原始帧可能含图片和识别结果，异常日志只打印类型，避免泄露业务数据。
                terminalError.compareAndSet(null, "Invalid event or storage failure: "
                        + error.getClass().getSimpleName());
                context.close();
            }
        }

        private void onChallenge(ChannelHandlerContext context, JsonNode frame, String type)
                throws Exception {
            if (!"challenge".equals(type) || !"3.0".equals(frame.path("version").asText())) {
                throw new IllegalArgumentException("Expected V3 challenge");
            }
            String nonce = frame.path("nonce").asText("");
            if (!nonce.matches("[0-9a-f]{48}")) {
                throw new IllegalArgumentException("Invalid nonce");
            }
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(settings.key(), "HmacSHA256"));
            // nonce 虽然由十六进制字符组成，但这里取字符串原文的 UTF-8 字节，不能先做十六进制解码。
            // 以订阅密钥为 HMAC 密钥；网络中只传 64 个小写十六进制字符，不传明文密钥。
            String digest = HexFormat.of().formatHex(mac.doFinal(nonce.getBytes(StandardCharsets.UTF_8)));
            ObjectNode auth = MAPPER.createObjectNode().put("type", "auth").put("hmac", digest);
            write(context, auth);
            state = State.AUTHENTICATED;
        }

        private void onAuthenticated(ChannelHandlerContext context, String type) throws Exception {
            if (!"authenticated".equals(type)) {
                throw new IllegalArgumentException("Expected authentication acknowledgement");
            }
            // 无游标，订阅确认之后只接收实时事件；空过滤列表表示订阅全部。
            ObjectNode subscription = MAPPER.createObjectNode().put("type", "subscribe");
            ArrayNode taskIds = subscription.putArray("taskIds");
            settings.taskIds().forEach(taskIds::add);
            ArrayNode eventTypes = subscription.putArray("eventTypes");
            settings.eventTypes().forEach(eventTypes::add);
            write(context, subscription);
            state = State.SUBSCRIBED;
        }

        private void onSubscribed(String type) {
            if (!"subscribed".equals(type)) {
                throw new IllegalArgumentException("Unexpected subscription acknowledgement");
            }
            // 把实际发送给盒子的过滤条件打印出来，便于区分任务名称和任务 ID。
            System.out.printf("Subscribed; taskIds=%s, eventTypes=%s; 等待新事件.%n",
                    settings.taskIds().isEmpty() ? "全部" : settings.taskIds(),
                    settings.eventTypes().isEmpty() ? "全部" : settings.eventTypes());
            state = State.STREAMING;
        }

        private void onStream(ChannelHandlerContext context, JsonNode frame, String type)
                throws Exception {
            if ("heartbeat".equals(type)) {
                // 盒子每 30 秒发一次心跳；首个心跳和之后每 30 秒打印一次，避免刷屏。
                long now = System.nanoTime();
                if (lastHeartbeatLogNanos == 0
                        || now - lastHeartbeatLogNanos >= Duration.ofSeconds(30).toNanos()) {
                    System.out.println("Heartbeat received; 连接正常，等待匹配的新事件.");
                    lastHeartbeatLogNanos = now;
                }
                return; // 心跳无需回复，也不代表有新事件。
            }
            // 直接展示收到的事件字段；限时图片 URL 的签名不写入控制台日志。
            printEventJson(frame);
            GatewayEvent event = GatewayEvent.parse(frame, MAPPER, imageClient);
            // 先下载并校验图片，再交给业务处理；失败则停机，实时流不会补发旧事件。
            sink.accept(event);
            Path directory = settings.outputDirectory().toAbsolutePath().normalize();
            System.out.printf("事件已保存：%s 和 %s%n%n",
                    directory.resolve(event.sourceEventId() + ".json"),
                    directory.resolve(event.sourceEventId() + ".jpg"));
            if (settings.maxEvents() > 0 && received.incrementAndGet() >= settings.maxEvents()) {
                finished.set(true);
                context.close();
            }
        }

        private static void printEventJson(JsonNode frame) throws IOException {
            if (!(frame instanceof ObjectNode eventFrame)) {
                throw new IllegalArgumentException("Event frame must be a JSON object");
            }
            ObjectNode printable = eventFrame.deepCopy();
            JsonNode snapshot = printable.path("data").path("snapshot");
            if (snapshot instanceof ObjectNode image && image.path("url").isTextual()) {
                String url = image.path("url").asText();
                int query = url.indexOf('?');
                if (query >= 0) {
                    image.put("url", url);
                }
            }
            System.out.println("收到事件 JSON（控制台隐藏图片 URL 签名，完整内容保存在事件 JSON 文件）：");
            System.out.println(MAPPER.writerWithDefaultPrettyPrinter().writeValueAsString(printable));
        }

        private static void write(ChannelHandlerContext context, ObjectNode frame) throws IOException {
            context.writeAndFlush(MAPPER.writeValueAsString(frame) + "\n");
        }

        @Override
        public void exceptionCaught(ChannelHandlerContext context, Throwable error) {
            System.err.println("Socket interrupted: " + error.getClass().getSimpleName());
            context.close();
        }
    }

    /** main 中的配置可直接使用；命令行地址和环境变量仍可覆盖默认连接参数。 */
    private record Settings(String host, int port, byte[] key, List<Long> taskIds,
                            List<String> eventTypes, Path outputDirectory,
                            boolean tls, int maxEvents) {
        private static Settings fromArguments(String[] args, String defaultHost, int defaultPort,
                                              String subscriberKey) {
            if (args.length > 1) {
                throw new IllegalArgumentException("只接受一个盒子地址参数，端口请设置 GATEWAY_PORT");
            }
            String host = args.length == 1 ? args[0].trim() : env("GATEWAY_HOST", defaultHost);
            if (host == null || host.isBlank()) {
                throw new IllegalArgumentException("缺少盒子地址；请检查 main 中的 defaultHost");
            }
            host = host.trim();
            int port = Integer.parseInt(env("GATEWAY_PORT", Integer.toString(defaultPort)));
            if (port < 1 || port > 65535) {
                throw new IllegalArgumentException("Invalid GATEWAY_PORT");
            }
            // 测试或部署时可用环境变量覆盖 main 中的密钥，便于轮换而无需改源码。
            String environmentKey = System.getenv("GATEWAY_EVENT_KEY");
            String configuredKey = environmentKey == null || environmentKey.isBlank()
                    ? subscriberKey : environmentKey;
            char[] characters;
            if (configuredKey == null || configuredKey.isBlank()) {
                Console console = System.console();
                if (console == null) {
                    throw new IllegalArgumentException("请在 main 的 subscriberKey 中填写密钥，或设置 GATEWAY_EVENT_KEY");
                }
                characters = console.readPassword("订阅密钥（输入不回显）：");
            } else {
                characters = configuredKey.toCharArray();
            }
            if (characters == null || characters.length == 0) {
                throw new IllegalArgumentException("Subscriber key is empty");
            }
            // 保留字节数组供 HMAC 使用，退出时在 finally 中清空；不要输出密钥或写入仓库。
            byte[] key = new String(characters).getBytes(StandardCharsets.UTF_8);
            Arrays.fill(characters, '\0');
            Path output = Path.of(env("GATEWAY_OUTPUT_DIR", "./gateway-events"));
            int maxEvents = Integer.parseInt(env("GATEWAY_MAX_EVENTS", "0"));
            if (maxEvents < 0) {
                throw new IllegalArgumentException("GATEWAY_MAX_EVENTS cannot be negative");
            }
            return new Settings(host, port, key, longList("GATEWAY_TASK_IDS"),
                    stringList("GATEWAY_EVENT_TYPES"), output,
                    Boolean.parseBoolean(env("GATEWAY_TLS", "false")), maxEvents);
        }

        private static String env(String name, String fallback) {
            String value = System.getenv(name);
            return value == null || value.isBlank() ? fallback : value.trim();
        }

        private static List<Long> longList(String name) {
            List<Long> values = new ArrayList<>();
            for (String raw : stringList(name)) {
                long value = Long.parseLong(raw);
                if (value <= 0) {
                    throw new IllegalArgumentException("Invalid " + name);
                }
                values.add(value);
            }
            return List.copyOf(values);
        }

        private static List<String> stringList(String name) {
            String raw = System.getenv(name);
            if (raw == null || raw.isBlank()) {
                return List.of();
            }
            List<String> values = new ArrayList<>();
            for (String part : raw.split(",")) {
                String value = part.trim();
                if (value.isEmpty()) {
                    throw new IllegalArgumentException("Invalid " + name);
                }
                values.add(value);
            }
            return List.copyOf(values);
        }
    }
}
