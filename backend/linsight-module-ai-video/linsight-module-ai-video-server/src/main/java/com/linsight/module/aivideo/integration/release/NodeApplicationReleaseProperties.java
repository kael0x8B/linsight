package com.linsight.module.aivideo.integration.release;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.nio.file.Files;
import java.nio.file.Path;

@Data
@Component
@ConfigurationProperties(prefix="linsight.ai-video.node-application-release")
public class NodeApplicationReleaseProperties {
    private boolean enabled;
    private String pythonExecutable = "python3";
    private String builderScript = "scripts/build-box-release.py";
    private String outputDirectory = "var/application-releases";
    /** Null uses the default private store; local simulator can use a dedicated download domain. */
    private Long storageConfigId;
    /** The platform publishes one shared application bundle; profiles remain for historical jobs. */
    private String defaultProfile;
    private Map<String, Profile> profiles = new LinkedHashMap<>();

    public String defaultProfileId() {
        if (defaultProfile != null && !defaultProfile.isBlank()) return defaultProfile;
        // Existing installations with one profile do not need a configuration migration.
        return profiles.size() == 1 ? profiles.keySet().iterator().next() : null;
    }

    @Data
    public static class Profile {
        private String label;
        private String architecture;
        private List<String> devices = List.of();
        private String pythonArchive;
        private String pythonSha256;
        private String wheelsDirectory;
        private String signingKey;
        private String keyId;
        private String minGlibc = "2.34";
    }

    /** Only server configuration can select executables, dependencies or signing keys. */
    public boolean ready(Profile p) {
        try {
            return enabled && p != null && p.getLabel() != null
                    && List.of("aarch64", "x86_64").contains(p.getArchitecture())
                    && !p.getDevices().isEmpty()
                    && p.getDevices().stream().allMatch(List.of("rk3566", "rk3568", "rk3588", "generic")::contains)
                    && p.getKeyId().matches("[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}")
                    && p.getPythonSha256().matches("[a-f0-9]{64}")
                    && p.getMinGlibc().matches("[0-9]+\\.[0-9]+")
                    && Files.isRegularFile(Path.of(builderScript))
                    && Files.isRegularFile(Path.of(p.getPythonArchive()))
                    && Files.isRegularFile(Path.of(p.getWheelsDirectory(), "manifest.json"))
                    && Files.isRegularFile(Path.of(p.getSigningKey()));
        } catch (RuntimeException error) { return false; }
    }
}
