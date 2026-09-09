<script setup lang="ts">
import { onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';

import { Alert, Button } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { localGateway } from '#/api/ai-video/node/gateway';
import { $t } from '#/locales';
import GatewayWorkbench from '#/views/ai-video/node/gateway-workbench.vue';

const signedIn = ref(false);
const error = ref('');
const [LoginForm, loginForm] = useVbenForm({
  showDefaultActions: false,
  schema: [{ fieldName: 'password', label: $t('ai-video-gateway.me8e6d72c99'), component: 'InputPassword', rules: 'required', componentProps: { autocomplete: 'current-password' } }],
});
async function login() {
  if (!(await loginForm.validate()).valid) return;
  try {
    const response = await fetch('/gateway-api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(await loginForm.getValues()) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || $t('ai-video-gateway.maeb6c8a818'));
    signedIn.value = true; error.value = ''; await loginForm.resetForm();
  } catch (e) { error.value = e instanceof Error ? e.message : $t('ai-video-gateway.m04a090194d'); }
}
async function logout() {
  await fetch('/gateway-api/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  signedIn.value = false;
}
onMounted(async () => { try { await localGateway('snapshot'); signedIn.value = true; } catch { /* Show the independent local login. */ } });
</script>
<template>
  <div v-if="signedIn"><div class="flex justify-end border-b bg-white px-6 py-2"><Button @click="logout">{{ $t('ai-video-gateway.m462c4a79d3') }}</Button></div><GatewayWorkbench :transport="localGateway" local /></div>
  <Page v-else :title="$t('ai-video-gateway.me232f77e96')" :description="$t('ai-video-gateway.m65380bc657')">
    <div class="mx-auto mt-12 max-w-md rounded-xl border bg-white p-8">
      <h1 class="mb-6 text-xl font-semibold">{{ $t('ai-video-gateway.m074e7bc232') }}</h1>
      <Alert v-if="error" class="mb-4" type="error" :message="error" show-icon />
      <LoginForm /><Button type="primary" block @click="login">{{ $t('ai-video-gateway.m21f1e88275') }}</Button>
      <p class="mt-4 text-sm text-muted-foreground">{{ $t('ai-video-gateway.mb5a1061ac8') }}</p>
    </div>
  </Page>
</template>
