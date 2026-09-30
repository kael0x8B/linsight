<script lang="ts" setup>
import type {
  AiVideoNode,
  AiVideoNodeDeployment,
  AiVideoNodeDeploymentConnection,
  AiVideoNodeDeploymentPreflight,
} from '#/api/ai-video/node';

import { computed, onBeforeUnmount, ref } from 'vue';

import { useVbenDrawer } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Checkbox,
  Descriptions,
  DescriptionsItem,
  Progress,
  Result,
  Steps,
  Tag,
} from 'ant-design-vue';

import { useVbenForm, z } from '#/adapter/form';
import {
  createNodeDeployment,
  getNodeDeployment,
  preflightNodeDeployment,
} from '#/api/ai-video/node';

import DeploymentTerminal from './deployment-terminal.vue';

const emit = defineEmits(['success']);

const currentStep = ref(0);
const connection = ref<AiVideoNodeDeploymentConnection>();
const preflight = ref<AiVideoNodeDeploymentPreflight>();
const fingerprintConfirmed = ref(false);
const deployment = ref<AiVideoNodeDeployment>();
const operationType = ref<'INITIAL' | 'REDEPLOY' | 'ROLLBACK'>('INITIAL');
const targetNode = ref<AiVideoNode>();
const pollError = ref('');
const actionError = ref('');
let requestId = crypto.randomUUID();
let pollGeneration = 0;
let pollTimer: ReturnType<typeof setTimeout> | undefined;

interface DrawerData {
  mode?: 'REDEPLOY' | 'ROLLBACK';
  node?: AiVideoNode;
}

const stepItems = [
  { title: '连接预检' },
  { title: '部署配置' },
  { title: '执行进度' },
];
const confirmText = computed(() => {
  if (currentStep.value === 0) return '检测连接';
  if (currentStep.value === 1) {
    if (operationType.value === 'ROLLBACK') return '恢复完整部署';
    return operationType.value === 'REDEPLOY' ? '开始在线升级' : '开始部署';
  }
  return deployment.value?.status === 'SUCCEEDED' ? '完成' : '关闭';
});
const statusText = computed(
  () =>
    ({
      FAILED: '部署失败',
      QUEUED: '等待执行',
      RUNNING: '正在部署',
      SUCCEEDED: '部署完成',
    })[deployment.value?.status ?? 'QUEUED'],
);

const [ConnectionForm, connectionFormApi] = useVbenForm({
  commonConfig: {
    componentProps: { class: 'w-full' },
    labelWidth: 96,
  },
  layout: 'horizontal',
  schema: [
    {
      component: 'Input',
      componentProps: { placeholder: '例如 192.168.2.17' },
      fieldName: 'host',
      label: '节点地址',
      rules: z.string().trim().min(1, '请输入节点地址').max(255),
    },
    {
      component: 'InputNumber',
      componentProps: { max: 65_535, min: 1 },
      fieldName: 'port',
      label: 'SSH 端口',
      rules: z.number().min(1).max(65_535),
    },
    {
      component: 'Input',
      componentProps: { autocomplete: 'username', placeholder: '例如 linaro' },
      fieldName: 'username',
      label: 'SSH 用户',
      rules: z
        .string()
        .regex(/^[A-Za-z_][\w-]{0,31}$/, '请输入合法 Linux 用户名'),
    },
    {
      component: 'InputPassword',
      componentProps: {
        autocomplete: 'current-password',
        placeholder: '仅用于本次预检和部署，不会保存',
      },
      fieldName: 'password',
      label: 'SSH 密码',
      rules: z.string().min(1, '请输入 SSH 密码').max(256),
    },
  ],
  showDefaultActions: false,
});

const [DeploymentForm, deploymentFormApi] = useVbenForm({
  commonConfig: {
    componentProps: { class: 'w-full' },
    labelWidth: 112,
  },
  layout: 'horizontal',
  schema: [
    {
      component: 'Input',
      componentProps: { placeholder: '例如 rk3566-edge-01' },
      fieldName: 'nodeCode',
      label: '节点编码',
      rules: z
        .string()
        .regex(/^[A-Za-z0-9_-]{1,64}$/, '仅支持字母、数字、_ 和 -'),
    },
    {
      component: 'Input',
      componentProps: { maxlength: 100, placeholder: '例如 RK3566 边缘网关' },
      fieldName: 'nodeName',
      label: '节点名称',
      rules: z.string().trim().min(1, '请输入节点名称').max(100),
    },
    {
      component: 'Input',
      componentProps: {
        placeholder: '网关能够访问的 Java 控制面地址',
      },
      fieldName: 'controlPlaneUrl',
      description: '不能填写 localhost；请使用网关可访问的控制面 IP 或域名。',
      label: '控制面地址',
      rules: z.string().url('请输入完整的 HTTP/HTTPS 地址'),
    },
    {
      component: 'Switch',
      componentProps: {
        class: '!w-auto shrink-0',
        checkedChildren: '自动安装',
        unCheckedChildren: '跳过安装',
      },
      defaultValue: true,
      fieldName: 'installDependencies',
      description: '缺少受支持 Python 时独立安装 3.12；并补齐 venv、FFmpeg、CA 证书和 curl，不修改系统 python3。',
      label: '系统依赖',
    },
  ],
  showDefaultActions: false,
});

async function runPreflight() {
  const { valid } = await connectionFormApi.validate();
  if (!valid) return;
  const values = {
    ...(await connectionFormApi.getValues()),
    nodeId: targetNode.value?.id,
  } as AiVideoNodeDeploymentConnection;
  actionError.value = '';
  drawerApi.lock();
  try {
    preflight.value = await preflightNodeDeployment(values);
    connection.value = values;
    if (preflight.value.existingNodeId && operationType.value !== 'ROLLBACK')
      operationType.value = 'REDEPLOY';
    fingerprintConfirmed.value = false;
    if (preflight.value.existingNodeCode) {
      await deploymentFormApi.setValues({
        nodeCode: preflight.value.existingNodeCode,
        nodeName: preflight.value.existingNodeName,
        ...(preflight.value.controlPlaneUrl
          ? { controlPlaneUrl: preflight.value.controlPlaneUrl }
          : {}),
      });
    }
    deploymentFormApi.updateSchema([
      {
        fieldName: 'nodeCode',
        componentProps: { disabled: !!preflight.value.existingNodeId },
      },
    ]);
    currentStep.value = 1;
  } catch (error) {
    actionError.value =
      error instanceof Error
        ? error.message
        : '连接预检失败，请检查提示后重试。';
  } finally {
    drawerApi.unlock();
  }
}

async function startDeployment() {
  const { valid } = await deploymentFormApi.validate();
  if (!valid || !connection.value || !preflight.value) return;
  if (!preflight.value.supported || !fingerprintConfirmed.value) return;
  if (
    operationType.value === 'ROLLBACK' &&
    !preflight.value.sourceRollbackAvailable
  )
    return;
  const values = await deploymentFormApi.getValues();
  if (!preflight.value.pythonSupported && !values.installDependencies) {
    actionError.value = '目标节点缺少 Python 3.12/3.13，请启用自动安装';
    return;
  }
  drawerApi.lock();
  try {
    const id = await createNodeDeployment({
      ...connection.value,
      nodeId: preflight.value.existingNodeId ?? targetNode.value?.id,
      requestId,
      action: operationType.value === 'ROLLBACK' ? 'ROLLBACK' : 'DEPLOY',
      controlPlaneUrl: values.controlPlaneUrl,
      hostKey: preflight.value.hostKey,
      hostKeyFingerprint: preflight.value.hostKeyFingerprint,
      hostKeyType: preflight.value.hostKeyType,
      installDependencies: values.installDependencies ?? true,
      nodeCode: values.nodeCode,
      nodeName: values.nodeName,
    });
    currentStep.value = 2;
    deployment.value = {
      createTime: '',
      host: connection.value.host,
      id,
      nodeCode: values.nodeCode,
      nodeName: values.nodeName,
      operationType: operationType.value,
      outputLog:
        operationType.value === 'REDEPLOY'
          ? '[QUEUED] 在线升级任务已创建，等待重新部署\n'
          : '[QUEUED] 部署任务已创建，等待执行\n',
      port: connection.value.port,
      progress: 5,
      stage: 'QUEUED',
      status: 'QUEUED',
      updateTime: '',
      username: connection.value.username,
    };
    connection.value = undefined;
    schedulePoll();
    await connectionFormApi.setFieldValue('password', '');
  } catch (error) {
    actionError.value =
      error instanceof Error
        ? error.message
        : '部署任务未能创建，请检查配置后重试。';
  } finally {
    drawerApi.unlock();
  }
}

function schedulePoll() {
  if (!deployment.value?.id) return;
  const generation = pollGeneration;
  const id = deployment.value.id;
  pollTimer = setTimeout(async () => {
    try {
      const result = await getNodeDeployment(id);
      if (generation !== pollGeneration) return;
      deployment.value = result;
      pollError.value = '';
      if (result.status === 'SUCCEEDED') emit('success');
    } catch {
      if (generation === pollGeneration)
        pollError.value = '日志刷新失败，正在自动重试；已收到的输出仍保留。';
    } finally {
      if (
        generation === pollGeneration &&
        deployment.value &&
        !['FAILED', 'SUCCEEDED'].includes(deployment.value.status)
      )
        schedulePoll();
    }
  }, 1500);
}

function clearPoll() {
  pollGeneration++;
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = undefined;
}

async function reset() {
  clearPoll();
  currentStep.value = 0;
  pollError.value = '';
  connection.value = undefined;
  preflight.value = undefined;
  fingerprintConfirmed.value = false;
  deployment.value = undefined;
  operationType.value = 'INITIAL';
  targetNode.value = undefined;
  actionError.value = '';
  requestId = crypto.randomUUID();
  if (connectionFormApi.isMounted) await connectionFormApi.resetForm();
  if (deploymentFormApi.isMounted) await deploymentFormApi.resetForm();
}

async function retryDeployment() {
  clearPoll();
  deployment.value = undefined;
  connection.value = undefined;
  preflight.value = undefined;
  fingerprintConfirmed.value = false;
  actionError.value = '';
  pollError.value = '';
  requestId = crypto.randomUUID();
  await connectionFormApi.setFieldValue('password', '');
  currentStep.value = 0;
}

const [Drawer, drawerApi] = useVbenDrawer({
  async onConfirm() {
    if (currentStep.value === 0) return runPreflight();
    if (currentStep.value === 1) return startDeployment();
    await drawerApi.close();
  },
  async onOpenChange(open) {
    if (!open) {
      await reset();
      return;
    }
    const data = drawerApi.getData<DrawerData>();
    if (data?.mode && data.node) {
      operationType.value = data.mode;
      targetNode.value = data.node;
    }
    const browserHost = window.location.hostname;
    const controlPlaneUrl = ['127.0.0.1', '::1', 'localhost'].includes(
      browserHost,
    )
      ? ''
      : `http://${browserHost}:48888`;
    await Promise.all([
      connectionFormApi.setValues({
        host: targetNode.value?.ipAddress,
        port: 22,
      }),
      deploymentFormApi.setValues({
        controlPlaneUrl,
        installDependencies: true,
        nodeCode: targetNode.value?.code ?? 'rk3566-edge-01',
        nodeName: targetNode.value?.name ?? 'RK3566 边缘网关',
      }),
    ]);
  },
});

const submitting = drawerApi.useStore((state) => state.submitting);

onBeforeUnmount(clearPoll);
</script>

<template>
  <Drawer
    class="w-[820px] max-w-[calc(100vw-32px)]"
    :show-confirm-button="false"
    :title="
      operationType === 'ROLLBACK'
        ? `恢复完整部署 · ${targetNode?.name ?? preflight?.existingNodeName ?? ''}`
        : operationType === 'REDEPLOY'
          ? `在线升级 · ${targetNode?.name ?? preflight?.existingNodeName ?? ''}`
          : '部署边缘节点'
    "
  >
    <template #prepend-footer>
      <Button v-if="currentStep === 1" @click="currentStep = 0">
        返回连接配置
      </Button>
      <Button
        v-if="currentStep === 2 && deployment?.status === 'FAILED'"
        @click="retryDeployment"
      >
        重新预检并重试
      </Button>
    </template>
    <template #append-footer>
      <Button
        type="primary"
        :disabled="
          currentStep === 1 &&
          (!preflight?.supported ||
            !fingerprintConfirmed ||
            (operationType === 'ROLLBACK' &&
              !preflight?.sourceRollbackAvailable))
        "
        :loading="submitting"
        @click="drawerApi.onConfirm()"
      >
        {{ confirmText }}
      </Button>
    </template>
    <div class="deployment-content px-2 py-1">
      <Steps :current="currentStep" :items="stepItems" size="small" />
      <Alert v-if="actionError" :message="actionError" show-icon type="error" />
      <Alert
        v-if="operationType === 'ROLLBACK'"
        message="恢复上一次源码部署的 Runtime、Python 环境和服务配置；会短暂中断推理。可恢复能力在 SSH 预检后确认，与签名 Agent 回滚分开。"
        show-icon
        type="warning"
      />

      <div v-show="currentStep === 0" class="deployment-step">
        <div class="deployment-section">
          <div class="section-heading">
            <IconifyIcon icon="lucide:shield-check" />
            SSH 连接
          </div>
          <ConnectionForm />
        </div>
      </div>

      <div v-show="currentStep === 1" class="deployment-step">
        <template v-if="preflight">
          <Alert
            :message="
              preflight.supported
                ? '环境满足自动部署基线'
                : '环境不满足自动部署基线，请先处理下方问题'
            "
            show-icon
            :type="preflight.supported ? 'success' : 'error'"
          />
          <div class="preflight-grid">
            <div class="metric-item">
              <span>当前版本</span
              ><strong>{{ preflight.currentVersion || '未安装' }}</strong>
            </div>
            <div class="metric-item">
              <span>本次目标</span
              ><strong>{{
                operationType === 'ROLLBACK'
                  ? preflight.previousVersion || '不可回滚'
                  : '当前源码包（打包后生成 source-指纹）'
              }}</strong>
            </div>
            <div class="metric-item">
              <span>完整部署可回滚版本</span
              ><strong>{{
                preflight.sourceRollbackAvailable
                  ? preflight.previousVersion
                  : '没有可用快照'
              }}</strong>
            </div>
            <div class="metric-item">
              <span>系统</span><strong>{{ preflight.osSummary }}</strong>
            </div>
            <div class="metric-item">
              <span>架构</span><strong>{{ preflight.architecture }}</strong>
            </div>
            <div class="metric-item">
              <span>Python</span><strong>{{ preflight.pythonVersion }}</strong>
            </div>
            <div class="metric-item">
              <span>可用内存 / 总内存</span
              ><strong
                >{{ preflight.memoryAvailableMb }} /
                {{ preflight.memoryMb }} MB</strong
              >
            </div>
            <div class="metric-item">
              <span>可用磁盘</span
              ><strong>{{ preflight.diskAvailableMb }} MB</strong>
            </div>
            <div class="metric-item">
              <span>推理模式</span
              ><strong>{{ preflight.executionMode }}</strong>
            </div>
          </div>
          <div class="flex flex-wrap gap-2">
            <Tag :color="preflight.sudoAvailable ? 'green' : 'red'">
              sudo {{ preflight.sudoAvailable ? '可用' : '缺失' }}
            </Tag>
            <Tag :color="preflight.ffmpegInstalled ? 'green' : 'orange'">
              FFmpeg {{ preflight.ffmpegInstalled ? '已安装' : '待安装' }}
            </Tag>
            <Tag :color="preflight.venvAvailable ? 'green' : 'orange'">
              Python 环境
              {{ preflight.venvAvailable ? '可用' : '待检查 / 补齐' }}
            </Tag>
            <Tag
              :color="
                preflight.offlineDependenciesAvailable ? 'green' : 'orange'
              "
            >
              依赖包
              {{
                preflight.offlineDependenciesAvailable
                  ? '离线就绪'
                  : '需在线下载'
              }}
            </Tag>
            <Tag :color="preflight.rknpuAvailable ? 'blue' : 'default'">
              RK NPU {{ preflight.rknpuAvailable ? '已发现' : '未发现' }}
            </Tag>
          </div>
          <Alert
            v-for="warning in preflight.warnings"
            :key="warning"
            :message="
              warning === '可用内存不足 256 MB'
                ? '可用内存不足 256 MB。请先停止该节点的识别任务并关闭预览，再返回连接配置重新预检；若模型缓存仍未释放，可在维护期间重启节点后重试。升级完成后需恢复识别任务。'
                : warning
            "
            show-icon
            type="warning"
          />
          <Alert
            v-if="preflight.existingNodeCode"
            :message="`该地址已注册为 ${preflight.existingNodeCode}，已自动沿用原节点身份`"
            description="重新部署必须保持节点编码不变，否则新配置无法与节点已有凭据匹配。"
            show-icon
            type="info"
          />
          <div class="fingerprint-box">
            <span>SSH 主机指纹</span>
            <code>{{ preflight.hostKeyFingerprint }}</code>
            <Checkbox v-model:checked="fingerprintConfirmed">
              我已确认这是目标网关的主机指纹
            </Checkbox>
          </div>
        </template>
        <div class="deployment-section">
          <div class="section-heading">
            <IconifyIcon icon="lucide:server-cog" />
            节点配置
          </div>
          <DeploymentForm />
        </div>
      </div>

      <template v-if="currentStep === 2 && deployment">
        <Result
          v-if="deployment.status === 'SUCCEEDED'"
          status="success"
          :sub-title="
            operationType === 'REDEPLOY'
              ? '最新版 AI Runtime 与 Edge Agent 已重新部署，原节点身份保持不变并已恢复心跳。'
              : 'AI Runtime 与 Edge Agent 已由 systemd 托管，节点已经开始上报心跳。'
          "
          :title="
            operationType === 'REDEPLOY' ? '在线升级完成' : '节点部署完成'
          "
        />
        <Result
          v-else-if="deployment.status === 'FAILED'"
          status="error"
          :sub-title="deployment.message"
          title="节点部署失败"
        />
        <div v-else class="deployment-progress">
          <div class="progress-icon">
            <IconifyIcon icon="lucide:package-open" />
          </div>
          <h3>{{ statusText }}</h3>
          <p>{{ deployment.message }}</p>
          <Progress :percent="deployment.progress" status="active" />
        </div>
        <Descriptions bordered :column="2" size="small">
          <DescriptionsItem label="目标节点">
            {{ deployment.host }}:{{ deployment.port }}
          </DescriptionsItem>
          <DescriptionsItem label="节点编码">
            {{ deployment.nodeCode }}
          </DescriptionsItem>
          <DescriptionsItem label="原版本">
            {{
              deployment.previousVersion ||
              preflight?.currentVersion ||
              '未安装 / 未记录'
            }}
          </DescriptionsItem>
          <DescriptionsItem label="目标版本">
            {{
              deployment.targetVersion ||
              (['SUCCEEDED', 'FAILED'].includes(deployment.status)
                ? '未记录 / 未生成'
                : '正在生成部署包版本')
            }}
          </DescriptionsItem>
          <DescriptionsItem label="执行阶段">
            {{ deployment.stage }}
          </DescriptionsItem>
          <DescriptionsItem label="部署状态">
            <Tag
              :color="
                deployment.status === 'FAILED'
                  ? 'red'
                  : deployment.status === 'SUCCEEDED'
                    ? 'green'
                    : 'blue'
              "
            >
              {{ statusText }}
            </Tag>
          </DescriptionsItem>
          <DescriptionsItem
            v-if="deployment.diagnosticId"
            label="诊断 ID"
            :span="2"
          >
            <code>{{ deployment.diagnosticId }}</code>
          </DescriptionsItem>
        </Descriptions>
        <Alert v-if="pollError" :message="pollError" type="warning" show-icon />
        <DeploymentTerminal
          class="mt-4"
          :output="deployment.outputLog"
          :status="deployment.status"
          :log-status="deployment.logStatus"
          :truncated="deployment.logTruncated"
        />
      </template>
    </div>
  </Drawer>
</template>

<style scoped>
.deployment-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}

.deployment-step {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.deployment-section {
  padding: 18px 18px 4px;
  background: hsl(var(--muted) / 35%);
  border-radius: 10px;
}

.section-heading {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 16px;
  font-size: 14px;
  font-weight: 600;
}

.preflight-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 72px;
  padding: 12px 14px;
  background: hsl(var(--muted) / 35%);
  border-radius: 8px;
}

.metric-item span,
.fingerprint-box > span {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.metric-item strong {
  margin-top: 5px;
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.fingerprint-box {
  display: grid;
  gap: 9px;
  padding: 14px 16px;
  border: 1px solid hsl(var(--border));
  border-radius: 9px;
}

.fingerprint-box code {
  font-size: 12px;
  overflow-wrap: anywhere;
}

.deployment-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  max-width: 560px;
  min-height: 260px;
  margin: 0 auto;
  text-align: center;
}

.deployment-progress .progress-icon {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  margin-bottom: 14px;
  font-size: 24px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 12%);
  border-radius: 12px;
}

.deployment-progress h3 {
  font-size: 18px;
  font-weight: 600;
}

.deployment-progress p {
  margin: 8px 0 20px;
  color: hsl(var(--muted-foreground));
}

@media (max-width: 760px) {
  .preflight-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 480px) {
  .preflight-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
