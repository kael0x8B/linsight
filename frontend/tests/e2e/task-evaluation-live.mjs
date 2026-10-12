import assert from 'node:assert/strict';
import { createHash, randomUUID } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

import { chromium } from 'playwright';

// Opt-in only: writes an explicitly labelled manual evaluation to a local test task.
assert.equal(process.env.LINSIGHT_LIVE_E2E, '1', 'Set LINSIGHT_LIVE_E2E=1');
assert.ok(
  process.env.LINSIGHT_E2E_PASSWORD,
  'Provide the local login password',
);
assert.ok(process.env.LINSIGHT_E2E_STATE, 'Provide the local E2E state JSON');
const statePath = path.resolve(process.env.LINSIGHT_E2E_STATE);
const output = path.dirname(statePath);
const state = JSON.parse(await fs.readFile(statePath, 'utf8'));
const origin = process.env.LINSIGHT_E2E_URL || 'http://127.0.0.1:5666';
assert.ok(['127.0.0.1', 'localhost'].includes(new URL(origin).hostname));
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
page.setDefaultTimeout(20_000);
page.setDefaultNavigationTimeout(30_000);
const errors = [];
const mutations = [];
const attempts = [];
let token;
let firstRecordId;
page.on('pageerror', (error) => errors.push(error.message));
page.on('request', (request) => {
  if (request.url().includes('/ai-video/') && request.method() !== 'GET') {
    mutations.push(new URL(request.url()).pathname);
  }
});
async function api(method, endpoint, data, headers = {}) {
  const response = await page.request.fetch(`${origin}/admin-api${endpoint}`, {
    method,
    data,
    headers: { Authorization: `Bearer ${token}`, 'tenant-id': '1', ...headers },
  });
  return response.json();
}
async function closeDrawer(title) {
  await page
    .getByRole('dialog')
    .filter({ hasText: title })
    .locator('[data-slot="sheet-close"]')
    .click();
}
try {
  await page.goto(origin);
  await page
    .getByPlaceholder('请输入用户名')
    .fill(process.env.LINSIGHT_E2E_USER || 'admin');
  await page
    .getByPlaceholder('请输入密码')
    .fill(process.env.LINSIGHT_E2E_PASSWORD);
  const loginResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith('/system/auth/login') &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'login', exact: true }).click();
  const login = await (await loginResponse).json();
  assert.equal(login.code, 0);
  token = login.data.accessToken;
  await page.waitForURL((url) => !url.pathname.includes('/auth/'));
  console.log('Live login passed');

  // Gateway recovery can briefly report RUNNING before the intentional fault recurs.
  let task;
  for (let attempt = 0; attempt < 20; attempt++) {
    task = (await api('GET', `/ai-video/task/get?id=${state.taskId}`)).data;
    if (task.errorCode === 'ALGORITHM_PROCESS_FAILED') break;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  assert.ok(
    task.code.startsWith('developer-e2e-'),
    'Only use a dedicated test task',
  );
  assert.equal(task.nodeId, state.nodeId);
  assert.equal(task.errorCode, 'ALGORITHM_PROCESS_FAILED');
  await page.goto(`${origin}/ai-video/task`);
  await page
    .locator('.task-name:visible')
    .filter({ hasText: task.name })
    .first()
    .waitFor();
  await page.getByRole('button', { name: '监控', exact: true }).first().click();
  console.log('Opened task monitor');
  await page.getByText('processor.py:4 (process)', { exact: true }).waitFor();
  await page.getByText(/处理帧 · ALGORITHM_PROCESS_FAILED/).waitFor();
  await page.waitForFunction(() => {
    const drawer = document.querySelector(
      '.ant-drawer-open .ant-drawer-content-wrapper',
    );
    return (
      drawer && drawer.getBoundingClientRect().right <= window.innerWidth + 1
    );
  });
  await page.screenshot({
    path: path.join(output, 'live-diagnostic.png'),
    fullPage: true,
  });

  await page.goto(`${origin}/ai-video/algorithm-validation`);
  await page.getByRole('button', { name: 'SDK 快速入门', exact: true }).click();
  await page
    .getByText('python -m ai_runtime.sdk init', { exact: false })
    .waitFor();
  await closeDrawer('SDK 快速入门');
  await page.getByRole('button', { name: '记录评测', exact: true }).click();
  await page.getByLabel('测试任务').click();
  await page
    .getByText(`${task.name} (#${state.taskId})`, { exact: true })
    .click();
  await page
    .getByText(`配置 v${task.configVersion}`, { exact: false })
    .waitFor();
  const dataset = `local-api-boundary-${Date.now()}`;
  const datasetHash = createHash('sha256')
    .update(await fs.readFile(path.join(output, 'sdk-result.json')))
    .digest('hex');
  const values = {
    测试集版本: dataset,
    '测试集 SHA256': datasetHash,
    证据引用: 'output/developer-foundation/live/task-diagnostic.json',
    实测环境: '本地 E2E：真实 Java/MySQL/Runtime/Agent/ONNX 与 RTSP 测试图；下列指标为接口边界样本，不代表模型准确率或现场实测。',
    事件准确率: '0.95',
    事件召回率: '0.95',
    每路每小时误报: '0.2',
    漏报事件数: '0',
    '端到端 P95（ms）': '8500',
    '平均分析 FPS': '0',
    'CPU 峰值（%）': '40',
    '内存峰值（MiB）': '120',
    '加速器显存峰值（MiB）': '0',
    备注: 'E2E_BOUNDARY_FIXTURE：验证高延迟、零 FPS、幂等、版本快照；禁止作为生产验收数据。',
  };
  for (const [label, value] of Object.entries(values))
    await page.getByLabel(label).fill(value);
  await page.getByRole('switch').click();
  // The real server commits first; discard only its first response to exercise lost-response retry.
  await page.route('**/ai-video/task/evaluation/create', async (route) => {
    attempts.push(route.request().postDataJSON());
    const response = await route.fetch();
    const result = await response.json();
    assert.equal(result.code, 0, result.msg);
    if (firstRecordId === undefined) {
      firstRecordId = result.data;
      await route.abort('failed');
    } else {
      assert.equal(result.data, firstRecordId);
      await route.fulfill({ response });
    }
  });
  await page.getByRole('button', { name: '保存记录', exact: true }).click();
  await page.getByText('保存未完成', { exact: false }).waitFor();
  await page.getByRole('button', { name: '保存记录', exact: true }).click();
  await page
    .getByRole('button', { name: '导出评测 JSON', exact: true })
    .waitFor();
  assert.equal(attempts.length, 2);
  assert.deepEqual(attempts[0], attempts[1]);
  const downloadEvent = page.waitForEvent('download');
  await page
    .getByRole('button', { name: '导出评测 JSON', exact: true })
    .click();
  await (await downloadEvent).saveAs(path.join(output, 'live-evaluation.json'));
  const record = JSON.parse(
    await fs.readFile(path.join(output, 'live-evaluation.json'), 'utf8'),
  );
  assert.equal(record.id, firstRecordId);
  assert.equal(record.status, 'FAIL');
  assert.deepEqual(record.failedChecks, ['endToEndP95Ms', 'averageFps']);
  assert.equal(
    record.configurationSnapshot.pipeline.pipelineVersionId,
    state.diagnosticPackage.pipelineVersionId,
  );
  assert.equal(
    record.configurationSnapshot.configurationSource,
    'GATEWAY_REPORTED_AT_RECORDING',
  );
  assert.equal(
    record.configurationSnapshot.gatewayRevision,
    task.gatewayRevision,
  );
  assert.equal(record.configurationSnapshot.models[0].modelVersionId, 18);
  await page.waitForFunction(
    () => document.querySelectorAll('.ant-message-notice').length === 0,
  );
  await page.screenshot({
    path: path.join(output, 'live-evaluation.png'),
    fullPage: true,
  });
  await closeDrawer('视频评测详情');
  await page.reload();
  await page.getByText(dataset, { exact: true }).waitFor();
  const listed = await api(
    'GET',
    `/ai-video/task/evaluation/page?pageNo=1&pageSize=100&taskId=${state.taskId}`,
  );
  assert.equal(
    listed.data.list.filter((row) => row.id === firstRecordId).length,
    1,
  );
  const conflict = await api('POST', '/ai-video/task/evaluation/create', {
    ...attempts[0],
    note: 'changed-body',
  });
  assert.equal(conflict.code, 1_020_003_013);
  const stale = await api('POST', '/ai-video/task/evaluation/create', {
    ...attempts[0],
    requestId: randomUUID(),
    expectedConfigVersion: task.configVersion + 1,
  });
  assert.equal(stale.code, 1_020_003_012);
  const denied = await api(
    'GET',
    `/ai-video/task/evaluation/get?id=${firstRecordId}`,
    undefined,
    { 'tenant-id': '2' },
  );
  assert.equal(denied.code, 403);
  assert.ok(!mutations.some((url) => url.includes('/algorithm/')));
  assert.deepEqual(errors, []);
  await fs.writeFile(
    path.join(output, 'browser-result.json'),
    JSON.stringify(
      {
        status: 'PASS',
        recordId: firstRecordId,
        taskId: state.taskId,
        dataset,
        duplicateAttempts: attempts.length,
        conflictCode: conflict.code,
        staleCode: stale.code,
        crossTenantCode: denied.code,
        pipelineMutations: 0,
        pageErrors: errors,
      },
      null,
      2,
    ),
  );
  console.log(
    `PASS: real login, diagnostic UI, SDK guide, MySQL record #${firstRecordId}, lost-response retry, immutable export/history, stale/conflict/tenant rejection`,
  );
} catch (error) {
  await page.screenshot({
    path: path.join(output, 'live-browser-error.png'),
    fullPage: true,
  });
  console.log((await page.locator('body').innerText()).slice(-5000));
  throw error;
} finally {
  await browser.close();
}
