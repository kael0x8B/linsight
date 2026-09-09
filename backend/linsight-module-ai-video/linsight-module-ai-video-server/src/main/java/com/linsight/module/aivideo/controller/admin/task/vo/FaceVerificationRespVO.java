package com.linsight.module.aivideo.controller.admin.task.vo;
import lombok.Data;
import java.util.Map;
@Data
public class FaceVerificationRespVO {
    private Long id;
    private String status;
    private Map<String, Object> result;
}
