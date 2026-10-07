package com.linsight.module.aivideo.service.node;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class NodeDeploymentScriptEncodingTest {

    @Test
    void normalizesBomAndMixedLineEndingsWithoutChangingShellContent() {
        String source = "\uFEFF#!/usr/bin/env bash\r\nset -euo pipefail\r"
                + "printf '%s\\n' '部署检查'\n";
        byte[] expected = ("#!/usr/bin/env bash\nset -euo pipefail\n"
                + "printf '%s\\n' '部署检查'\n").getBytes(StandardCharsets.UTF_8);

        byte[] normalized = NodeDeploymentRunner.normalizeShellScript(source.getBytes(StandardCharsets.UTF_8));

        assertArrayEquals(expected, normalized);
        assertArrayEquals(normalized, NodeDeploymentRunner.normalizeShellScript(normalized));
    }

    @Test
    void fixesActualCleanupHeaderPipefailErrorBeforeExecutingAnyCleanupCommands() throws Exception {
        String cleanup = new String(NodeDeploymentRunner.diskPressureCleanupScript(), StandardCharsets.UTF_8);
        // Execute only the shebang, comment and strict-mode line, never the cleanup body.
        String header = cleanup.lines().limit(3).reduce("", (text, line) -> text + line + "\n");
        assertTrue(header.endsWith("set -euo pipefail\n"));
        byte[] windowsHeader = header.replace("\n", "\r\n").getBytes(StandardCharsets.UTF_8);

        ShellResult broken = runBash(windowsHeader, false);
        assertNotEquals(0, broken.exitCode());
        assertTrue(broken.output().contains("pipefail"), broken.output());

        ShellResult repaired = runBash(NodeDeploymentRunner.normalizeShellScript(windowsHeader), false);
        assertEquals(0, repaired.exitCode(), repaired.output());
    }

    @ParameterizedTest
    @ValueSource(strings = {"recoveryScript", "dependencyScript", "pythonScript", "diskPressureCleanupScript"})
    void allUploadedShellResourcesRemainValidAfterWindowsLineEndingConversion(String loader) throws Exception {
        byte[] uploaded = ReflectionTestUtils.invokeMethod(NodeDeploymentRunner.class, loader);
        assertNotNull(uploaded);
        String script = new String(uploaded, StandardCharsets.UTF_8);
        assertFalse(script.contains("\r"));
        assertFalse(script.startsWith("\uFEFF"));
        byte[] repackaged = ("\uFEFF" + script.replace("\n", "\r\n")).getBytes(StandardCharsets.UTF_8);
        byte[] normalized = NodeDeploymentRunner.normalizeShellScript(repackaged);
        assertArrayEquals(uploaded, normalized);

        ShellResult result = runBash(normalized, true);
        assertEquals(0, result.exitCode(), loader + ": " + result.output());
    }

    private static ShellResult runBash(byte[] script, boolean syntaxOnly) throws Exception {
        Process process = new ProcessBuilder(syntaxOnly ? new String[]{"bash", "-n"} : new String[]{"bash"})
                .redirectErrorStream(true).start();
        try {
            try (var input = process.getOutputStream()) {
                input.write(script);
            }
            assertTrue(process.waitFor(5, TimeUnit.SECONDS), "Bash did not finish within five seconds");
            return new ShellResult(process.exitValue(),
                    new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8));
        } finally {
            if (process.isAlive()) process.destroyForcibly();
        }
    }

    private record ShellResult(int exitCode, String output) { }
}
