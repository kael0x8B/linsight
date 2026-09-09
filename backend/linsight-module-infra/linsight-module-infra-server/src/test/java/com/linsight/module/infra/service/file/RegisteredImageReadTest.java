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
class RegisteredImageReadTest {
 @Mock FileMapper fileMapper; @Mock FileConfigService fileConfigService; @Mock FileClient fileClient;
 @InjectMocks FileServiceImpl service;
 @Test void unregisteredUrlCannotCauseNetworkRequest() {
  assertThrows(com.linsight.framework.common.exception.ServiceException.class,()->service.readRegisteredImage("http://169.254.169.254/latest/meta-data"));
  verifyNoInteractions(fileConfigService,fileClient);
 }
 @Test void oversizedRegisteredFileIsRejectedBeforeReading() {
  var file=new FileDO();file.setSize(6L*1024*1024);when(fileMapper.selectOne(any())).thenReturn(file);
  assertThrows(com.linsight.framework.common.exception.ServiceException.class,()->service.readRegisteredImage("stored"));
  verifyNoInteractions(fileConfigService,fileClient);
 }
 @Test void storageClientReceivesRegisteredPathInsteadOfExternalUrl() throws Exception {
  var file=new FileDO();file.setSize(3L);file.setConfigId(1L);file.setPath("ai-video/recognition-library/photo.png");
  when(fileMapper.selectOne(any())).thenReturn(file);when(fileConfigService.getFileClient(1L)).thenReturn(fileClient);
  when(fileClient.getContent(file.getPath())).thenReturn(new byte[]{1,2,3});
  assertArrayEquals(new byte[]{1,2,3},service.readRegisteredImage("https://stored/photo.png?signature=redacted"));
  verify(fileClient).getContent("ai-video/recognition-library/photo.png");
 }
}
