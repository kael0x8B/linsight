package com.linsight.module.aivideo.convert.camera;

import cn.hutool.core.util.StrUtil;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraRespVO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;
import org.mapstruct.Mapper;
import org.mapstruct.factory.Mappers;

import java.util.List;

/**
 * 摄像头安全响应转换器。
 *
 * <p>只构造管理端允许看到的字段，避免码流路径和访问凭据进入响应对象。</p>
 */
@Mapper
public interface CameraConvert {

    CameraConvert INSTANCE = Mappers.getMapper(CameraConvert.class);

    default CameraRespVO convert(CameraDO camera) {
        if (camera == null) {
            return null;
        }
        CameraRespVO response = BeanUtils.toBean(camera, CameraRespVO.class);
        response.setMaskedStreamEndpoint(camera.getProtocol().toLowerCase() + "://" + camera.getHost()
                + ":" + camera.getPort() + "/***");
        response.setCredentialConfigured(StrUtil.isNotBlank(camera.getUsername())
                || StrUtil.isNotBlank(camera.getPassword()));
        return response;
    }

    default PageResult<CameraRespVO> convertPage(PageResult<CameraDO> page) {
        List<CameraRespVO> list = page.getList().stream().map(this::convert).toList();
        return new PageResult<>(list, page.getTotal());
    }

}
