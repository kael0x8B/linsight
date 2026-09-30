package com.linsight.module.aivideo.service.node;

import com.linsight.framework.common.util.json.JsonUtils;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class NodeDeploymentWheelhouseTest {
    @TempDir Path source;

    private Path prepare(String name) throws Exception {
        Files.writeString(source.resolve("pyproject.toml"), "[project]\nname='test'\n");
        Path target = NodeDeploymentWheelhouse.directory(source, "aarch64", "3.12.3");
        Files.createDirectories(target);
        Files.writeString(target.resolve("safe-1.0-py3-none-any.whl"), "wheel-content");
        Files.writeString(target.resolve("manifest.json"), JsonUtils.toJsonString(Map.of(
                "schemaVersion", 1, "architecture", "aarch64", "pythonVersion", "3.12",
                "pyprojectSha256", target.getParent().getFileName().toString(),
                "files", Map.of(name, NodeDeploymentRunner.sha256("wheel-content".getBytes())))));
        return target;
    }

    @Test void requiresMatchingTargetAndDependencyManifest() throws Exception {
        prepare("safe-1.0-py3-none-any.whl");
        assertEquals(2, NodeDeploymentWheelhouse.verifiedFiles(source, "arm64", "3.12.3").size());
        assertTrue(NodeDeploymentWheelhouse.verifiedFiles(source, "x86_64", "3.12.3").isEmpty());
        assertTrue(NodeDeploymentWheelhouse.verifiedFiles(source, "aarch64", "3.13.1").isEmpty());
        Files.writeString(source.resolve("pyproject.toml"), "[project]\nname='changed'\n");
        assertTrue(NodeDeploymentWheelhouse.verifiedFiles(source, "aarch64", "3.12.3").isEmpty());
    }

    @Test void rejectsCorruptionInsteadOfFallingBackToNetwork() throws Exception {
        var target = prepare("safe-1.0-py3-none-any.whl");
        Files.writeString(target.resolve("safe-1.0-py3-none-any.whl"), "corrupt");
        assertThrows(IllegalStateException.class, () -> NodeDeploymentWheelhouse.verifiedFiles(source, "aarch64", "3.12"));
    }

    @Test void rejectsTraversalInManifest() throws Exception {
        prepare("../private.whl");
        assertThrows(IllegalStateException.class, () -> NodeDeploymentWheelhouse.verifiedFiles(source, "aarch64", "3.12"));
    }

    @Test void bundlesOnlyVerifiedTargetWheelsAndVersionTracksTheirContent() throws Exception {
        prepare("safe-1.0-py3-none-any.whl");
        Files.createDirectories(source.resolve("ai_runtime"));
        Files.createDirectories(source.resolve("edge_agent"));
        writeGatewayConsoleBundle();
        var properties = new com.linsight.module.aivideo.integration.ssh.NodeDeploymentProperties();
        properties.setRuntimeSourceDir(source.toString());
        var runner = new NodeDeploymentRunner();
        org.springframework.test.util.ReflectionTestUtils.setField(runner, "properties", properties);
        byte[] bundled = org.springframework.test.util.ReflectionTestUtils.invokeMethod(runner, "buildRuntimePackage", "aarch64", "3.12.3");
        byte[] plain = org.springframework.test.util.ReflectionTestUtils.invokeMethod(runner, "buildRuntimePackage", "x86_64", "3.12.3");
        assertNotEquals(NodeDeploymentRunner.sha256(bundled), NodeDeploymentRunner.sha256(plain));
        var names = new java.util.ArrayList<String>();
        try (var zip = new java.util.zip.ZipInputStream(new java.io.ByteArrayInputStream(bundled))) {
            java.util.zip.ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) names.add(entry.getName());
        }
        assertTrue(names.contains("deployment-wheels/manifest.json"));
        assertTrue(names.contains("deployment-wheels/safe-1.0-py3-none-any.whl"));
    }

    private void writeGatewayConsoleBundle() throws Exception {
        Path directory = source.resolve("gateway-console");
        Files.createDirectories(directory);
        byte[] artifact = "gateway console artifact".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        String digest = NodeDeploymentRunner.sha256(artifact);
        String fileName = "gateway-console-" + digest.substring(0, 12) + ".tar.gz";
        Files.write(directory.resolve(fileName), artifact);
        Files.writeString(directory.resolve("manifest.json"), """
                {"schemaVersion":"1.0","artifactType":"linsightGatewayConsole",
                 "artifact":{"fileName":"%s","sha256":"%s"}}
                """.formatted(fileName, digest));
    }
}
