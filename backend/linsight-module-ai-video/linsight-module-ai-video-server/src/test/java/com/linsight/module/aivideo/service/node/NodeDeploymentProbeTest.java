package com.linsight.module.aivideo.service.node;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class NodeDeploymentProbeTest {
    @TempDir Path root;

    @Test void discoversRknpuThroughDrmButNotARegularDisplayDevice() throws Exception {
        Path dev = Files.createDirectories(root.resolve("dev/dri"));
        Path drm = Files.createDirectories(root.resolve("sys/class/drm"));
        Path display = Files.createDirectories(drm.resolve("renderD128/device"));
        Files.writeString(display.resolve("uevent"), "DRIVER=rockchip-drm\n");
        Files.createFile(dev.resolve("renderD128"));
        assertEquals("False", probe());

        Path npu = Files.createDirectories(drm.resolve("renderD129/device"));
        Files.writeString(npu.resolve("uevent"), "DRIVER=RKNPU\nOF_NAME=npu\n");
        assertEquals("False", probe(), "A driver without an actual device is unavailable");
        Files.createFile(dev.resolve("renderD129"));
        assertEquals("True", probe());
    }

    @Test void keepsLegacyDeviceDetectionAndToleratesMissingSysfs() throws Exception {
        Files.createDirectories(root.resolve("dev"));
        assertEquals("False", probe());
        Files.createFile(root.resolve("dev/rknpu"));
        assertEquals("True", probe());
    }

    private String probe() throws Exception {
        String script = "import pathlib, sys\n" + NodeDeploymentProbe.RKNPU_PROBE
                + "print(rknpu_available(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])))\n";
        Process process = new ProcessBuilder("python3", "-c", script,
                root.resolve("dev").toString(), root.resolve("sys/class/drm").toString())
                .redirectErrorStream(true).start();
        boolean exited = process.waitFor(5, TimeUnit.SECONDS);
        if (!exited) process.destroyForcibly();
        assertTrue(exited, "Hardware probe timed out");
        String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8).trim();
        assertEquals(0, process.exitValue(), output);
        return output;
    }
}
