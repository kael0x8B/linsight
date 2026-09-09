package com.linsight.module.aivideo.architecture;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertTrue;

class AiVideoArchitectureTest {

    private static final Pattern IMPORT_PATTERN = Pattern.compile("^import\\s+([\\w.]+);", Pattern.MULTILINE);
    private static final Pattern DAL_DOMAIN_PATTERN = Pattern.compile(
            "com\\.linsight\\.module\\.aivideo\\.dal\\.(?:dataobject|mysql|redis)\\.([a-z]+)\\.");
    private static final Pattern ADMIN_MAPPING_PATTERN = Pattern.compile(
            "@(Get|Post|Put|Delete|Patch)Mapping(?:\\([^\\n]*\\))?");
    private static final String PERMISSION_CALL = "@ss\\.has(?:Permission|AnyPermissions)\\((?:'ai-video:[^']+'(?:,\\s*)?)+\\)";
    private static final Pattern PRE_AUTHORIZE_PATTERN = Pattern.compile(
            "@PreAuthorize\\(\"" + PERMISSION_CALL + "(?:\\s+and\\s+" + PERMISSION_CALL + ")*\"\\)");

    @Test void compoundPermissionsKeepEveryRequiredCheck() {
        assertTrue(PRE_AUTHORIZE_PATTERN.matcher("@PreAuthorize(\"@ss.hasPermission('ai-video:task:start') and @ss.hasPermission('ai-video:library:query')\")").matches());
        assertTrue(!PRE_AUTHORIZE_PATTERN.matcher("@PreAuthorize(\"@ss.hasPermission('ai-video:task:start') or true\")").matches());
    }
    private static final Set<String> DOMAINS = Set.of(
            "camera", "model", "algorithm", "task", "rule", "event", "node", "integration");

    @Test
    void controllersMustNotDependOnDal() throws IOException {
        assertNoForbiddenImports(serverSource("controller"), List.of("com.linsight.module.aivideo.dal."));
    }

    @Test
    void mappersMustNotDependOnUpperLayers() throws IOException {
        assertNoForbiddenImports(serverSource("dal/mysql"), List.of(
                "com.linsight.module.aivideo.controller.",
                "com.linsight.module.aivideo.service."));
    }

    @Test
    void domainDalMustRemainIsolated() throws IOException {
        List<String> violations = new ArrayList<>();
        for (Path source : javaSources(serverSource("dal"))) {
            String content = Files.readString(source);
            String owner = domainFromPath(source);
            if (owner == null) {
                continue;
            }
            Matcher matcher = IMPORT_PATTERN.matcher(content);
            while (matcher.find()) {
                Matcher domainMatcher = DAL_DOMAIN_PATTERN.matcher(matcher.group(1) + ".");
                if (domainMatcher.find() && !owner.equals(domainMatcher.group(1))) {
                    violations.add(source + " imports another domain DAL: " + matcher.group(1));
                }
            }
        }
        assertTrue(violations.isEmpty(), String.join(System.lineSeparator(), violations));
    }

    @Test
    void apiModuleMustContainContractsOnly() throws IOException {
        Path apiSource = serverRoot().resolveSibling("linsight-module-ai-video-api/src/main/java");
        List<String> forbidden = List.of(".controller.", ".service.", ".dal.", ".framework.",
                "Controller.java", "ServiceImpl.java", "Mapper.java", "DO.java");
        List<String> violations = new ArrayList<>();
        for (Path source : javaSources(apiSource)) {
            String normalized = source.toString().replace('\\', '/');
            for (String token : forbidden) {
                if (normalized.contains(token)) {
                    violations.add(source + " contains server implementation token: " + token);
                }
            }
        }
        assertTrue(violations.isEmpty(), String.join(System.lineSeparator(), violations));
    }

    @Test
    void systemAndInfraMustNotDependOnAiVideo() throws IOException {
        Path backendRoot = serverRoot().getParent().getParent();
        assertNoForbiddenImports(backendRoot.resolve(
                        "linsight-module-system/linsight-module-system-server/src/main/java"),
                List.of("com.linsight.module.aivideo."));
        assertNoForbiddenImports(backendRoot.resolve(
                        "linsight-module-infra/linsight-module-infra-server/src/main/java"),
                List.of("com.linsight.module.aivideo."));
    }

    @Test
    void everyAdminEndpointMustDeclareAiVideoPermission() throws IOException {
        List<String> violations = new ArrayList<>();
        for (Path source : javaSources(serverSource("controller/admin"))) {
            if (!source.getFileName().toString().endsWith("Controller.java")) continue;
            String content = Files.readString(source);
            long mappings = ADMIN_MAPPING_PATTERN.matcher(content).results().count();
            long permissions = PRE_AUTHORIZE_PATTERN.matcher(content).results().count();
            if (mappings != permissions) {
                violations.add(source + " endpointMappings=" + mappings + ", aiVideoPermissions=" + permissions);
            }
        }
        assertTrue(violations.isEmpty(), String.join(System.lineSeparator(), violations));
    }

    @Test
    void nodeControllersMustNotRepeatFrameworkApiPrefix() throws IOException {
        List<String> violations = new ArrayList<>();
        for (Path source : javaSources(serverSource("controller/node"))) {
            if (!source.getFileName().toString().endsWith("Controller.java")) continue;
            String content = Files.readString(source);
            if (content.contains("@RequestMapping(\"/node-api")) {
                violations.add(source + " repeats the framework-managed /node-api prefix");
            }
        }
        assertTrue(violations.isEmpty(), String.join(System.lineSeparator(), violations));
    }

    @Test
    void everyBusinessDataObjectMustUseTenantBase() throws IOException {
        List<String> violations = new ArrayList<>();
        for (Path source : javaSources(serverSource("dal/dataobject"))) {
            if (!source.getFileName().toString().endsWith("DO.java")) continue;
            String content = Files.readString(source);
            if (!content.contains("extends TenantBaseDO")) {
                violations.add(source + " does not extend TenantBaseDO");
            }
        }
        assertTrue(violations.isEmpty(), String.join(System.lineSeparator(), violations));
    }

    private static void assertNoForbiddenImports(Path sourceRoot, List<String> forbiddenImports) throws IOException {
        List<String> violations = new ArrayList<>();
        for (Path source : javaSources(sourceRoot)) {
            String content = Files.readString(source);
            Matcher matcher = IMPORT_PATTERN.matcher(content);
            while (matcher.find()) {
                String importedType = matcher.group(1);
                for (String forbiddenImport : forbiddenImports) {
                    if (importedType.startsWith(forbiddenImport)) {
                        violations.add(source + " imports " + importedType);
                    }
                }
            }
        }
        assertTrue(violations.isEmpty(), String.join(System.lineSeparator(), violations));
    }

    private static List<Path> javaSources(Path sourceRoot) throws IOException {
        if (!Files.isDirectory(sourceRoot)) {
            return List.of();
        }
        try (Stream<Path> paths = Files.walk(sourceRoot)) {
            return paths.filter(path -> path.toString().endsWith(".java")).toList();
        }
    }

    private static String domainFromPath(Path source) {
        for (Path part : source) {
            String name = part.toString();
            if (DOMAINS.contains(name)) {
                return name;
            }
        }
        return null;
    }

    private static Path serverSource(String relativePath) {
        return serverRoot().resolve("src/main/java/com/linsight/module/aivideo").resolve(relativePath);
    }

    private static Path serverRoot() {
        return Path.of(System.getProperty("aivideo.server.basedir", ".")).toAbsolutePath().normalize();
    }

}
