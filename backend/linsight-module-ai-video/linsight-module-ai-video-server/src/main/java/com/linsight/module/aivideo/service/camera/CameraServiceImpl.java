package com.linsight.module.aivideo.service.camera;

import cn.hutool.core.util.StrUtil;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraPageReqVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;
import com.linsight.module.aivideo.dal.mysql.camera.CameraMapper;
import com.linsight.module.aivideo.enums.camera.CameraProtocolEnum;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import java.net.URLEncoder;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.camera.ErrorCodeConstants.*;

@Service
@Validated
public class CameraServiceImpl implements CameraService {

    private static final String CREDENTIAL_KEY_VERSION = "mybatis-plus-aes-v1";
    private static final int ONLINE_STATUS_UNKNOWN = 0;

    @Resource
    private CameraMapper cameraMapper;
    @Resource
    private CameraGroupService cameraGroupService;

    @Override
    public java.util.Map<Long, String> getCameraNames(java.util.Collection<Long> ids) {
        if (ids == null || ids.isEmpty()) return java.util.Map.of();
        return cameraMapper.selectByIds(ids).stream().collect(java.util.stream.Collectors.toMap(
                CameraDO::getId, CameraDO::getName));
    }

    @Override
    public Long createCamera(CameraSaveReqVO createReqVO) {
        validateProtocol(createReqVO.getProtocol());
        validateGroup(createReqVO.getGroupId());
        validateCodeUnique(null, createReqVO.getCode());
        if (StrUtil.isBlank(createReqVO.getMainStreamUri())) {
            throw exception(CAMERA_MAIN_STREAM_REQUIRED);
        }
        CameraDO camera = BeanUtils.toBean(createReqVO, CameraDO.class);
        camera.setGroupId(normalizeGroupId(createReqVO.getGroupId()));
        camera.setCredentialKeyVersion(CREDENTIAL_KEY_VERSION);
        camera.setOnlineStatus(ONLINE_STATUS_UNKNOWN);
        camera.setVersion(1);
        cameraMapper.insert(camera);
        return camera.getId();
    }

    @Override
    public void updateCamera(CameraSaveReqVO updateReqVO) {
        CameraDO current = validateExists(updateReqVO.getId());
        validateProtocol(updateReqVO.getProtocol());
        validateGroup(updateReqVO.getGroupId());
        validateCodeUnique(updateReqVO.getId(), updateReqVO.getCode());

        CameraDO update = BeanUtils.toBean(updateReqVO, CameraDO.class);
        update.setGroupId(normalizeGroupId(updateReqVO.getGroupId()));
        update.setCredentialKeyVersion(CREDENTIAL_KEY_VERSION);
        update.setVersion(current.getVersion());
        preserveBlankSecrets(update);
        cameraMapper.updateById(update);
    }

    @Override
    public void deleteCamera(Long id) {
        validateExists(id);
        cameraMapper.deleteById(id);
    }

    @Override
    public CameraDO getCamera(Long id) {
        return validateExists(id);
    }

    @Override
    public PageResult<CameraDO> getCameraPage(CameraPageReqVO pageReqVO) {
        if (pageReqVO.getIds() != null) {
            var rows = cameraMapper.selectBatchIds(pageReqVO.getIds());
            return new PageResult<>(rows, (long) rows.size());
        }
        return cameraMapper.selectPage(pageReqVO, pageReqVO.getName(), pageReqVO.getCode(),
                pageReqVO.getGroupId(), pageReqVO.getProtocol(), pageReqVO.getOnlineStatus(), pageReqVO.getStatus());
    }

    @Override
    public String getRuntimeStreamUrl(Long id, String streamType) {
        CameraDO camera = validateExists(id);
        String streamUri = Objects.equals(streamType, "SUB") ? camera.getSubStreamUri() : camera.getMainStreamUri();
        if (StrUtil.isBlank(streamUri)) {
            throw exception(CAMERA_PREVIEW_STREAM_NOT_CONFIGURED);
        }
        String pathAndQuery = normalizePathAndQuery(streamUri);
        String userInfo = "";
        if (StrUtil.isNotBlank(camera.getUsername())) {
            userInfo = encodeUserInfo(camera.getUsername());
            if (camera.getPassword() != null) {
                userInfo += ":" + encodeUserInfo(camera.getPassword());
            }
            userInfo += "@";
        }
        String host = camera.getHost().contains(":") && !camera.getHost().startsWith("[")
                ? "[" + camera.getHost() + "]" : camera.getHost();
        return "rtsp://" + userInfo + host + ":" + camera.getPort() + pathAndQuery;
    }

    private CameraDO validateExists(Long id) {
        if (id == null) {
            throw exception(CAMERA_NOT_FOUND);
        }
        CameraDO camera = cameraMapper.selectById(id);
        if (camera == null) {
            throw exception(CAMERA_NOT_FOUND);
        }
        return camera;
    }

    private void validateCodeUnique(Long id, String code) {
        CameraDO sameCode = cameraMapper.selectByCode(code);
        if (sameCode != null && !Objects.equals(sameCode.getId(), id)) {
            throw exception(CAMERA_CODE_DUPLICATE);
        }
    }

    private void validateGroup(Long groupId) {
        if (groupId != null && groupId > 0) {
            cameraGroupService.getCameraGroup(groupId);
        }
    }

    private static void validateProtocol(String protocol) {
        if (!CameraProtocolEnum.contains(protocol)) {
            throw exception(CAMERA_PROTOCOL_INVALID);
        }
    }

    private static Long normalizeGroupId(Long groupId) {
        return groupId == null ? CameraGroupDOConstants.UNGROUPED_ID : groupId;
    }

    private static void preserveBlankSecrets(CameraDO update) {
        if (StrUtil.isBlank(update.getMainStreamUri())) {
            update.setMainStreamUri(null);
        }
        if (StrUtil.isBlank(update.getSubStreamUri())) {
            update.setSubStreamUri(null);
        }
        if (StrUtil.isBlank(update.getUsername())) {
            update.setUsername(null);
        }
        if (StrUtil.isBlank(update.getPassword())) {
            update.setPassword(null);
        }
    }

    private static String encodeUserInfo(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
    }

    private static String normalizePathAndQuery(String streamUri) {
        if (!streamUri.contains("://")) {
            return "/" + StrUtil.removePrefix(streamUri, "/");
        }
        URI uri = URI.create(streamUri);
        String path = StrUtil.blankToDefault(uri.getRawPath(), "/");
        return uri.getRawQuery() == null ? path : path + "?" + uri.getRawQuery();
    }

    private static final class CameraGroupDOConstants {
        private static final Long UNGROUPED_ID = 0L;

        private CameraGroupDOConstants() {
        }
    }

}
