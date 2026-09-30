package com.linsight.module.aivideo.service.model;

import com.linsight.module.aivideo.service.node.NodeExecutionProviderDTO;
import com.linsight.module.aivideo.service.node.NodeModelEnvironmentDTO;

import java.math.BigInteger;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Shared deployment gate for model, algorithm-package and built-in pipeline entry points. */
public final class ModelDeploymentCompatibility {
    private static final Set<String> DEVICE_SPECIFIC_FORMATS = Set.of("RKNN", "TENSORRT");

    private ModelDeploymentCompatibility() {}

    public record ExecutionRequirement(
            String provider,
            String target,
            String runtime,
            String minimumRuntimeVersion,
            boolean deviceSpecific,
            boolean targetRequired) {}

    /** Do not infer an accelerator target from an asset name, CPU architecture or utilization. */
    public static String deploymentBlocker(String format, Map<String, Object> manifest,
            NodeModelEnvironmentDTO environment, boolean installed) {
        var decoder = manifest.get("decoder") instanceof Map<?, ?> value ? value : Map.of();
        var requirement = executionRequirement(format, manifest);
        if (environment == null || !environment.reported()) {
            // Older runtimes include the ONNX CPU backend. A READY receipt proves an existing install.
            boolean legacyOnnx = "ONNX".equals(format)
                    && (requirement.provider() == null || "onnxruntime".equals(requirement.provider()))
                    && requirement.target() == null && requirement.minimumRuntimeVersion() == null;
            return installed || legacyOnnx ? "" : "网关尚未上报运行环境，请先在线升级后重试";
        }
        boolean supportsFormat = environment.formats().contains(format)
                || environment.providers().stream().anyMatch(provider -> provider.formats().contains(format));
        if (!supportsFormat) return "网关运行环境不支持此模型格式";
        if ("ARCHIVE".equals(format) && !installed
                && !Set.of("FACE_PAIR_SFACE", "FACE_PAIR_SFACE_RKNN")
                        .contains(String.valueOf(decoder.get("type")))
                && requirement.provider() == null) {
            return "模型包的运行依赖尚未确认，请联系管理员先验证目标网关适配";
        }
        if (requirement.provider() == null) {
            if (requirement.deviceSpecific()) {
                return installed ? "" : "模型尚未声明执行后端，请联系管理员补齐适配版本";
            }
            return "";
        }
        List<NodeExecutionProviderDTO> providers = environment.providers().stream()
                .filter(provider -> requirement.provider().equals(provider.code())).toList();
        if (providers.isEmpty()) return "网关不支持模型要求的执行后端 " + requirement.provider();
        providers = providers.stream().filter(provider -> provider.formats().contains(format)).toList();
        if (providers.isEmpty()) return "网关执行后端不支持此模型格式";
        if (requirement.target() == null && requirement.targetRequired()) {
            return installed ? "" : "模型尚未声明适用目标，请联系管理员补齐适配版本";
        }
        if (requirement.target() != null) {
            providers = providers.stream()
                    .filter(provider -> provider.targets().contains(requirement.target())).toList();
            if (providers.isEmpty()) return "模型适用目标与当前网关不匹配";
        }
        if (requirement.runtime() != null) {
            providers = providers.stream()
                    .filter(provider -> requirement.runtime().equals(provider.runtime())).toList();
            if (providers.isEmpty()) return "网关执行后端的运行库与模型要求不匹配";
        }
        if (requirement.minimumRuntimeVersion() != null) {
            if (providers.stream().noneMatch(provider -> provider.runtimeVersion() != null)) {
                return installed ? "" : "网关尚未上报执行后端版本，请先在线升级后重试";
            }
            if (providers.stream().noneMatch(provider -> versionAtLeast(
                    provider.runtimeVersion(), requirement.minimumRuntimeVersion()))) {
                return installed ? "" : "网关执行后端版本低于模型要求";
            }
        }
        return "";
    }

    public static ExecutionRequirement executionRequirement(String format, Map<String, Object> manifest) {
        Map<?, ?> execution = manifest.get("execution") instanceof Map<?, ?> value ? value : Map.of();
        String provider = stringValue(execution.get("provider"));
        String target = stringValue(execution.get("target"));
        if (target == null) target = stringValue(manifest.get("targetPlatform"));
        String runtime = stringValue(execution.get("runtime"));
        String minimumRuntimeVersion = stringValue(execution.get("minRuntimeVersion"));
        var decoder = manifest.get("decoder") instanceof Map<?, ?> value ? value : Map.of();
        boolean legacyRknpu = "RKNN".equals(format)
                || "FACE_PAIR_SFACE_RKNN".equals(decoder.get("type"));
        if (provider == null && legacyRknpu) provider = "rknpu2";
        if (runtime == null && legacyRknpu) runtime = "rknn-toolkit-lite2";
        boolean deviceSpecific = DEVICE_SPECIFIC_FORMATS.contains(format) || legacyRknpu;
        boolean targetRequired = deviceSpecific || "rknpu2".equals(provider);
        return new ExecutionRequirement(provider, target, runtime, minimumRuntimeVersion,
                deviceSpecific, targetRequired);
    }

    private static String stringValue(Object value) {
        return value instanceof String text && !text.isBlank() ? text : null;
    }

    private static boolean versionAtLeast(String actual, String required) {
        if (Objects.equals(actual, required)) return true;
        List<BigInteger> actualParts = numericVersion(actual);
        List<BigInteger> requiredParts = numericVersion(required);
        if (actualParts.isEmpty() || requiredParts.isEmpty()) return false;
        int length = Math.max(actualParts.size(), requiredParts.size());
        for (int index = 0; index < length; index++) {
            var left = index < actualParts.size() ? actualParts.get(index) : BigInteger.ZERO;
            var right = index < requiredParts.size() ? requiredParts.get(index) : BigInteger.ZERO;
            int compared = left.compareTo(right);
            if (compared != 0) return compared > 0;
        }
        // A prerelease never satisfies the same stable minimum version.
        return !actual.contains("-") || required.contains("-");
    }

    private static List<BigInteger> numericVersion(String value) {
        if (value == null || !value.matches("[0-9]+(?:\\.[0-9]+)*(?:[-+][0-9A-Za-z._-]+)?")) {
            return List.of();
        }
        String numeric = value.split("[-+]", 2)[0];
        return Arrays.stream(numeric.split("\\."))
                .map(BigInteger::new).toList();
    }
}
