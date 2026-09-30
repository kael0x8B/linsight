<script setup lang="ts">
import type { PlatformConnectionProbe } from '#/api/ai-video/node/gateway';

import { onBeforeUnmount, onMounted, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import {
  Alert,
  Button,
  Form,
  FormItem,
  Input,
  Spin,
  Tag,
} from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  checkLocalGatewaySession,
  getLocalPlatformConnection,
  localGateway,
  loginLocalGateway,
  logoutLocalGateway,
  saveLocalPlatformConnection,
  testLocalPlatformConnection,
} from '#/api/ai-video/node/gateway';
import { $t } from '#/locales';
import GatewayWorkbench from '#/views/ai-video/node/gateway-workbench.vue';

const signedIn = ref(false);
const error = ref('');
const checking = ref(true);
const loginLoading = ref(false);
const logoutLoading = ref(false);
const t = (key: string) => $t(`ai-video-gateway.${key}`);
const [ConnectionModal, connectionModal] = useVbenModal({
  title: '平台连接设置',
  class: 'w-[560px]',
  confirmText: '保存并重连',
  cancelText: '关闭',
  onConfirm: saveConnection,
});
const connectionLoading = ref(false);
const connectionError = ref('');
const connectionSource = ref<'DEPLOYMENT' | 'LOCAL_OVERRIDE'>('DEPLOYMENT');
const platformUrl = ref('');
const probe = ref<null | PlatformConnectionProbe>(null);
const [LoginForm, loginForm] = useVbenForm({
  showDefaultActions: false,
  layout: 'vertical',
  wrapperClass: 'grid-cols-1',
  handleSubmit: login,
  submitOnEnter: true,
  schema: [
    {
      fieldName: 'password',
      label: $t('ai-video-gateway.me8e6d72c99'),
      component: 'InputPassword',
      rules: 'required',
      componentProps: {
        autocomplete: 'current-password',
        size: 'large',
        placeholder: t('passwordPlaceholder'),
        maxlength: 256,
      },
    },
  ],
});
async function login() {
  if (loginLoading.value) return;
  const validation = await loginForm.validate();
  if (!validation.valid) return;
  loginLoading.value = true;
  error.value = '';
  try {
    const values = await loginForm.getValues();
    await loginLocalGateway(values.password);
    signedIn.value = true;
    await loginForm.resetForm();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : t('maeb6c8a818');
  } finally {
    loginLoading.value = false;
  }
}
async function logout() {
  logoutLoading.value = true;
  try {
    await logoutLocalGateway();
    signedIn.value = false;
    error.value = '';
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : t('logoutFailed');
  } finally {
    logoutLoading.value = false;
  }
}
function sessionExpired() {
  if (!signedIn.value) return;
  signedIn.value = false;
  connectionModal.close();
  error.value = t('mf3b638c155');
}
async function restoreSession() {
  checking.value = true;
  error.value = '';
  try {
    signedIn.value = await checkLocalGatewaySession();
  } catch {
    error.value = t('sessionUnavailable');
  } finally {
    checking.value = false;
  }
}
async function openConnection() {
  connectionModal.open();
  connectionLoading.value = true;
  connectionError.value = '';
  probe.value = null;
  try {
    const connection = await getLocalPlatformConnection();
    platformUrl.value = connection.platformUrl;
    connectionSource.value = connection.source;
  } catch (cause) {
    connectionError.value =
      cause instanceof Error ? cause.message : '读取平台地址失败';
  } finally {
    connectionLoading.value = false;
  }
}
async function testConnection() {
  connectionLoading.value = true;
  connectionError.value = '';
  probe.value = null;
  try {
    probe.value = await testLocalPlatformConnection(platformUrl.value);
    platformUrl.value = probe.value.platformUrl;
  } catch (cause) {
    connectionError.value =
      cause instanceof Error ? cause.message : '测试平台连接失败';
  } finally {
    connectionLoading.value = false;
  }
}
async function saveConnection() {
  connectionModal.lock();
  connectionLoading.value = true;
  connectionError.value = '';
  try {
    const saved = await saveLocalPlatformConnection(platformUrl.value);
    platformUrl.value = saved.platformUrl;
    connectionSource.value = saved.source;
    probe.value = saved.probe;
  } catch (cause) {
    connectionError.value =
      cause instanceof Error ? cause.message : '保存平台地址失败';
  } finally {
    connectionLoading.value = false;
    connectionModal.unlock();
  }
}
onMounted(() => {
  window.addEventListener('gateway-session-expired', sessionExpired);
  void restoreSession();
});
onBeforeUnmount(() =>
  window.removeEventListener('gateway-session-expired', sessionExpired),
);
</script>
<template>
  <div v-if="checking" class="gateway-loading" role="status">
    <Spin size="large" />
    <p>{{ t('sessionChecking') }}</p>
  </div>
  <div v-else-if="signedIn" class="gateway-shell">
    <header class="gateway-topbar">
      <div class="gateway-brand">
        <span class="gateway-logo">L</span><strong>LInsight</strong
        ><span class="gateway-topbar-label">{{ t('localConsole') }}</span>
      </div>
      <div class="gateway-topbar-actions">
        <Button @click="openConnection">{{ t('platformSettings') }}</Button>
        <Button :loading="logoutLoading" @click="logout">{{
          t('m462c4a79d3')
        }}</Button>
      </div>
    </header>
    <Alert v-if="error" class="m-4" type="error" :message="error" show-icon />
    <GatewayWorkbench :transport="localGateway" local />
    <ConnectionModal>
      <div class="space-y-4 py-2">
        <Alert
          message="修改后 Edge Agent 会自动断开旧平台并连接新地址，本地识别任务不会停止。"
          type="info"
          show-icon
        />
        <Form layout="vertical">
          <FormItem label="平台地址" required>
            <Input
              v-model:value="platformUrl"
              :disabled="connectionLoading"
              placeholder="例如 192.168.2.11 或 http://192.168.2.11:48888"
              @press-enter="testConnection"
            />
          </FormItem>
        </Form>
        <div class="flex items-center justify-between">
          <div class="text-sm text-muted-foreground">
            当前来源：
            <Tag
              :color="
                connectionSource === 'LOCAL_OVERRIDE' ? 'blue' : 'default'
              "
            >
              {{
                connectionSource === 'LOCAL_OVERRIDE'
                  ? '盒子本地设置'
                  : '部署配置'
              }}
            </Tag>
          </div>
          <Button :loading="connectionLoading" @click="testConnection"
            >测试连接</Button
          >
        </div>
        <Alert
          v-if="connectionError"
          :message="connectionError"
          type="error"
          show-icon
        />
        <Alert
          v-if="probe"
          :message="probe.message"
          :description="`地址：${probe.platformUrl}；耗时：${probe.latencyMs} ms${probe.httpStatus ? `；HTTP ${probe.httpStatus}` : ''}`"
          :type="probe.reachable ? 'success' : 'warning'"
          show-icon
        />
      </div>
    </ConnectionModal>
  </div>
  <main v-else class="gateway-login">
    <div class="gateway-login-card">
      <section class="gateway-login-story">
        <div class="gateway-brand">
          <span class="gateway-logo">L</span><strong>LInsight</strong>
        </div>
        <div>
          <span class="gateway-login-kicker">{{ t('localConsole') }}</span>
          <h1>{{ t('loginHeadline') }}</h1>
          <p>{{ t('loginDescription') }}</p>
        </div>
        <div class="gateway-device" aria-hidden="true">
          <svg viewBox="0 0 360 180" fill="none">
            <path
              d="M32 125H108M252 125H328M180 26V57"
              stroke="currentColor"
              stroke-width="2"
              stroke-dasharray="5 6"
              opacity=".4"
            />
            <rect
              x="106"
              y="57"
              width="148"
              height="107"
              rx="18"
              fill="currentColor"
              fill-opacity=".07"
              stroke="currentColor"
              stroke-opacity=".4"
            />
            <rect
              x="123"
              y="75"
              width="114"
              height="54"
              rx="7"
              fill="currentColor"
              fill-opacity=".08"
            />
            <path
              d="M147 94V88H159M201 88H213V100M213 111V117H201M159 117H147V105"
              stroke="currentColor"
              stroke-width="2"
            />
            <circle
              cx="180"
              cy="102"
              r="9"
              stroke="currentColor"
              stroke-width="2"
            />
            <circle cx="130" cy="146" r="3" fill="#6ee7b7" />
            <path
              d="M193 146H230"
              stroke="currentColor"
              stroke-width="3"
              stroke-linecap="round"
            />
            <circle cx="26" cy="125" r="6" stroke="currentColor" />
            <circle cx="334" cy="125" r="6" stroke="currentColor" />
            <circle cx="180" cy="20" r="6" stroke="currentColor" />
          </svg>
        </div>
        <div class="gateway-login-capabilities">
          <span>{{ t('localRecognition') }}</span
          ><span>{{ t('deviceManagement') }}</span
          ><span>{{ t('eventDelivery') }}</span>
        </div>
      </section>
      <section class="gateway-login-form">
        <div class="gateway-login-heading">
          <h2>{{ t('m074e7bc232') }}</h2>
          <p>{{ t('loginWelcome') }}</p>
        </div>
        <Alert
          v-if="error"
          class="mb-5"
          type="error"
          :message="error"
          show-icon
        />
        <LoginForm />
        <Button
          class="gateway-login-submit"
          type="primary"
          size="large"
          block
          :loading="loginLoading"
          @click="login"
          >{{ t('enterWorkbench') }}</Button
        >
        <p class="gateway-session-hint">{{ t('sessionHint') }}</p>
        <div class="gateway-login-help">
          <strong>{{ t('passwordHelpTitle') }}</strong>
          <p>{{ t('mb5a1061ac8') }}</p>
        </div>
      </section>
    </div>
    <footer>LInsight · {{ t('localConsole') }}</footer>
  </main>
</template>

<style scoped>
.gateway-loading {
  display: flex;
  min-height: 100dvh;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 20px;
  color: hsl(var(--muted-foreground));
}
.gateway-shell {
  min-height: 100dvh;
  background: hsl(var(--background));
}
.gateway-topbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 32px;
  border-bottom: 1px solid hsl(var(--border));
  background: hsl(var(--card));
}
.gateway-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 22px;
  letter-spacing: -0.5px;
}
.gateway-logo {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 10px;
  background: #2563eb;
  color: white;
  font-weight: 800;
  font-size: 24px;
}
.gateway-topbar-label {
  margin-left: 8px;
  padding-left: 20px;
  border-left: 1px solid hsl(var(--border));
  color: hsl(var(--muted-foreground));
  font-size: 14px;
  letter-spacing: 0;
}
.gateway-topbar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.gateway-login {
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  background:
    radial-gradient(ellipse at 20% 10%, #e8efff, transparent 55%), #f5f7fb;
  color: #17243c;
}
.gateway-login-card {
  display: grid;
  grid-template-columns: 1fr 1fr;
  width: min(100%, 1000px);
  overflow: hidden;
  border: 1px solid #e0e7f1;
  border-radius: 24px;
  box-shadow: 0 24px 80px #17315b12;
  background: white;
}
.gateway-login-story {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 36px;
  padding: 44px;
  color: #eef5ff;
  background: linear-gradient(145deg, #102957, #153b79 70%, #1c4b8f);
}
.gateway-login-story .gateway-logo {
  background: #ffffff1a;
  border: 1px solid #ffffff30;
}
.gateway-login-kicker {
  color: #b2cefb;
  font-size: 13px;
}
.gateway-login-story h1 {
  margin: 14px 0 18px;
  max-width: 320px;
  font-size: 34px;
  line-height: 1.45;
  font-weight: 600;
  letter-spacing: 1px;
}
.gateway-login-story p {
  color: #b9cbe8;
  font-size: 14px;
  line-height: 1.9;
}
.gateway-device {
  margin: -22px 0 -14px;
  color: #a4c8ff;
}
.gateway-device svg {
  width: 100%;
  height: 165px;
}
.gateway-login-capabilities {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #c2d5f4;
  font-size: 12px;
}
.gateway-login-form {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 52px 48px;
}
.gateway-login-heading {
  margin-bottom: 32px;
}
.gateway-login-heading h2 {
  font-size: 26px;
  font-weight: 600;
  margin-bottom: 10px;
}
.gateway-login-heading p {
  color: #718096;
  font-size: 14px;
}
.gateway-login-submit {
  height: 46px;
  margin-top: 6px;
}
.gateway-session-hint {
  margin-top: 16px;
  color: #718096;
  font-size: 12px;
  line-height: 1.8;
}
.gateway-login-help {
  margin-top: 36px;
  border-top: 1px solid #edf0f5;
  padding-top: 22px;
  font-size: 12px;
  line-height: 1.9;
  color: #718096;
}
.gateway-login-help strong {
  display: block;
  color: #475569;
  margin-bottom: 5px;
  font-weight: 500;
}
.gateway-login footer {
  padding-top: 28px;
  color: #94a3b8;
  font-size: 12px;
}
@media (max-width: 700px) {
  .gateway-login {
    padding: 24px 16px;
  }
  .gateway-login-card {
    grid-template-columns: 1fr;
    max-width: 460px;
    border-radius: 18px;
  }
  .gateway-login-story {
    gap: 18px;
    padding: 28px;
  }
  .gateway-login-story h1 {
    font-size: 24px;
    margin: 8px 0;
    max-width: none;
  }
  .gateway-device,
  .gateway-login-capabilities {
    display: none;
  }
  .gateway-login-form {
    padding: 30px 28px;
  }
  .gateway-login-help {
    margin-top: 24px;
  }
  .gateway-topbar {
    padding: 16px;
  }
  .gateway-topbar-label {
    display: none;
  }
}
</style>
