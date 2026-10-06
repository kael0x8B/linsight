package com.linsight.module.aivideo.service.node;

import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.linsight.framework.tenant.core.util.TenantUtils;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.dal.dataobject.node.NodeApplicationReleaseDO;
import com.linsight.module.aivideo.dal.mysql.node.NodeApplicationReleaseMapper;
import com.linsight.module.aivideo.integration.release.NodeApplicationReleaseProperties;
import com.linsight.module.aivideo.integration.ssh.NodeDeploymentProperties;
import com.linsight.module.infra.api.file.FileApi;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** MySQL is the queue; a lease fences late workers after a restart or connection loss. */
@Service
@Slf4j
public class NodeApplicationReleaseWorker {
    @Resource private NodeApplicationReleaseMapper mapper;
    @Resource private NodeApplicationReleaseProperties properties;
    @Resource private NodeDeploymentProperties deploymentProperties;
    @Resource private FileApi fileApi;
    @Resource(name="nodeApplicationReleaseExecutor") private ThreadPoolTaskExecutor executor;
    private final String owner = UUID.randomUUID().toString();
    private final AtomicReference<NodeApplicationReleaseDO> active = new AtomicReference<>();

    @Scheduled(fixedDelay=10000, initialDelay=15000, scheduler="nodeApplicationReleaseScheduler")
    public void tick() {
        var running = active.get();
        if (running != null) {
            TenantUtils.execute(running.getTenantId(), () -> mapper.heartbeat(running.getId(), owner));
            return;
        }
        if (!properties.isEnabled()) return;
        mapper.expireLeases();
        for (var candidate : mapper.queued()) {
            if (!active.compareAndSet(null, candidate)) return;
            try {
                boolean claimed = TenantUtils.execute(candidate.getTenantId(), () -> mapper.claim(candidate.getId(), owner) == 1);
                if (!claimed) { active.compareAndSet(candidate, null); continue; }
                executor.execute(() -> {
                    try { TenantUtils.execute(candidate.getTenantId(), () -> build(candidate)); }
                    finally { active.compareAndSet(candidate, null); }
                });
                return;
            } catch (RuntimeException error) {
                active.compareAndSet(candidate, null);
                // A claimed job remains durable and will expire if the executor could not accept it.
                log.warn("Application release scheduling failed, job={}", candidate.getId());
                return;
            }
        }
    }

    private void build(NodeApplicationReleaseDO row) {
        Path work = null;
        Process process = null;
        String stage = "BUILDING";
        try {
            var profile = properties.getProfiles().get(row.getProfileId());
            if (!properties.ready(profile) || !NodeApplicationReleaseService.digest(profile).equals(row.getProfileDigest())) {
                fail(row, "原构建配置未就绪或已变更，请联系平台维护人员检查发布环境"); return;
            }
            Path root = Path.of(properties.getOutputDirectory()).toAbsolutePath().normalize();
            Files.createDirectories(root);
            if (Files.getFileStore(root).getUsableSpace() < 2L * 1024 * 1024 * 1024) {
                fail(row, "构建服务器临时空间不足 2 GiB，请清理后重试"); return;
            }
            work = Files.createTempDirectory(root, "release-" + row.getId() + "-");
            Path result = work.resolve("result.json");
            Path notes = work.resolve("notes.txt");
            Files.writeString(notes, row.getNotes());
            var command = new ArrayList<>(List.of(properties.getPythonExecutable(), properties.getBuilderScript(),
                    "--runtime", deploymentProperties.resolveRuntimeSource().toString(),
                    "--version", row.getVersion(), "--arch", profile.getArchitecture(),
                    "--python", profile.getPythonArchive(), "--python-sha256", profile.getPythonSha256(),
                    "--wheels", profile.getWheelsDirectory(), "--key-id", profile.getKeyId(),
                    "--signing-key", profile.getSigningKey(), "--min-glibc", profile.getMinGlibc(),
                    "--notes", notes.toString(), "--backward-compatible", "--output", work.toString(),
                    "--result-file", result.toString(), "--devices"));
            command.addAll(profile.getDevices());
            process = new ProcessBuilder(command).redirectOutput(ProcessBuilder.Redirect.DISCARD)
                    .redirectError(ProcessBuilder.Redirect.DISCARD).start();
            long deadline = System.nanoTime() + TimeUnit.MINUTES.toNanos(20);
            while (!process.waitFor(10, TimeUnit.SECONDS)) {
                if (System.nanoTime() > deadline) throw new IllegalStateException("Build timeout");
                if (mapper.heartbeat(row.getId(), owner) != 1) throw new IllegalStateException("Build lease lost");
            }
            if (process.exitValue() != 0) {
                fail(row, "制品校验或打包失败：请检查 Python 摘要、离线依赖、网页制品和签名密钥"); return;
            }
            BuildResult built = JsonUtils.parseObject(Files.readString(result), BuildResult.class);
            String expected = "linsight-box-" + row.getVersion() + "-" + row.getArchitecture() + ".lup";
            if (built == null || !expected.equals(built.fileName()) || !row.getKeyId().equals(built.keyId())
                    || !isDigest(built.sha256()) || !isDigest(built.sourceSha256()) || !isDigest(built.bootstrapSha256())) {
                throw new IllegalStateException("Invalid build result");
            }
            Path bundle = work.resolve(expected);
            if (Files.size(bundle) != built.size()) throw new IllegalStateException("Artifact changed");
            stage = "STORING";
            if (mapper.update(null, owned(row).set(NodeApplicationReleaseDO::getStatus, stage)
                    .set(NodeApplicationReleaseDO::getMessage, "签名和完整性校验通过，正在保存制品")) != 1) {
                throw new IllegalStateException("Build lease lost");
            }
            // Unique object set also prevents collisions when isolated databases share one bucket.
            String directory = "node-releases/" + row.getTenantId() + "/" + row.getId() + "/" + row.getAttempt()
                    + "/" + UUID.randomUUID();
            Long bundleId = fileApi.createFileFromPath(bundle, expected, directory, "application/octet-stream", properties.getStorageConfigId());
            Long bootstrapId = fileApi.createFileFromPath(work.resolve("linsight-bootstrap.pyz"),
                    "linsight-bootstrap.pyz", directory, "application/octet-stream", properties.getStorageConfigId());
            Long keyId = fileApi.createFileFromPath(work.resolve("release-public.pem"),
                    "release-public.pem", directory, "application/x-pem-file", properties.getStorageConfigId());
            mapper.update(null, owned(row).set(NodeApplicationReleaseDO::getStatus, "SUCCEEDED")
                    .set(NodeApplicationReleaseDO::getMessage, "升级包已生成，可下载后用于盒子应用升级")
                    .set(NodeApplicationReleaseDO::getBundleFileId, bundleId)
                    .set(NodeApplicationReleaseDO::getBootstrapFileId, bootstrapId)
                    .set(NodeApplicationReleaseDO::getPublicKeyFileId, keyId)
                    .set(NodeApplicationReleaseDO::getFileName, expected).set(NodeApplicationReleaseDO::getSize, built.size())
                    .set(NodeApplicationReleaseDO::getSha256, built.sha256())
                    .set(NodeApplicationReleaseDO::getBootstrapSha256, built.bootstrapSha256())
                    .set(NodeApplicationReleaseDO::getSourceSha256, built.sourceSha256())
                    .set(NodeApplicationReleaseDO::getFinishTime, LocalDateTime.now()));
        } catch (Exception error) {
            if (error instanceof InterruptedException) Thread.currentThread().interrupt();
            log.warn("Application release failed: job={}, stage={}, errorType={}", row.getId(), stage, error.getClass().getSimpleName());
            fail(row, "STORING".equals(stage) ? "制品保存失败，请检查文件存储连接及权限后重试"
                    : "构建失败或中断，请检查服务器构建环境后重试");
        } finally {
            if (process != null && process.isAlive()) {
                process.destroyForcibly();
                try { process.waitFor(5, TimeUnit.SECONDS); }
                catch (InterruptedException ignored) { Thread.currentThread().interrupt(); }
            }
            if (work != null) {
                try (var paths = Files.walk(work)) {
                    for (var path : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
                } catch (Exception error) { log.warn("Application release temporary cleanup failed: job={}", row.getId()); }
            }
        }
    }
    private LambdaUpdateWrapper<NodeApplicationReleaseDO> owned(NodeApplicationReleaseDO row) {
        return new LambdaUpdateWrapper<NodeApplicationReleaseDO>().eq(NodeApplicationReleaseDO::getId, row.getId())
                .eq(NodeApplicationReleaseDO::getExecutorOwner, owner)
                .in(NodeApplicationReleaseDO::getStatus, "BUILDING", "STORING")
                .apply("lease_until > NOW()");
    }
    private void fail(NodeApplicationReleaseDO row, String message) {
        mapper.update(null, owned(row).set(NodeApplicationReleaseDO::getStatus, "FAILED")
                .set(NodeApplicationReleaseDO::getMessage, message).set(NodeApplicationReleaseDO::getFinishTime, LocalDateTime.now()));
    }
    private static boolean isDigest(String value) { return value != null && value.matches("[a-f0-9]{64}"); }
    public record BuildResult(String fileName, long size, String sha256, String bootstrapSha256, String sourceSha256, String keyId) {}
}
