package com.linsight.module.aivideo.controller.admin.camera.vo;
import jakarta.validation.constraints.*;
import lombok.Data;
import java.util.List;
@Data
public class CameraDisplayPreferenceSaveReqVO {
 @NotNull @Positive private Long cameraId;
 @NotNull @Size(max=128) private List<@Pattern(regexp="(roi-)?(task|entry)-[0-9]+|recognition-regions") String> hiddenLayers;
}
