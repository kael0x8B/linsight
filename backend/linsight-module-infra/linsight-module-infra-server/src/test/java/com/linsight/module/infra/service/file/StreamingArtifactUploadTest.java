package com.linsight.module.infra.service.file;

import com.linsight.module.infra.controller.admin.file.vo.file.FileCreateReqVO;
import com.linsight.module.infra.framework.file.core.client.FileClient;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class StreamingArtifactUploadTest {
    @TempDir Path root;
    @Test void delegatesPathToStorageAndRegistersOnlySuccessfulUpload() throws Exception {
        var source = root.resolve("large.lup");
        byte[] data = new byte[4 * 1024 * 1024]; Files.write(source, data);
        var service = spy(new FileServiceImpl());
        var configs = mock(FileConfigService.class); var client = mock(FileClient.class);
        ReflectionTestUtils.setField(service, "fileConfigService", configs);
        when(configs.getMasterFileClient()).thenReturn(client); when(client.getId()).thenReturn(7L);
        when(client.upload(eq(source), anyString(), eq("application/octet-stream")))
                .thenReturn("https://storage.invalid/package.lup?signature=secret");
        doReturn(99L).when(service).createFile(any(FileCreateReqVO.class));
        assertEquals(99L, service.createFileFromPath(source, "package.lup", "release/1", "application/octet-stream"));
        verify(service).createFile(argThat((FileCreateReqVO file) -> file.getSize() == data.length
                && file.getUrl().equals("https://storage.invalid/package.lup") && file.getConfigId() == 7L));
        verify(client, never()).upload(any(byte[].class), anyString(), anyString());
        when(client.upload(eq(source), anyString(), anyString())).thenThrow(new IllegalStateException("Storage unavailable"));
        assertThrows(IllegalStateException.class, () -> service.createFileFromPath(source, "package.lup", "release/1", "application/octet-stream"));
        verify(service, times(1)).createFile(any(FileCreateReqVO.class));
    }
    @Test void rejectsEmptyAndSymlinkSourcesBeforeStorageAccess() throws Exception {
        var source = Files.createFile(root.resolve("empty")); var service = spy(new FileServiceImpl());
        assertThrows(IllegalArgumentException.class, () -> service.createFileFromPath(source, "file", "release", "application/octet-stream"));
        Files.writeString(source, "data"); var link = Files.createSymbolicLink(root.resolve("link"), source);
        assertThrows(IllegalArgumentException.class, () -> service.createFileFromPath(link, "file", "release", "application/octet-stream"));
    }
    @Test void dedicatedBuildStorageDoesNotUseOrChangeTheDefaultStore() throws Exception {
        var source = Files.writeString(root.resolve("package.lup"), "signed test artifact");
        var service = spy(new FileServiceImpl());
        var configs = mock(FileConfigService.class); var client = mock(FileClient.class);
        ReflectionTestUtils.setField(service, "fileConfigService", configs);
        when(configs.getFileClient(71001L)).thenReturn(client);
        when(client.getId()).thenReturn(71001L);
        when(client.upload(eq(source), anyString(), anyString())).thenReturn("http://127.0.0.1/private/package.lup?signature=secret");
        doReturn(12L).when(service).createFile(any(FileCreateReqVO.class));
        assertEquals(12L, service.createFileFromPath(source, "package.lup", "release/test", "application/octet-stream", 71001L));
        verify(configs, never()).getMasterFileClient();
        verify(service).createFile(argThat((FileCreateReqVO file) -> file.getConfigId() == 71001L
                && !file.getUrl().contains("signature")));
        assertThrows(IllegalArgumentException.class, () -> service.createFileFromPath(source, "package.lup", "release/test", "application/octet-stream", 999L));
        verify(configs, never()).getMasterFileClient();
    }
}
