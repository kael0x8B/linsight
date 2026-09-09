package com.linsight.module.aivideo.service.camera;

import com.baomidou.mybatisplus.annotation.TableField;
import com.linsight.framework.mybatis.core.type.EncryptTypeHandler;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraRespVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class CameraCredentialContractTest {

    private static final Set<String> SECRET_FIELDS = Set.of(
            "mainStreamUri", "subStreamUri", "username", "password", "credentialKeyVersion");

    @Test
    void persistentSecretsMustUseEstablishedEncryptTypeHandler() throws NoSuchFieldException {
        for (String fieldName : Set.of("mainStreamUri", "subStreamUri", "username", "password")) {
            Field field = CameraDO.class.getDeclaredField(fieldName);
            TableField annotation = field.getAnnotation(TableField.class);
            assertEquals(EncryptTypeHandler.class, annotation.typeHandler(), fieldName);
        }
    }

    @Test
    void adminResponseMustNotDeclareSecretFields() {
        for (Field field : CameraRespVO.class.getDeclaredFields()) {
            assertFalse(SECRET_FIELDS.contains(field.getName()), field.getName());
        }
    }

    @Test
    void secretCarriersMustExcludeValuesFromToString() {
        CameraDO camera = new CameraDO();
        camera.setMainStreamUri("/private/path");
        camera.setUsername("operator");
        camera.setPassword("secret-password");
        CameraSaveReqVO request = new CameraSaveReqVO();
        request.setMainStreamUri("/private/path");
        request.setPassword("secret-password");

        assertFalse(camera.toString().contains("secret-password"));
        assertFalse(camera.toString().contains("/private/path"));
        assertFalse(request.toString().contains("secret-password"));
        assertFalse(request.toString().contains("/private/path"));
    }

}
