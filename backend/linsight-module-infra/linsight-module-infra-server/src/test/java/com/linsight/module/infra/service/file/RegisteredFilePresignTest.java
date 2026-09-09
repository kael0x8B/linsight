package com.linsight.module.infra.service.file;

import com.linsight.module.infra.dal.mysql.file.FileMapper;
import com.linsight.module.infra.dal.dataobject.file.FileDO;
import com.linsight.module.infra.framework.file.core.client.FileClient;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(MockitoExtension.class)
class RegisteredFilePresignTest {
    @Mock FileMapper fileMapper;
    @Mock FileConfigService fileConfigService;
    @Mock FileClient fileClient;
    @InjectMocks FileServiceImpl service;

    @Test void oldHostAndExpiredSignatureUseRegisteredObjectKeyAndOriginalStorage() {
        var file = new FileDO().setConfigId(71000L).setPath("ai-video/model/helmet.rknn");
        when(fileMapper.selectOne(any())).thenReturn(file);
        when(fileConfigService.getFileClient(71000L)).thenReturn(fileClient);
        when(fileClient.presignGetUrl(file.getPath(), 600)).thenReturn("https://current.invalid/fresh");
        assertEquals("https://current.invalid/fresh", service.presignGetUrl(
                "http://old.invalid/bucket/ai-video/model/helmet.rknn?X-Amz-Signature=expired", 600));
        verify(fileClient).presignGetUrl("ai-video/model/helmet.rknn", 600);
        verify(fileConfigService, never()).getMasterFileClient();
    }

    @Test void bareObjectKeysRemainCompatible() {
        when(fileConfigService.getMasterFileClient()).thenReturn(fileClient);
        when(fileClient.presignGetUrl("model/helmet.rknn", 600)).thenReturn("fresh");
        assertEquals("fresh", service.presignGetUrl("model/helmet.rknn", 600));
    }
}
