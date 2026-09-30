<script setup lang="ts">
import type { FaceVerificationResult } from '#/api/ai-video/task/face-verification';

import { computed, onBeforeUnmount, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import {
  Alert,
  Button,
  Descriptions,
  DescriptionsItem,
  Image,
  message,
  Upload,
} from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { getCameraPage } from '#/api/ai-video/camera';
import { getModelPage, getModelVersionList } from '#/api/ai-video/model';
import { getNodeSimpleList } from '#/api/ai-video/node';
import {
  createFaceVerification,
  getFaceVerification,
} from '#/api/ai-video/task/face-verification';

type Option = { label: string; value: number };
const cameras = ref<Option[]>([]);
const nodes = ref<Option[]>([]);
const models = ref<Option[]>([]);
const versions = ref<Option[]>([]);
const file = ref<File>();
const preview = ref('');
const error = ref('');
const result = ref<FaceVerificationResult>();
const running = ref(false);
let generation = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
const reasons: Record<string, string> = {
  NO_FACE: '未检测到人脸，请正对摄像头',
  MULTIPLE_FACES: '画面内有多张人脸，请一次只由一人参与',
  FACE_TOO_SMALL: '人脸过小，请靠近摄像头或缩小取图区域',
  FACE_CLIPPED: '人脸未完整进入画面',
  INSUFFICIENT_IMAGE_QUALITY: '画面质量不足，请调整光照和站位',
  IDENTITY_NOT_CONFIRMED: '尚未达到身份核验阈值',
  NO_FRESH_FRAME: '未取得新的摄像头画面',
};
const resultText = computed(() => {
  if (!result.value) return '';
  const state = result.value.result.status;
  if (state === 'MATCH') return '本次身份比对通过（开发验证）';
  if (state === 'REFERENCE_INVALID') return '参考照片不符合要求';
  if (['EXPIRED', 'FAILED'].includes(result.value.status))
    return '核验超时或执行失败';
  return (
    reasons[result.value.result.reason ?? ''] ??
    '未能确认身份，请检查照片与取图区域'
  );
});

const [Form, formApi] = useVbenForm({
  showDefaultActions: false,
  wrapperClass: 'grid-cols-2',
  schema: [
    {
      fieldName: 'cameraId',
      label: '取图摄像头',
      component: 'Select',
      rules: 'required',
      componentProps: () => ({ options: cameras.value }),
    },
    {
      fieldName: 'nodeId',
      label: '推理网关',
      component: 'Select',
      rules: 'required',
      componentProps: () => ({ options: nodes.value }),
    },
    {
      fieldName: 'modelId',
      label: '核验模型',
      component: 'Select',
      rules: 'required',
      componentProps: () => ({ options: models.value, onChange: loadVersions }),
    },
    {
      fieldName: 'modelVersionId',
      label: '已就绪版本',
      component: 'Select',
      rules: 'required',
      componentProps: () => ({ options: versions.value }),
    },
    {
      fieldName: 'similarityThreshold',
      label: '测试相似度阈值',
      component: 'InputNumber',
      defaultValue: 0.6,
      rules: 'required',
      componentProps: { min: 0.1, max: 1, step: 0.05 },
    },
    {
      fieldName: 'roiX',
      label: '区域左边界（0–1）',
      component: 'InputNumber',
      defaultValue: 0,
      componentProps: { min: 0, max: 1, step: 0.05 },
    },
    {
      fieldName: 'roiY',
      label: '区域上边界（0–1）',
      component: 'InputNumber',
      defaultValue: 0,
      componentProps: { min: 0, max: 1, step: 0.05 },
    },
    {
      fieldName: 'roiWidth',
      label: '区域宽度（0–1）',
      component: 'InputNumber',
      defaultValue: 1,
      componentProps: { min: 0.05, max: 1, step: 0.05 },
    },
    {
      fieldName: 'roiHeight',
      label: '区域高度（0–1）',
      component: 'InputNumber',
      defaultValue: 1,
      componentProps: { min: 0.05, max: 1, step: 0.05 },
    },
    {
      fieldName: 'consentConfirmed',
      label: '本人参与确认',
      component: 'Checkbox',
      defaultValue: false,
      componentProps: { content: '本人同意本次照片与摄像头画面比对' },
    },
  ],
});

function isFacePair(manifest?: string) {
  try {
    return ['FACE_PAIR_SFACE', 'FACE_PAIR_SFACE_RKNN'].includes(
      JSON.parse(manifest ?? '{}').decoder?.type,
    );
  } catch {
    return false;
  }
}
async function loadVersions(id: number) {
  versions.value = [];
  await formApi.setValues({ modelVersionId: undefined });
  if (!id) return;
  try {
    const values = await getModelVersionList(id);
    versions.value = values
      .filter(
        (v) =>
          v.publishStatus === 'PUBLISHED' &&
          v.executionStatus === 'READY' &&
          isFacePair(v.runtimeManifest),
      )
      .map((v) => ({ label: v.version, value: v.id }));
  } catch {
    error.value = '模型版本加载失败，请重试';
  }
}

function cleanup() {
  generation++;
  if (timer) clearTimeout(timer);
  timer = undefined;
  if (preview.value) URL.revokeObjectURL(preview.value);
  preview.value = '';
  file.value = undefined;
  running.value = false;
}
function chooseFile(value: File) {
  if (
    !['image/jpeg', 'image/png'].includes(value.type) ||
    value.size > 10 * 1024 * 1024
  ) {
    message.warning('请选择不超过 10 MB 的 JPG 或 PNG 正面照片');
    return false;
  }
  if (preview.value) URL.revokeObjectURL(preview.value);
  preview.value = URL.createObjectURL(value);
  file.value = value;
  return false;
}
async function poll(id: number, version: number, deadline: number) {
  if (version !== generation) return;
  try {
    const value = await getFaceVerification(id);
    if (version !== generation) return;
    result.value = value;
    if (!['QUEUED', 'RUNNING', 'SENT'].includes(value.status)) {
      running.value = false;
      return;
    }
    if (Date.now() > deadline) {
      error.value = '等待结果超时，可稍后重新发起核验';
      running.value = false;
      return;
    }
    timer = setTimeout(() => poll(id, version, deadline), 1200);
  } catch {
    if (version === generation) {
      error.value = '查询失败，请检查网关与平台连接';
      running.value = false;
    }
  }
}
async function start() {
  const validation = await formApi.validate();
  if (running.value || !validation.valid) return;
  const values = await formApi.getValues();
  if (!file.value || values.consentConfirmed !== true) {
    message.warning('请上传参考照片并确认本人参与本次核验');
    return;
  }
  running.value = true;
  error.value = '';
  result.value = undefined;
  const version = ++generation;
  try {
    const id = await createFaceVerification({
      cameraId: Number(values.cameraId),
      nodeId: Number(values.nodeId),
      modelVersionId: Number(values.modelVersionId),
      consentConfirmed: true,
      file: file.value,
      similarityThreshold: Number(values.similarityThreshold),
      roiX: Number(values.roiX),
      roiY: Number(values.roiY),
      roiWidth: Number(values.roiWidth),
      roiHeight: Number(values.roiHeight),
    });
    await poll(id, version, Date.now() + 40_000);
  } catch {
    if (version === generation) {
      error.value =
        '发起失败：请确认所选模型已部署到该网关，且取图区域未超出画面';
      running.value = false;
    }
  }
}
const [Modal] = useVbenModal({
  showConfirmButton: false,
  async onOpenChange(open) {
    if (!open) {
      cleanup();
      return;
    }
    error.value = '';
    result.value = undefined;
    await formApi.setValues({ consentConfirmed: false });
    try {
      const [cameraPage, nodeList, modelPage] = await Promise.all([
        getCameraPage({ pageNo: 1, pageSize: 100, status: 0 }),
        getNodeSimpleList(),
        getModelPage({ pageNo: 1, pageSize: 100, status: 0 }),
      ]);
      cameras.value = cameraPage.list
        .filter((c) => c.id !== undefined)
        .map((c) => ({ label: c.name, value: Number(c.id) }));
      nodes.value = nodeList.map((n) => ({ label: n.name, value: n.id }));
      models.value = modelPage.list
        .filter(
          (m) =>
            m.id !== undefined &&
            (m.code === 'active-entry-face-yunet-sface' ||
              m.capabilities.some(
                (c) => c.capabilityKey === 'recognition.face-verification',
              )),
        )
        .map((m) => ({ label: m.name, value: Number(m.id) }));
    } catch {
      error.value = '配置加载失败，请关闭后重试';
    }
  },
});
onBeforeUnmount(cleanup);
</script>

<template>
  <Modal title="单次人脸比对" class="w-[800px] max-w-[95vw]">
    <div class="space-y-4">
      <Alert v-if="error" type="error" show-icon :message="error" />
      <Alert
        v-if="!models.length"
        type="info"
        message="尚无可用的主动核验模型，请先在模型中心登记并部署核验引擎。"
      />
      <Form />
      <div class="flex items-center gap-4">
        <Upload
          :before-upload="chooseFile"
          :show-upload-list="false"
          accept="image/jpeg,image/png"
          :disabled="running"
        >
          <Button>上传本人的正面参考照片</Button>
        </Upload>
        <Image
          v-if="preview"
          :src="preview"
          :width="80"
          :height="80"
          style="object-fit: contain"
        />
      </div>
      <p class="text-xs text-muted-foreground">
        仅比对本次上传的本人照片，最长 30
        秒，关闭窗口后也会到期自动结束。比对结果不作为通行依据，活体校验尚未验证。
      </p>
      <Button
        type="primary"
        :loading="running"
        :disabled="!models.length"
        @click="start"
      >
        {{ running ? '网关核验中…' : '本人开始本次核验' }}
      </Button>
      <template v-if="result && !running">
        <Alert
          :type="result.result.status === 'MATCH' ? 'success' : 'warning'"
          :message="resultText"
          show-icon
        />
        <Descriptions :column="2" bordered size="small">
          <DescriptionsItem label="相似度">
            {{ result.result.similarity?.toFixed(3) ?? '无有效结果' }}
          </DescriptionsItem>
          <DescriptionsItem label="有效匹配帧">
            {{ result.result.matchedFrames ?? 0 }} /
            {{ result.result.sampledFrames ?? 0 }}
          </DescriptionsItem>
          <DescriptionsItem label="推理位置">
            边缘网关 · {{ result.result.device ?? '未返回' }}
          </DescriptionsItem>
          <DescriptionsItem label="活体校验">未验证</DescriptionsItem>
        </Descriptions>
      </template>
    </div>
  </Modal>
</template>
