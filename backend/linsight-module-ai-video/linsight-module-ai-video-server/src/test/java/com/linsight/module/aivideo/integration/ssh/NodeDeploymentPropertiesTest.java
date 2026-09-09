package com.linsight.module.aivideo.integration.ssh;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class NodeDeploymentPropertiesTest {
    @TempDir Path root;

    private Path source(Path path) throws Exception {
        Files.createDirectories(path.resolve("ai_runtime"));
        Files.createDirectories(path.resolve("edge_agent"));
        Files.writeString(path.resolve("pyproject.toml"), "[project]");
        return path;
    }

    @Test void defaultFindsSameSourceFromRepositoryMavenAndIdeDirectories() throws Exception {
        Files.createDirectories(root.resolve("backend/linsight-server"));
        Files.writeString(root.resolve("backend/pom.xml"), "<project/>");
        Path expected = source(root.resolve("runtime"));
        var properties = new NodeDeploymentProperties();
        for (String directory : new String[]{"", "backend", "backend/linsight-server"}) {
            assertEquals(expected, properties.resolveRuntimeSource(root.resolve(directory)));
        }
    }

    @Test void explicitSourceIsHonoredAndInvalidOverrideNeverFallsBack() throws Exception {
        Path expected = source(root.resolve("custom"));
        var properties = new NodeDeploymentProperties();
        properties.setRuntimeSourceDir(expected.toString());
        assertEquals(expected, properties.resolveRuntimeSource(root));
        properties.setRuntimeSourceDir("custom");
        assertEquals(expected, properties.resolveRuntimeSource(root));
        properties.setRuntimeSourceDir("missing");
        assertThrows(IllegalStateException.class, () -> properties.resolveRuntimeSource(root));
    }
}
