package com.linsight.module.aivideo.service.task;
import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.Map;
import static org.assertj.core.api.Assertions.*;
class TaskModelCapabilityTest {
    Map<String,Object> dag(String capability) { return Map.of("nodes",List.of(Map.of("id","model","capabilityKey",capability))); }
    @Test void cocoCannotServeAsVestClassifier() {
        assertThatThrownBy(()->TaskServiceImpl.validateBindingLabels(dag("ppe.reflective-vest"),"model","{\"decoder\":{\"labels\":[\"person\",\"car\"]}}"))
                .hasMessageContaining("no_vest");
    }
    @Test void vestOnlyWeightCannotDetermineAbsence() {
        assertThatThrownBy(()->TaskServiceImpl.validateBindingLabels(dag("ppe.reflective-vest"),"model","{\"decoder\":{\"labels\":[\"vest\"]}}"));
    }
    @Test void onePpeWeightCanProvideBothRoles() {
        String manifest="{\"decoder\":{\"labels\":[\"person\",\"vest\",\"no_vest\"]}}";
        assertThatCode(()->TaskServiceImpl.validateBindingLabels(dag("ppe.reflective-vest"),"model",manifest)).doesNotThrowAnyException();
        assertThatCode(()->TaskServiceImpl.validateBindingLabels(dag("detector.person"),"model",manifest)).doesNotThrowAnyException();
    }
    @Test void missingMetadataDoesNotClaimPpeCapability() {
        assertThatThrownBy(()->TaskServiceImpl.validateBindingLabels(dag("ppe.reflective-vest"),"model",null));
    }
}
