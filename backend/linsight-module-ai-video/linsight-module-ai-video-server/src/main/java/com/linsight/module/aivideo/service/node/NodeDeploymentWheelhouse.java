package com.linsight.module.aivideo.service.node;

import com.linsight.framework.common.util.json.JsonUtils;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** Immutable, target-specific dependency artifacts prepared on the build host. */
final class NodeDeploymentWheelhouse {
    private NodeDeploymentWheelhouse() {}

    static Path directory(Path source, String architecture, String python) throws Exception {
        String arch = switch (architecture == null ? "" : architecture) {
            case "aarch64", "arm64" -> "aarch64";
            case "x86_64", "amd64" -> "x86_64";
            default -> null;
        };
        if (arch == null || python == null || !python.matches("3\\.(12|13)(?:\\..*)?")) return null;
        if (!Files.isRegularFile(source.resolve("pyproject.toml"))) return null;
        String minor = python.startsWith("3.12") ? "3.12" : "3.13";
        String digest = NodeDeploymentRunner.sha256(Files.readAllBytes(source.resolve("pyproject.toml")));
        return source.resolve("deployment-wheels").resolve(digest).resolve(arch + "-cp" + minor.replace(".", ""));
    }

    static List<Path> verifiedFiles(Path source, String architecture, String python) throws Exception {
        Path directory = directory(source, architecture, python);
        if (directory == null || !Files.exists(directory)) return List.of();
        Path manifest = directory.resolve("manifest.json");
        Map<String, Object> metadata = JsonUtils.parseMap(Files.readString(manifest));
        if (metadata == null || !Integer.valueOf(1).equals(metadata.get("schemaVersion"))
                || !directory.getParent().getFileName().toString().equals(metadata.get("pyprojectSha256"))
                || !directory.getFileName().toString().equals(metadata.get("architecture") + "-cp"
                    + String.valueOf(metadata.get("pythonVersion")).replace(".", ""))
                || !(metadata.get("files") instanceof Map<?, ?> files) || files.isEmpty()) {
            throw new IllegalStateException("离线依赖清单无效，请重新准备目标架构的部署依赖");
        }
        List<Path> result = new ArrayList<>();
        result.add(manifest);
        for (var entry : files.entrySet()) {
            String name = String.valueOf(entry.getKey());
            if (!name.matches("[A-Za-z0-9_.+\\-]+\\.whl") || !(entry.getValue() instanceof String hash)
                    || !hash.matches("[0-9a-f]{64}")) throw new IllegalStateException("离线依赖清单路径或摘要无效");
            Path wheel = directory.resolve(name);
            if (Files.isSymbolicLink(wheel) || !Files.isRegularFile(wheel)
                    || !hash.equals(NodeDeploymentRunner.sha256(Files.readAllBytes(wheel)))) {
                throw new IllegalStateException("离线依赖校验失败：" + name);
            }
            result.add(wheel);
        }
        return result.stream().sorted().toList();
    }
}
