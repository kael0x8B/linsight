package com.linsight.module.aivideo.service.model;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelVersionUploadReqVO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelVersionDO;
import com.linsight.module.aivideo.dal.mysql.model.ModelMapper;
import com.linsight.module.aivideo.dal.mysql.model.ModelVersionMapper;
import com.linsight.module.infra.api.file.FileApi;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockMultipartFile;

import java.io.ByteArrayOutputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ModelServiceImplTest {

    @Mock
    private ModelMapper modelMapper;
    @Mock
    private ModelVersionMapper modelVersionMapper;
    @Mock
    private FileApi fileApi;
    @InjectMocks
    private ModelServiceImpl modelService;

    @Test
    void rejectResizeModesNotSupportedByRuntimeBeforeDeployment() {
        String manifest = version("MIT").getRuntimeManifest().replace("\"preprocess\":{", "\"preprocess\":{\"resize\":\"LETTERBOX\",");
        assertThrows(ServiceException.class, () -> ModelServiceImpl.validateRuntimeManifest(manifest));
    }

    @Test
    void plateDecodersMustMatchTheirTaskAndLetterboxContract() {
        String detector = runtimeManifest().replace("AUTO_DETECTION", "YOLO_PLATE")
                .replace("\"preprocess\":{", "\"preprocess\":{\"resize\":\"LETTERBOX\",");
        ModelServiceImpl.validateRuntimeManifest(detector);
        assertThrows(ServiceException.class, () -> ModelServiceImpl.validateRuntimeManifest(
                detector.replace("OBJECT_DETECTION", "OCR")));
        String ocr = runtimeManifest().replace("AUTO_DETECTION", "CHINESE_PLATE_CTC")
                .replace("OBJECT_DETECTION", "OCR");
        ModelServiceImpl.validateRuntimeManifest(ocr);
        assertThrows(ServiceException.class, () -> ModelServiceImpl.validateRuntimeManifest(
                ocr.replace("OCR", "CLASSIFICATION")));
    }

    @Test
    void routedOcrRightPaddingRequiresItsDecoderAndOcrTask() {
        String manifest = routedOcrManifest();

        ModelServiceImpl.validateRuntimeManifest(manifest);

        assertThrows(ServiceException.class, () -> ModelServiceImpl.validateRuntimeManifest(
                manifest.replace("PLATE_OCR_ROUTED", "CHINESE_PLATE_CTC")));
        assertThrows(ServiceException.class, () -> ModelServiceImpl.validateRuntimeManifest(
                manifest.replace("\"taskType\": \"OCR\"", "\"taskType\": \"OBJECT_DETECTION\"")));
    }

    @Test
    void routedOcrArchiveUploadPreservesItsExecutionManifest() throws Exception {
        when(modelMapper.selectById(1L)).thenReturn(model());
        when(fileApi.createFile(any(byte[].class), anyString(), anyString(), anyString()))
                .thenReturn("model/routed-ocr");
        ByteArrayOutputStream content = new ByteArrayOutputStream();
        try (ZipOutputStream archive = new ZipOutputStream(content)) {
            for (String member : new String[]{"specialist.onnx", "site.onnx"}) {
                archive.putNextEntry(new ZipEntry(member));
                archive.write(new byte[]{0x08, 0x08, 0x3a, 0x00});
                archive.closeEntry();
            }
        }
        ModelVersionUploadReqVO request = uploadRequest("plate-ocr-routed.zip", "GPL-3.0; Apache-2.0",
                content.toByteArray());
        request.setRuntimeManifest(routedOcrManifest());

        modelService.uploadVersion(request);

        ArgumentCaptor<ModelVersionDO> captor = ArgumentCaptor.forClass(ModelVersionDO.class);
        verify(modelVersionMapper).insert(captor.capture());
        assertEquals("ARCHIVE", captor.getValue().getArtifactFormat());
        assertEquals(JsonUtils.parseMap(routedOcrManifest()),
                JsonUtils.parseMap(captor.getValue().getRuntimeManifest()));
        assertEquals("DRAFT", captor.getValue().getPublishStatus());
    }

    @Test
    void runtimeManifestSupportsGenericProviderTargetAndMinimumVersion() {
        String manifest = runtimeManifest().replace("\"preprocess\":{",
                "\"targetPlatform\":\"sm_87\",\"execution\":{" +
                "\"provider\":\"nvidia-tensorrt\",\"target\":\"sm_87\"," +
                "\"runtime\":\"tensorrt\",\"minRuntimeVersion\":\"10.2.0\"},\"preprocess\":{");

        ModelServiceImpl.validateRuntimeManifest(manifest);
        assertThrows(ServiceException.class, () -> ModelServiceImpl.validateRuntimeManifest(
                manifest.replace("\"target\":\"sm_87\"", "\"target\":\"sm_89\"")));
        assertThrows(ServiceException.class, () -> ModelServiceImpl.validateRuntimeManifest(
                runtimeManifest().replace("\"preprocess\":{",
                        "\"execution\":{\"provider\":\"nvidia-tensorrt\"," +
                        "\"minRuntimeVersion\":\"10.2.0\"},\"preprocess\":{")));
    }

    @Test
    void uploadVersionMustHashValidateAndStoreWithoutExposingArtifact() throws Exception {
        when(modelMapper.selectById(1L)).thenReturn(model());
        when(fileApi.createFile(any(byte[].class), anyString(), anyString(), anyString()))
                .thenReturn("http://minio.internal/models/person.onnx");
        ModelVersionUploadReqVO request = uploadRequest("person.onnx", "Apache-2.0");

        modelService.uploadVersion(request);

        ArgumentCaptor<ModelVersionDO> captor = ArgumentCaptor.forClass(ModelVersionDO.class);
        verify(modelVersionMapper).insert(captor.capture());
        ModelVersionDO persisted = captor.getValue();
        assertEquals("ONNX", persisted.getArtifactFormat());
        assertEquals(64, persisted.getSha256().length());
        assertEquals("VERIFIED", persisted.getValidationStatus());
        assertEquals("DRAFT", persisted.getPublishStatus());
        assertTrue(!persisted.toString().contains("minio.internal"));
        verify(modelVersionMapper).selectByModelAndSha256(1L, persisted.getSha256());
    }

    @Test
    void uploadVersionMustRejectUnsupportedFormatBeforeObjectStorage() {
        when(modelMapper.selectById(1L)).thenReturn(model());
        ModelVersionUploadReqVO request = uploadRequest("person.exe", "Apache-2.0");

        ServiceException error = assertThrows(ServiceException.class, () -> modelService.uploadVersion(request));

        assertEquals(1_020_001_013, error.getCode());
        verify(fileApi, never()).createFile(any(byte[].class), anyString(), anyString(), anyString());
    }

    @Test
    void ptExtensionMustBeStoredAsPytorchCheckpointNotTorchscript() throws Exception {
        when(modelMapper.selectById(1L)).thenReturn(model());
        when(fileApi.createFile(any(byte[].class), anyString(), anyString(), anyString()))
                .thenReturn("model/ref");
        ModelVersionUploadReqVO request = uploadRequest(
                "person.pt", "Apache-2.0", new byte[]{0x50, 0x4b, 0x03, 0x04});

        modelService.uploadVersion(request);

        ArgumentCaptor<ModelVersionDO> captor = ArgumentCaptor.forClass(ModelVersionDO.class);
        verify(modelVersionMapper).insert(captor.capture());
        assertEquals("PYTORCH", captor.getValue().getArtifactFormat());
    }

    @Test
    void uploadVersionMustRejectExecutableMasqueradingAsOnnx() {
        when(modelMapper.selectById(1L)).thenReturn(model());
        ModelVersionUploadReqVO request = uploadRequest(
                "person.onnx", "Apache-2.0", new byte[]{'M', 'Z', 0, 0, 1, 2});

        ServiceException error = assertThrows(ServiceException.class, () -> modelService.uploadVersion(request));

        assertEquals(1_020_001_013, error.getCode());
        verify(fileApi, never()).createFile(any(byte[].class), anyString(), anyString(), anyString());
    }

    @Test
    void uploadVersionMustRejectTraversalFileName() {
        when(modelMapper.selectById(1L)).thenReturn(model());
        ModelVersionUploadReqVO request = uploadRequest("../person.onnx", "Apache-2.0");

        assertThrows(ServiceException.class, () -> modelService.uploadVersion(request));

        verify(fileApi, never()).createFile(any(byte[].class), anyString(), anyString(), anyString());
    }

    @Test
    void publishMustNotApplyCommercialOrLicenseReviewGate() {
        ModelDO model = model();
        ModelVersionDO version = version("UNKNOWN");
        when(modelVersionMapper.selectById(10L)).thenReturn(version);
        when(modelMapper.selectById(1L)).thenReturn(model);

        modelService.publishVersion(10L);

        assertEquals("PUBLISHED", version.getPublishStatus());
        assertEquals(10L, model.getCurrentVersionId());
        verify(modelMapper).updateById(model);
    }

    @Test
    void publishMustSupersedePreviousAndPointModelToImmutableVersion() {
        ModelDO model = model();
        ModelVersionDO version = version("Apache-2.0");
        when(modelVersionMapper.selectById(10L)).thenReturn(version);
        when(modelMapper.selectById(1L)).thenReturn(model);

        modelService.publishVersion(10L);

        verify(modelVersionMapper).supersedeCurrentPublished(1L, 10L);
        assertEquals("PUBLISHED", version.getPublishStatus());
        assertEquals(10L, model.getCurrentVersionId());
        verify(modelMapper).updateById(model);
    }

    private static ModelDO model() {
        ModelDO model = new ModelDO();
        model.setId(1L);
        model.setName("Person Detection Model");
        model.setCode("person-detection");
        model.setSourceType("PRESET");
        model.setStatus(0);
        return model;
    }

    private static ModelVersionDO version(String license) {
        ModelVersionDO version = new ModelVersionDO();
        version.setId(10L);
        version.setModelId(1L);
        version.setVersion("1.0.0");
        version.setSourceRepository("https://example.invalid/model.git");
        version.setSourceRevision("0123456789abcdef");
        version.setLicenseSpdx(license);
        version.setValidationStatus("VERIFIED");
        version.setPublishStatus("DRAFT");
        version.setRuntimeManifest(runtimeManifest());
        return version;
    }

    private static ModelVersionUploadReqVO uploadRequest(String name, String license) {
        return uploadRequest(name, license, new byte[]{0x08, 0x08, 0x3a, 0x00});
    }

    private static ModelVersionUploadReqVO uploadRequest(
            String name, String license, byte[] content) {
        ModelVersionUploadReqVO request = new ModelVersionUploadReqVO();
        request.setModelId(1L);
        request.setVersion("1.0.0");
        request.setSourceRepository("https://example.invalid/model.git");
        request.setSourceRevision("0123456789abcdef");
        request.setLicenseSpdx(license);
        request.setRuntimeManifest(runtimeManifest());
        request.setFile(new MockMultipartFile("file", name, "application/octet-stream", content));
        return request;
    }

    private static String runtimeManifest() {
        return "{\"schemaVersion\":\"1.0\",\"taskType\":\"OBJECT_DETECTION\"," +
                "\"preprocess\":{\"color\":\"RGB\",\"layout\":\"NCHW\",\"dtype\":\"FLOAT32\"}," +
                "\"decoder\":{\"type\":\"AUTO_DETECTION\",\"labels\":[\"person\"]}}";
    }

    private static String routedOcrManifest() {
        // The shipped two-model archive uses this complete preprocessing contract.
        return """
                {
                  "schemaVersion": "1.0",
                  "taskType": "OCR",
                  "preprocess": {
                    "inputWidth": 320,
                    "inputHeight": 48,
                    "color": "BGR",
                    "layout": "NCHW",
                    "dtype": "FLOAT32",
                    "scale": 0.00392156862745098,
                    "mean": [0.5, 0.5, 0.5],
                    "std": [0.5, 0.5, 0.5],
                    "resize": "OCR_RIGHT_PAD"
                  },
                  "decoder": {
                    "type": "PLATE_OCR_ROUTED"
                  }
                }
                """;
    }
}
