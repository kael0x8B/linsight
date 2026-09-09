package com.linsight.module.aivideo.integration.runtime;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class RuntimePreviewClientTest {

    @Test
    void runtimeDiagnosticIdMustBePreservedAcrossAdapterBoundary() {
        String diagnosticId = "f0b2e48b-1d1e-4fe8-b7e1-064a2b91724d";
        NodePreviewTunnelHandler.TunnelRequestException cause =
                new NodePreviewTunnelHandler.TunnelRequestException(diagnosticId,
                        "PREVIEW_STREAM_OPEN_FAILED", "Runtime rejected preview request");

        RuntimePreviewClient.RuntimePreviewException exception =
                new RuntimePreviewClient.RuntimePreviewException(cause);

        assertEquals(diagnosticId, exception.getDiagnosticId());
    }

}
