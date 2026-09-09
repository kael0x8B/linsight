package com.linsight.module.aivideo.controller.node.node;

import com.linsight.module.aivideo.controller.node.node.vo.NodeCommandReportReqVO;
import jakarta.validation.Validation;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class NodeDependencyStageContractTest {
    @Test
    void acceptsPreparationProgressAndRejectsUnknownStages() {
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var request = new NodeCommandReportReqVO();
            request.setCommandId("11111111-1111-1111-1111-111111111111");
            request.setStatus("RUNNING");
            for (String stage : List.of("CHECKING_ENV", "INSTALLING_DEPS", "DOWNLOADING_DEPS",
                    "RETRYING_DEPS", "VERIFYING_ENV", "ENV_READY", "LOADING", "VERIFYING")) {
                request.setStage(stage);
                assertTrue(validator.validate(request).isEmpty(), stage);
            }
            request.setStage("RUN_ARBITRARY_SCRIPT");
            assertFalse(validator.validate(request).isEmpty());
        }
    }
}
