package com.linsight.module.aivideo.service.node;

import com.linsight.module.aivideo.controller.admin.node.NodeApplicationReleaseController;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeApplicationReleaseCreateReqVO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeApplicationReleaseDO;
import com.linsight.module.aivideo.dal.mysql.node.NodeApplicationReleaseMapper;
import com.linsight.module.aivideo.integration.release.NodeApplicationReleaseProperties;
import com.linsight.module.infra.api.file.FileApi;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.security.access.prepost.PreAuthorize;
import jakarta.validation.Validation;
import java.util.function.Supplier;
import java.util.List;
import org.mockito.ArgumentCaptor;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class NodeApplicationReleaseTest {
    final NodeApplicationReleaseMapper mapper = mock(NodeApplicationReleaseMapper.class);
    final NodeApplicationReleaseProperties properties = spy(new NodeApplicationReleaseProperties());
    final NodeOperationService operations = mock(NodeOperationService.class);
    final FileApi files = mock(FileApi.class);
    final NodeApplicationReleaseService service = new NodeApplicationReleaseService();
    NodeApplicationReleaseTest() {
        ReflectionTestUtils.setField(service, "mapper", mapper);
        ReflectionTestUtils.setField(service, "properties", properties);
        ReflectionTestUtils.setField(service, "operations", operations);
        ReflectionTestUtils.setField(service, "fileApi", files);
        when(operations.exclusive(anyString(), any())).thenAnswer(call -> ((Supplier<?>) call.getArgument(1)).get());
    }
    NodeApplicationReleaseCreateReqVO request() {
        var request = new NodeApplicationReleaseCreateReqVO();
        request.setRequestId("01234567-89ab-cdef"); request.setProfileId("simulator");
        request.setVersion("simulator-1.0.6"); request.setNotes("Offline"); request.setBackwardCompatible(true);
        return request;
    }
    void ready() {
        var profile = new NodeApplicationReleaseProperties.Profile();
        profile.setLabel("ARM64 application"); profile.setArchitecture("aarch64");
        profile.setDevices(List.of("rk3566", "rk3568", "rk3588")); profile.setKeyId("test-key");
        properties.getProfiles().put("simulator", profile);
        doReturn(true).when(properties).ready(any());
    }
    @Test void rejectsUnconfiguredProfileBeforeQueuing() {
        assertThrows(RuntimeException.class, () -> service.create(request()));
        verify(mapper, never()).insert(any(NodeApplicationReleaseDO.class));
    }
    @Test void createsOneSharedBundleWithoutClientProfileOrCompatibilityCheckbox() {
        ready();
        properties.getProfiles().put("arm64", properties.getProfiles().get("simulator"));
        properties.setDefaultProfile("arm64");
        var request = request(); request.setProfileId(null); request.setBackwardCompatible(null);
        when(mapper.insert(any(NodeApplicationReleaseDO.class))).thenAnswer(call -> {
            ((NodeApplicationReleaseDO) call.getArgument(0)).setId(18L); return 1;
        });
        assertEquals(18L, service.create(request));
        var inserted = ArgumentCaptor.forClass(NodeApplicationReleaseDO.class);
        verify(mapper).insert(inserted.capture());
        assertEquals("arm64", inserted.getValue().getProfileId());
        assertEquals("rk3566,rk3568,rk3588", inserted.getValue().getDevices());
        assertEquals("aarch64", inserted.getValue().getArchitecture());
        assertEquals(List.of("rk3566", "rk3568", "rk3588"), service.configuration().devices());
        assertTrue(service.configuration().ready());
    }
    @Test void neverGuessesAmongMultipleProfilesOrFallsBackFromAnInvalidDefault() {
        ready(); assertEquals("simulator", properties.defaultProfileId());
        properties.getProfiles().put("arm64", properties.getProfiles().get("simulator"));
        var request = request(); request.setProfileId(null);
        assertFalse(service.configuration().ready());
        assertThrows(RuntimeException.class, () -> service.create(request));
        properties.setDefaultProfile("missing");
        assertFalse(service.configuration().ready());
        assertThrows(RuntimeException.class, () -> service.create(request));
        verify(mapper, never()).insert(any(NodeApplicationReleaseDO.class));
    }
    @Test void defaultRequestReplaySurvivesDefaultProfileChangesWithoutBuildingAgain() {
        var request = request(); request.setProfileId(null); request.setBackwardCompatible(null);
        var prior = new NodeApplicationReleaseDO(); prior.setId(19L); prior.setProfileId("old-default");
        prior.setVersion(request.getVersion()); prior.setNotes(request.getNotes());
        when(mapper.selectOne(any(com.baomidou.mybatisplus.core.toolkit.support.SFunction.class), any())).thenReturn(prior);
        properties.setDefaultProfile("new-unavailable-default");
        assertEquals(19L, service.create(request));
        request.setNotes("Different content");
        assertThrows(RuntimeException.class, () -> service.create(request));
        verify(mapper, never()).insert(any(NodeApplicationReleaseDO.class));
    }
    @Test void acceptsIdempotentReplayButRejectsChangedRequestBody() {
        ready(); var request = request(); var prior = new NodeApplicationReleaseDO();
        prior.setId(11L); prior.setProfileId(request.getProfileId()); prior.setVersion(request.getVersion()); prior.setNotes(request.getNotes());
        when(mapper.selectOne(any(com.baomidou.mybatisplus.core.toolkit.support.SFunction.class), any())).thenReturn(prior);
        assertEquals(11L, service.create(request));
        request.setNotes("Different release");
        assertThrows(RuntimeException.class, () -> service.create(request));
    }
    @Test void existingVersionCannotBeRepublished() {
        ready(); when(mapper.selectCount(any())).thenReturn(1L);
        assertThrows(RuntimeException.class, () -> service.create(request()));
    }
    @Test void refusesDownloadBeforeCompletionAndRejectsUnknownArtifact() {
        var row = new NodeApplicationReleaseDO(); row.setStatus("STORING");
        when(mapper.selectById(1L)).thenReturn(row);
        assertThrows(RuntimeException.class, () -> service.download(1L, "bundle"));
        row.setStatus("SUCCEEDED");
        assertThrows(RuntimeException.class, () -> service.download(1L, "../private-key"));
        verifyNoInteractions(files);
    }
    @Test void downloadsUseRegisteredFileAndShortExpiry() {
        var row = new NodeApplicationReleaseDO(); row.setStatus("SUCCEEDED"); row.setBundleFileId(9L);
        when(mapper.selectById(1L)).thenReturn(row);
        when(files.presignRegisteredFile(9L, 60)).thenReturn("signed-url");
        assertEquals("signed-url", service.download(1L, "bundle"));
        assertThrows(RuntimeException.class, () -> service.download(2L, "bundle"));
    }
    @Test void permissionAndRequestValidationCoverAllEntrypoints() {
        for (var method : NodeApplicationReleaseController.class.getDeclaredMethods()) {
            assertEquals("@ss.hasPermission('ai-video:node:upgrade')", method.getAnnotation(PreAuthorize.class).value());
        }
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator(); var request = request();
            assertTrue(validator.validate(request).isEmpty());
            request.setProfileId(null); request.setBackwardCompatible(null);
            assertTrue(validator.validate(request).isEmpty());
            request.setVersion("../release;$(command)"); assertFalse(validator.validate(request).isEmpty());
            request = request(); request.setBackwardCompatible(false); assertFalse(validator.validate(request).isEmpty());
            request = request(); request.setProfileId("/arbitrary/path"); assertFalse(validator.validate(request).isEmpty());
        }
    }
    @Test void claimedJobsCannotCompleteAfterLeaseExpiry() {
        // The same fenced predicate protects progress, failure and publication updates.
        var worker = new NodeApplicationReleaseWorker(); var row = new NodeApplicationReleaseDO(); row.setId(17L);
        com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper<NodeApplicationReleaseDO> wrapper =
                ReflectionTestUtils.invokeMethod(worker, "owned", row);
        com.baomidou.mybatisplus.core.MybatisConfiguration config = new com.baomidou.mybatisplus.core.MybatisConfiguration();
        com.baomidou.mybatisplus.core.metadata.TableInfoHelper.initTableInfo(new org.apache.ibatis.builder.MapperBuilderAssistant(config, ""), NodeApplicationReleaseDO.class);
        assertTrue(wrapper.getSqlSegment().contains("lease_until > NOW()"));
        assertTrue(wrapper.getSqlSegment().contains("executor_owner"));
    }
}
