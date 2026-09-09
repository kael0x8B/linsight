<script setup lang="ts">
import { useVbenModal } from "@vben/common-ui";
import { message } from "ant-design-vue";
import { useVbenForm } from "#/adapter/form";
import { createRule, type AiVideoRuleApi } from "#/api/ai-video/rule";
const emit = defineEmits(["success"]);
const [Form, formApi] = useVbenForm({
  showDefaultActions: false,
  schema: [
    { fieldName: "name", label: "规则名称", component: "Input", rules: "required" },
    { fieldName: "code", label: "稳定编码", component: "Input", rules: "required" },
    {
      fieldName: "eventType",
      label: "事件类型",
      component: "AutoComplete",
      rules: "required",
      componentProps: {
        mode: undefined,
        options: [
          { label: "未戴安全帽", value: "SAFETY_HELMET" },
          { label: "未穿反光衣", value: "REFLECTIVE_VEST" },
          { label: "区域入侵", value: "AREA_INTRUSION" },
          { label: "车辆违停", value: "ILLEGAL_PARKING" },
          { label: "人员徘徊", value: "LOITERING" },
        ],
      },
    },
    { fieldName: "description", label: "说明", component: "Textarea" },
  ],
});
const [Modal, api] = useVbenModal({
  async onConfirm() {
    if (!(await formApi.validate()).valid) return;
    api.lock();
    try {
      await createRule({ ...((await formApi.getValues()) as AiVideoRuleApi.RuleSave), status: 0 });
      emit("success");
      await api.close();
      message.success("规则已创建，请编辑并发布首个版本");
    } finally {
      api.unlock();
    }
  },
});
</script>
<template>
  <Modal title="创建规则"><Form /></Modal>
</template>
