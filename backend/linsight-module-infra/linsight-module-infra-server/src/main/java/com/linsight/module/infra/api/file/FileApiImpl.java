package com.linsight.module.infra.api.file;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.infra.api.file.dto.FileCreateReqDTO;
import com.linsight.module.infra.service.file.FileService;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.RestController;

import jakarta.annotation.Resource;

import static com.linsight.framework.common.pojo.CommonResult.success;

@RestController // 提供 RESTful API 接口，给 Feign 调用
@Validated
public class FileApiImpl implements FileApi {

    @Resource
    private FileService fileService;

    @Override
    public Long createFileFromPath(java.nio.file.Path source, String name, String directory, String type) {
        return fileService.createFileFromPath(source, name, directory, type);
    }

    @Override
    public Long createFileFromPath(java.nio.file.Path source, String name, String directory, String type, Long configId) {
        return fileService.createFileFromPath(source, name, directory, type, configId);
    }

    @Override
    public String presignRegisteredFile(Long id, int seconds) {
        return fileService.presignGetUrl(fileService.getFile(id).getUrl(), seconds);
    }

    @Override
    public CommonResult<byte[]> readRegisteredImage(String url) {
        return success(fileService.readRegisteredImage(url));
    }

    @Override
    public CommonResult<String> createFile(FileCreateReqDTO createReqDTO) {
        return success(fileService.createFile(createReqDTO.getContent(), createReqDTO.getName(),
                createReqDTO.getDirectory(), createReqDTO.getType()));
    }

    @Override
    public CommonResult<String> presignGetUrl(String url, Integer expirationSeconds) {
        return success(fileService.presignGetUrl(url, expirationSeconds));
    }

}
