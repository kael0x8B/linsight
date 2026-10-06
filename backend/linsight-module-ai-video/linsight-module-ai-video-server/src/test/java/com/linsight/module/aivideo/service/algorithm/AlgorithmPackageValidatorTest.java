package com.linsight.module.aivideo.service.algorithm;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.framework.common.util.json.JsonUtils;
import org.junit.jupiter.api.Test;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import static org.junit.jupiter.api.Assertions.*;

class AlgorithmPackageValidatorTest {
    private Map<String, Object> manifest() {
        return new LinkedHashMap<>(Map.of("schemaVersion", "1.0", "sdkVersion", "1.0", "code", "unknown-supplier",
                "name", "外部算法", "version", "1.0.0", "entrypoint", "processor.py", "models", List.of(Map.of("slot", "person")),
                "parameterSchema", Map.of("type", "object", "properties", Map.of("libraryId", Map.of("type", "integer", "minimum", 1)), "required", List.of("libraryId"))));
    }
    private byte[] zip(Map<String, Object> manifest, String path) throws Exception {
        var bytes = new ByteArrayOutputStream();
        try (var zip = new ZipOutputStream(bytes)) {
            zip.putNextEntry(new ZipEntry("algorithm.json")); zip.write(JsonUtils.toJsonString(manifest).getBytes(StandardCharsets.UTF_8)); zip.closeEntry();
            zip.putNextEntry(new ZipEntry(path)); zip.write("raise RuntimeError('must not execute on upload')".getBytes(StandardCharsets.UTF_8)); zip.closeEntry();
        }
        return bytes.toByteArray();
    }
    @Test void validatesWithoutExecutingAndAllowsUserSuppliedRequiredValues() throws Exception {
        assertEquals("unknown-supplier", AlgorithmPackageValidator.inspect(zip(manifest(), "processor.py")).get("code"));
        var schema = AlgorithmPackageValidator.map(manifest().get("parameterSchema"));
        assertThrows(ServiceException.class, () -> AlgorithmPackageValidator.validateParameters(schema, Map.of()));
        assertThrows(ServiceException.class, () -> AlgorithmPackageValidator.validateParameters(schema, Map.of("libraryId", "1")));
        assertDoesNotThrow(() -> AlgorithmPackageValidator.validateParameters(schema, Map.of("libraryId", 1)));
    }
    @Test void rejectsIncompatibleSdkTraversalAndMalformedDescriptions() throws Exception {
        var incompatible = manifest(); incompatible.put("sdkVersion", "2.0");
        assertThrows(ServiceException.class, () -> AlgorithmPackageValidator.inspect(zip(incompatible, "processor.py")));
        assertThrows(ServiceException.class, () -> AlgorithmPackageValidator.inspect(zip(manifest(), "../processor.py")));
        var malformed = manifest(); malformed.put("timeoutMillis", "invalid");
        assertThrows(ServiceException.class, () -> AlgorithmPackageValidator.inspect(zip(malformed, "processor.py")));
    }
    @Test void assignedPeopleCannotBeEmptyOrSelectMoreThanTheDeclaredLimit() {
        var schema = Map.<String, Object>of("properties", Map.of("personIds",
                Map.of("type", "array", "minItems", 1, "maxItems", 1)));
        assertThrows(ServiceException.class, () -> AlgorithmPackageValidator.validateParameters(schema, Map.of("personIds", List.of())));
        assertThrows(ServiceException.class, () -> AlgorithmPackageValidator.validateParameters(schema, Map.of("personIds", List.of(8, 9))));
        assertDoesNotThrow(() -> AlgorithmPackageValidator.validateParameters(schema, Map.of("personIds", List.of(8))));
    }
    @Test void compatibilityRequiresFormatTaskTypeAndLabelsTogether() {
        var role = Map.<String, Object>of("formats", List.of("RKNN"), "taskType", "OBJECT_DETECTION", "labels", List.of("helmet", "no_helmet"));
        var helmet = Map.<String, Object>of("taskType", "OBJECT_DETECTION", "decoder", Map.of("labels", List.of("helmet", "no_helmet")));
        assertFalse(AlgorithmPackageService.compatible(role, "RKNN", null));
        assertTrue(AlgorithmPackageService.compatible(role, "RKNN", helmet));
        assertFalse(AlgorithmPackageService.compatible(role, "ONNX", helmet));
        assertFalse(AlgorithmPackageService.compatible(role, "RKNN", Map.of("taskType", "OBJECT_DETECTION", "decoder", Map.of("labels", List.of("person")))));
    }

    @Test void plateEvidenceRequiresCompatibleDecodersAndAnExplicitRuntimeCapability() {
        var value = manifest();
        var detector = Map.<String, Object>of("slot", "plate", "taskType", "OBJECT_DETECTION", "decoderTypes", List.of("YOLO_PLATE"));
        var ocr = Map.<String, Object>of("slot", "ocr", "taskType", "OCR", "decoderTypes", List.of("CHINESE_PLATE_CTC"));
        value.put("models", List.of(detector, ocr));
        value.put("frameInput", Map.of("type", "PLATE_OCR", "detectorSlot", "plate", "ocrSlot", "ocr"));
        assertThrows(ServiceException.class, () -> AlgorithmPackageValidator.validateManifest(value));
        value.put("runtimeRequirements", List.of("plate-ocr-evidence-v1"));
        assertDoesNotThrow(() -> AlgorithmPackageValidator.validateManifest(value));
        assertFalse(AlgorithmPackageService.compatible(ocr, "ONNX", Map.of("taskType", "OCR", "decoder", Map.of("type", "LPRNET"))));
        assertTrue(AlgorithmPackageService.compatible(ocr, "RKNN", Map.of("taskType", "OCR", "decoder", Map.of("type", "CHINESE_PLATE_CTC"))));
        value.put("frameInput", Map.of("type", "PLATE_OCR", "detectorSlot", "plate", "ocrSlot", "plate"));
        assertThrows(ServiceException.class, () -> AlgorithmPackageValidator.validateManifest(value));
    }

    @Test void downloadablePackagesCarryValidatedRuleDefaults() throws Exception {
        var root = java.nio.file.Path.of("").toAbsolutePath();
        while (root != null && !java.nio.file.Files.isDirectory(root.resolve("runtime/algorithm_packages"))) root = root.getParent();
        assertNotNull(root, "repository examples must be available");
        for (String name : List.of("fall", "vehicle-parking", "person-absence", "person-absence-count", "xinjiang-plate")) {
            var manifest = JsonUtils.parseMap(java.nio.file.Files.readString(root.resolve("runtime/algorithm_packages/" + name + "/algorithm.json")));
            assertDoesNotThrow(() -> AlgorithmPackageValidator.inspect(zip(manifest, "processor.py")));
            var rule = AlgorithmPackageValidator.map(manifest.get("defaultRule"));
            rule.put("eventType", "WRONG_EVENT");
            assertThrows(ServiceException.class, () -> AlgorithmPackageValidator.inspect(zip(manifest, "processor.py")));
        }
    }
}
