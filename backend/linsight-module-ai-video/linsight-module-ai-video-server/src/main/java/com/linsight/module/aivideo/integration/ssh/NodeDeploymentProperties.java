package com.linsight.module.aivideo.integration.ssh;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.nio.file.Files;
import java.nio.file.Path;

@Data
@Component
@ConfigurationProperties(prefix = "linsight.ai-video.node-deployment")
public class NodeDeploymentProperties {
    private boolean enabled = true;
    private String runtimeSourceDir = "auto";

    public Path resolveRuntimeSource() {
        return resolveRuntimeSource(Path.of("").toAbsolutePath());
    }

    Path resolveRuntimeSource(Path workingDirectory) {
        if (runtimeSourceDir != null && !runtimeSourceDir.isBlank() && !"auto".equals(runtimeSourceDir)) {
            Path configured = workingDirectory.resolve(runtimeSourceDir).toAbsolutePath().normalize();
            if (isRuntimeSource(configured)) return configured;
            throw new IllegalStateException("控制面未找到 Runtime 源目录：" + configured);
        }
        // Maven, IDE and repository scripts start the server from different directories.
        for (Path root = workingDirectory.toAbsolutePath().normalize(); root != null; root = root.getParent()) {
            Path candidate = root.resolve("runtime");
            if (Files.isRegularFile(root.resolve("backend/pom.xml")) && isRuntimeSource(candidate)) return candidate;
        }
        throw new IllegalStateException("控制面未找到 Runtime 源目录，请设置 LINSIGHT_NODE_DEPLOYMENT_RUNTIME_SOURCE 为 Runtime 绝对路径");
    }

    private static boolean isRuntimeSource(Path path) {
        return Files.isRegularFile(path.resolve("pyproject.toml"))
                && Files.isDirectory(path.resolve("ai_runtime")) && Files.isDirectory(path.resolve("edge_agent"));
    }
    /**
     * Some ARM gateways need longer than a LAN round trip to finish SSH key exchange and
     * password authentication. Keep the timeout bounded, but do not hard-code a desktop-only
     * eight-second assumption in the transport.
     */
    private Duration connectTimeout = Duration.ofSeconds(30);
}
