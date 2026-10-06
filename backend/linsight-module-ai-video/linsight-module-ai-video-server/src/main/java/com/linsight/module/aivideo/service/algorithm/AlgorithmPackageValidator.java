package com.linsight.module.aivideo.service.algorithm;

import com.linsight.framework.common.util.json.JsonUtils;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.ZipInputStream;

/** Validates code artifacts without loading or executing supplier code in the control plane. */
public final class AlgorithmPackageValidator {
    public static final int MAX_BYTES = 8 * 1024 * 1024;
    private AlgorithmPackageValidator() { }

    public static Map<String, Object> inspect(byte[] bytes) {
        if (bytes.length == 0 || bytes.length > MAX_BYTES) throw invalid("算法包最大 8 MB，模型文件请单独上传");
        Map<String, byte[]> files = new HashMap<>();
        int total = 0;
        try (var zip = new ZipInputStream(new ByteArrayInputStream(bytes), StandardCharsets.UTF_8)) {
            java.util.zip.ZipEntry entry;
            int count = 0;
            while ((entry = zip.getNextEntry()) != null) {
                String name = entry.getName();
                if (++count > 128 || name.startsWith("/") || name.contains("\\") || name.contains(":")
                        || Arrays.asList(name.split("/")).contains("..") || files.containsKey(name)) {
                    throw invalid("算法包包含不安全、重复路径或过多文件");
                }
                if (entry.isDirectory()) continue;
                if (!name.matches(".*\\.(py|json|txt|md)")) throw invalid("算法包只接受 Python、JSON 和说明文件");
                byte[] data = zip.readNBytes(32 * 1024 * 1024 + 1 - total);
                total += data.length;
                if (total > 32 * 1024 * 1024) throw invalid("算法包解压大小超限");
                files.put(name, data);
            }
            byte[] manifestBytes = files.get("algorithm.json");
            if (manifestBytes == null || manifestBytes.length > 256 * 1024) throw invalid("缺少有效的 algorithm.json");
            Map<String, Object> manifest = JsonUtils.parseMap(new String(manifestBytes, StandardCharsets.UTF_8));
            validateManifest(manifest);
            if (!files.containsKey((String) manifest.get("entrypoint"))) throw invalid("算法执行入口不存在");
            return manifest;
        } catch (com.linsight.framework.common.exception.ServiceException error) {
            throw error;
        } catch (java.io.IOException | RuntimeException error) {
            throw invalid("算法 ZIP 或描述文件无效");
        }
    }

    public static void validateManifest(Map<String, Object> manifest) {
        if (manifest == null || !"1.0".equals(manifest.get("schemaVersion")) || !"1.0".equals(manifest.get("sdkVersion"))) {
            throw invalid("算法包需要 SDK 1.0");
        }
        requireText(manifest, "code", "[a-z][a-z0-9-]{1,63}");
        requireText(manifest, "version", "[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}");
        requireText(manifest, "name", ".{1,100}");
        requireText(manifest, "entrypoint", "[a-zA-Z_][a-zA-Z0-9_]*\\.py");
        if (!(manifest.get("models") instanceof List<?> models) || models.isEmpty() || models.size() > 20) {
            throw invalid("算法必须声明 1–20 个模型角色");
        }
        Set<String> slots = new HashSet<>();
        for (Object value : models) {
            if (!(value instanceof Map<?, ?> role) || !(role.get("slot") instanceof String slot)
                    || !slot.matches("[a-z][a-z0-9-]{0,63}") || !slots.add(slot)) throw invalid("模型角色无效或重复");
            if (role.containsKey("decoderTypes") && (!(role.get("decoderTypes") instanceof List<?> types)
                    || types.stream().anyMatch(type -> !(type instanceof String)))) throw invalid("模型解码器要求必须为字符串数组");
            if (role.containsKey("labels") && !(role.get("labels") instanceof List<?>)) throw invalid("模型标签要求无效");
        }
        if (manifest.containsKey("frameInput")) validatePlateInput(manifest);
        if (!(manifest.getOrDefault("timeoutMillis", 3000) instanceof Number)) throw invalid("算法超时必须是数字");
        int timeout = ((Number) manifest.getOrDefault("timeoutMillis", 3000)).intValue();
        if (timeout < 100 || timeout > 30000) throw invalid("算法超时必须为 100–30000 毫秒");
        Map<String, Object> schema = map(manifest.getOrDefault("parameterSchema", Map.of("type", "object", "properties", Map.of())));
        if (!"object".equals(schema.get("type"))) throw invalid("算法参数必须是对象 JSON Schema");
        var defaultSchema = new LinkedHashMap<>(schema);
        defaultSchema.put("required", List.of());
        validateParameters(defaultSchema, map(manifest.getOrDefault("defaultParameters", Map.of())));
        if (manifest.containsKey("defaultRule")) {
            var errors = com.linsight.module.aivideo.service.rule.RuleAstValidator.validate(
                    map(manifest.get("defaultRule")), String.valueOf(manifest.getOrDefault("eventType", "ALGORITHM_EVENT")));
            if (!errors.isEmpty()) throw invalid("默认告警规则无效：" + String.join("；", errors));
        }
    }

    private static void validatePlateInput(Map<String, Object> manifest) {
        var input = map(manifest.get("frameInput"));
        if (!"PLATE_OCR".equals(input.get("type"))
                || !(manifest.get("runtimeRequirements") instanceof List<?> requirements)
                || !requirements.contains("plate-ocr-evidence-v1")) throw invalid("车牌输入需要 plate-ocr-evidence-v1 能力");
        var detector = input.get("detectorSlot");
        var ocr = input.get("ocrSlot");
        if (!(detector instanceof String) || !(ocr instanceof String) || detector.equals(ocr)) throw invalid("车牌模型角色无效");
        var roles = ((List<?>) manifest.get("models")).stream().map(AlgorithmPackageValidator::map).toList();
        if (roles.size() != 2) throw invalid("车牌输入需要定位与 OCR 两个模型角色");
        for (String field : List.of("detectorSlot", "ocrSlot")) {
            var role = roles.stream().filter(r -> input.get(field).equals(r.get("slot"))).findFirst().orElseThrow(() -> invalid("车牌模型角色不存在"));
            boolean detection = field.equals("detectorSlot");
            var allowed = detection ? List.of("YOLO_PLATE", "YOLO26_PLATE_POSE") : List.of("CHINESE_PLATE_CTC", "PLATE_OCR_ROUTED");
            if (!(detection ? "OBJECT_DETECTION" : "OCR").equals(role.get("taskType"))
                    || !(role.get("decoderTypes") instanceof List<?> types) || types.isEmpty()
                    || !allowed.containsAll(types)) throw invalid("车牌输入必须声明兼容的模型解码器");
        }
    }

    public static void validateParameters(Map<String, Object> schema, Map<String, Object> values) {
        Map<String, Object> properties = map(schema.getOrDefault("properties", Map.of()));
        for (Object key : (List<?>) schema.getOrDefault("required", List.of())) {
            if (!values.containsKey(key)) throw invalid("缺少必填配置：" + key);
        }
        if (Boolean.FALSE.equals(schema.get("additionalProperties")) && !properties.keySet().containsAll(values.keySet())) {
            throw invalid("包含未声明算法配置");
        }
        for (var entry : values.entrySet()) {
            if (!properties.containsKey(entry.getKey())) continue;
            var spec = map(properties.get(entry.getKey()));
            Object value = entry.getValue();
            String type = String.valueOf(spec.get("type"));
            boolean valid = switch (type) {
                case "number" -> value instanceof Number;
                case "integer" -> value instanceof Number n && n.doubleValue() == Math.rint(n.doubleValue());
                case "boolean" -> value instanceof Boolean;
                case "string" -> value instanceof String;
                case "array" -> value instanceof List<?>;
                case "object" -> value instanceof Map<?, ?>;
                default -> false;
            };
            if (!valid) throw invalid("算法配置类型无效：" + entry.getKey());
            if (spec.get("enum") instanceof List<?> choices && !choices.contains(value)) throw invalid("算法配置选项无效：" + entry.getKey());
            if (value instanceof Number n && (!Double.isFinite(n.doubleValue())
                    || n.doubleValue() < ((Number) spec.getOrDefault("minimum", -1e100)).doubleValue()
                    || n.doubleValue() > ((Number) spec.getOrDefault("maximum", 1e100)).doubleValue())) throw invalid("算法配置超出范围：" + entry.getKey());
            if (value instanceof List<?> list && list.size() < ((Number) spec.getOrDefault("minItems", 0)).intValue()) throw invalid("算法配置条目不足");
            if (value instanceof String s && s.length() > ((Number) spec.getOrDefault("maxLength", 4096)).intValue()) throw invalid("算法配置过长");
            if (value instanceof List<?> list && list.size() > ((Number) spec.getOrDefault("maxItems", 4096)).intValue()) throw invalid("算法配置条目过多");
            if (value instanceof Map<?, ?>) {
                var object = map(value); validateParameters(spec, object);
                if ("roi".equals(spec.get("x-widget"))) {
                    for (String field : List.of("x", "y", "width", "height")) if (!(object.get(field) instanceof Number)) throw invalid("识别区域坐标不完整");
                    double x = ((Number) object.get("x")).doubleValue(), y = ((Number) object.get("y")).doubleValue();
                    double w = ((Number) object.get("width")).doubleValue(), h = ((Number) object.get("height")).doubleValue();
                    if (w <= 0 || h <= 0 || x < 0 || y < 0 || x + w > 1 || y + h > 1) throw invalid("识别区域必须在画面内且面积大于零");
                }
            }
            if (value instanceof List<?> list && spec.containsKey("items")) {
                for (Object item : list) validateParameters(Map.of("properties", Map.of(entry.getKey(), spec.get("items"))), Collections.singletonMap(entry.getKey(), item));
            }
        }
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> map(Object value) {
        if (!(value instanceof Map<?, ?>)) throw invalid("算法描述必须是对象");
        return (Map<String, Object>) value;
    }

    private static void requireText(Map<String, Object> manifest, String key, String pattern) {
        if (!(manifest.get(key) instanceof String text) || !text.matches(pattern)) throw invalid("算法描述字段无效：" + key);
    }

    public static RuntimeException invalid(String reason) {
        return com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception(
                com.linsight.module.aivideo.enums.algorithm.ErrorCodeConstants.ALGORITHM_PACKAGE_INVALID, reason);
    }
}
