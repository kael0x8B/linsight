package com.linsight.module.aivideo.service.node;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeApplicationReleaseCreateReqVO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeApplicationReleaseDO;
import com.linsight.module.aivideo.dal.mysql.node.NodeApplicationReleaseMapper;
import com.linsight.module.aivideo.integration.release.NodeApplicationReleaseProperties;
import com.linsight.module.infra.api.file.FileApi;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import cn.hutool.crypto.digest.DigestUtil;
import com.linsight.framework.common.util.json.JsonUtils;
import java.util.List;
import java.util.Objects;
import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_APPLICATION_RELEASE_ERROR;

@Service
public class NodeApplicationReleaseService {
    @Resource private NodeApplicationReleaseMapper mapper;
    @Resource private NodeApplicationReleaseProperties properties;
    @Resource private NodeOperationService operations;
    @Resource private FileApi fileApi;

    public record ProfileView(String id, String label, String architecture, List<String> devices, boolean ready) {}
    public List<ProfileView> profiles() {
        return properties.getProfiles().entrySet().stream().map(e -> new ProfileView(e.getKey(),
                e.getValue().getLabel(), e.getValue().getArchitecture(), e.getValue().getDevices(),
                properties.ready(e.getValue()))).toList();
    }
    public record BuildView(String label, String architecture, List<String> devices, boolean ready) {}
    public BuildView configuration() {
        var profile = properties.getProfiles().get(properties.defaultProfileId());
        return profile == null ? new BuildView("", "", List.of(), false)
                : new BuildView(profile.getLabel(), profile.getArchitecture(), profile.getDevices(), properties.ready(profile));
    }
    public static String digest(NodeApplicationReleaseProperties.Profile profile) {
        return DigestUtil.sha256Hex(JsonUtils.toJsonString(profile));
    }
    public Long create(NodeApplicationReleaseCreateReqVO request) {
        if (Boolean.FALSE.equals(request.getBackwardCompatible())) throw failure("当前仅支持数据格式向后兼容的应用升级");
        return operations.exclusive("application-release", () -> {
            var prior = mapper.selectOne(NodeApplicationReleaseDO::getRequestId, request.getRequestId());
            if (prior != null) {
                if ((request.getProfileId() != null && !Objects.equals(prior.getProfileId(), request.getProfileId()))
                        || !Objects.equals(prior.getVersion(), request.getVersion())
                        || !Objects.equals(prior.getNotes(), request.getNotes())) throw failure("重复请求的内容不一致");
                return prior.getId();
            }
            String profileId = request.getProfileId() != null ? request.getProfileId() : properties.defaultProfileId();
            var profile = properties.getProfiles().get(profileId);
            if (profile == null || !properties.ready(profile)) throw failure("升级包构建服务尚未就绪，请联系平台维护人员检查发布环境");
            if (mapper.selectCount(new LambdaQueryWrapper<NodeApplicationReleaseDO>()
                    .eq(NodeApplicationReleaseDO::getProfileId, profileId)
                    .eq(NodeApplicationReleaseDO::getVersion, request.getVersion())) > 0) {
                throw failure("该应用版本已有记录，请使用新版本号；失败记录可重试");
            }
            if (mapper.selectCount(new LambdaQueryWrapper<NodeApplicationReleaseDO>()
                    .in(NodeApplicationReleaseDO::getStatus, "QUEUED", "BUILDING", "STORING")) >= 20) {
                throw failure("等待构建的任务过多，请稍后重试");
            }
            var row = new NodeApplicationReleaseDO();
            row.setRequestId(request.getRequestId()); row.setProfileId(profileId);
            row.setProfileLabel(profile.getLabel()); row.setProfileDigest(digest(profile));
            row.setArchitecture(profile.getArchitecture()); row.setDevices(String.join(",", profile.getDevices()));
            row.setKeyId(profile.getKeyId()); row.setVersion(request.getVersion()); row.setNotes(request.getNotes());
            row.setStatus("QUEUED"); row.setMessage("等待构建"); row.setAttempt(1);
            mapper.insert(row); return row.getId();
        });
    }
    public void retry(Long id) {
        operations.exclusive("application-release", () -> {
            var row = get(id);
            var profile = properties.getProfiles().get(row.getProfileId());
            if (!properties.ready(profile) || !digest(profile).equals(row.getProfileDigest())) {
                throw failure("原构建配置已变更或未就绪，请联系平台维护人员恢复配置或使用新版本号");
            }
            if (!"FAILED".equals(row.getStatus())) throw failure("只能重试失败任务");
            mapper.update(null, new LambdaUpdateWrapper<NodeApplicationReleaseDO>()
                    .eq(NodeApplicationReleaseDO::getId, id).eq(NodeApplicationReleaseDO::getStatus, "FAILED")
                    .set(NodeApplicationReleaseDO::getStatus, "QUEUED")
                    .set(NodeApplicationReleaseDO::getMessage, "等待重新构建")
                    .set(NodeApplicationReleaseDO::getFinishTime, null)
                    .set(NodeApplicationReleaseDO::getAttempt, row.getAttempt() + 1));
            return null;
        });
    }
    public NodeApplicationReleaseDO get(Long id) {
        var row = mapper.selectById(id);
        if (row == null) throw failure("升级包记录不存在");
        return row;
    }
    public PageResult<NodeApplicationReleaseDO> page(PageParam page) { return mapper.page(page); }
    public String download(Long id, String artifact) {
        var row = get(id);
        if (!"SUCCEEDED".equals(row.getStatus())) throw failure("升级包尚未完成，不能下载");
        Long fileId = switch (artifact) {
            case "bundle" -> row.getBundleFileId();
            case "bootstrap" -> row.getBootstrapFileId();
            case "public-key" -> row.getPublicKeyFileId();
            default -> throw failure("未知的制品类型");
        };
        return fileApi.presignRegisteredFile(fileId, 60);
    }
    private static RuntimeException failure(String message) {
        return exception(NODE_APPLICATION_RELEASE_ERROR, message);
    }
}
