import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import process from 'node:process';

import { chromium } from 'playwright';

// All admin APIs (including authentication) are isolated fixtures. Never changes a real task.
const origin = process.env.LINSIGHT_E2E_URL || 'http://127.0.0.1:5666';
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
const errors = [];
const requests = [];
const records = [];
let permissions = ['ai-video:task:query', 'ai-video:task:update'];
let failList = false;
let failSave = false;
const task = {
  id: 101,
  name: '开发者评测任务',
  configVersion: 7,
  gatewayRevision: 4,
  pipelineVersionId: 31,
  algorithmId: 9,
  modelVersionId: 51,
  nodeId: 11,
  actualStatus: 'STOPPED',
};
const envelope = (data) => ({ code: 0, msg: '', data });
page.on('pageerror', (error) => errors.push(error.message));
await page.route('**/admin-api/**', async (route) => {
  const request = route.request();
  const url = new URL(request.url());
  const path = url.pathname.replace('/admin-api', '');
  requests.push({ path, method: request.method(), body: request.postData() });
  let data = [];
  if (path === '/system/auth/login')
    data = {
      accessToken: 'e2e-only',
      refreshToken: 'e2e-only',
      userId: 1,
      expiresTime: Date.now() + 3600000,
    };
  else if (path === '/system/tenant/simple-list')
    data = [{ id: 1, name: '隔离测试租户' }];
  else if (path === '/system/tenant/get-by-website')
    data = { id: 1, name: '隔离测试租户' };
  else if (path === '/system/auth/get-permission-info')
    data = {
      user: {
        id: 1,
        username: 'tester',
        nickname: '评测测试员',
        homePath: '/ai-video/algorithm-validation',
      },
      roles: ['tester'],
      permissions,
      menus: [
        {
          id: 7150,
          name: 'AI 能力',
          parentId: 0,
          path: '/ai-center',
          visible: true,
          children: [
            {
              id: 7140,
              parentId: 7150,
              name: '视频评测记录',
              path: '/ai-video/algorithm-validation',
              component: 'ai-video/algorithm-validation/index',
              componentName: 'AiVideoAlgorithmValidation',
              visible: true,
            },
          ],
        },
      ],
    };
  else if (path === '/ai-video/task/page') data = { list: [task], total: 1 };
  else if (path === '/ai-video/task/get') data = task;
  else if (path === '/ai-video/task/evaluation/page') {
    if (failList)
      return route.fulfill({ json: { code: 500, msg: '列表故障注入' } });
    const list = records.filter(
      (record) =>
        !url.searchParams.get('status') ||
        record.status === url.searchParams.get('status'),
    );
    data = { list, total: list.length };
  } else if (path === '/ai-video/task/evaluation/create') {
    if (failSave)
      return route.fulfill({
        json: { code: 500, msg: '保存故障注入，请重试' },
      });
    const measurement = request.postDataJSON();
    const failedChecks =
      measurement.metrics.endToEndP95Ms >
      measurement.thresholds.maxEndToEndP95Ms
        ? ['endToEndP95Ms']
        : [];
    data = 100 + records.length;
    records.unshift({
      id: data,
      taskId: task.id,
      taskName: task.name,
      configVersion: 7,
      source: 'MANUAL_VIDEO',
      status: failedChecks.length ? 'FAIL' : 'PASS',
      failedChecks,
      ...measurement,
      measurement,
      createTime: Date.now(),
      creator: 'tester',
      configurationSnapshot: {
        schemaVersion: '1.0',
        pipeline: { pipelineVersionId: 31 },
        models: [{ modelVersionId: 51, sha256: 'b'.repeat(64) }],
        gatewayRevision: 4,
        gatewayConfiguration: { rule: { schemaVersion: '1.0' } },
      },
    });
  } else if (path === '/ai-video/task/evaluation/get')
    data = records.find(
      (record) => record.id === Number(url.searchParams.get('id')),
    );
  return route.fulfill({ json: envelope(data) });
});
await fs.mkdir('../output/developer-foundation', { recursive: true });
async function closeDrawer(title) {
  const dialog = page.getByRole('dialog').filter({ hasText: title });
  await dialog.locator('[data-slot="sheet-close"]').click();
}
try {
  await page.goto(origin);
  await page.getByPlaceholder('请输入用户名').fill('tester');
  await page.getByPlaceholder('请输入密码').fill('fixture-password');
  await page.getByRole('button', { name: 'login', exact: true }).click();
  await page
    .locator('.ant-empty-description:visible')
    .filter({ hasText: '暂无评测记录' })
    .waitFor();
  await page.getByRole('button', { name: 'SDK 快速入门', exact: true }).click();
  await page
    .getByText('python -m ai_runtime.sdk init', { exact: false })
    .waitFor();
  await closeDrawer('SDK 快速入门');
  await page.getByRole('button', { name: '记录评测', exact: true }).click();
  await page.getByLabel('测试任务').click();
  await page.getByText('开发者评测任务 (#101)', { exact: true }).click();
  await page.getByText('配置 v7', { exact: false }).waitFor();
  const values = {
    测试集版本: 'video-fixture-v1',
    '测试集 SHA256': 'a'.repeat(64),
    证据引用: 'reports/run-001.json',
    实测环境: '浏览器回归 fixture；不代表现场实测',
    事件准确率: '0.95',
    事件召回率: '0.95',
    每路每小时误报: '0.2',
    漏报事件数: '0',
    '端到端 P95（ms）': '8500',
    '平均分析 FPS': '1',
    'CPU 峰值（%）': '40',
    '内存峰值（MiB）': '120',
    '加速器显存峰值（MiB）': '0',
  };
  for (const [label, value] of Object.entries(values))
    await page.getByLabel(label).fill(value);
  await page.getByRole('switch').click();
  failSave = true;
  await page.getByRole('button', { name: '保存记录', exact: true }).click();
  await page.getByText('保存未完成', { exact: false }).waitFor();
  const firstAttempt = requests.findLast((request) =>
    request.path.endsWith('/evaluation/create'),
  );
  failSave = false;
  await page.getByRole('button', { name: '保存记录', exact: true }).click();
  await page
    .getByRole('button', { name: '导出评测 JSON', exact: true })
    .waitFor();
  const attempts = requests.filter((request) =>
    request.path.endsWith('/evaluation/create'),
  );
  assert.deepEqual(
    JSON.parse(firstAttempt.body),
    JSON.parse(attempts.at(-1).body),
  );
  assert.equal(records.length, 1);
  assert.equal(records[0].measurement.expectedConfigVersion, 7);
  assert.equal(records[0].measurement.expectedGatewayRevision, 4);
  assert.equal(records[0].measurement.metrics.endToEndP95Ms, 8500);
  assert.equal(records[0].status, 'FAIL');
  const downloadEvent = page.waitForEvent('download');
  await page
    .getByRole('button', { name: '导出评测 JSON', exact: true })
    .click();
  const download = await downloadEvent;
  await download.saveAs('../output/developer-foundation/evaluation.json');
  const report = JSON.parse(
    await fs.readFile('../output/developer-foundation/evaluation.json', 'utf8'),
  );
  assert.equal(report.configurationSnapshot.pipeline.pipelineVersionId, 31);
  await page.waitForFunction(
    () => document.querySelectorAll('.ant-message-notice').length === 0,
  );
  await page.screenshot({
    path: '../output/developer-foundation/evaluation-detail.png',
    fullPage: true,
  });
  await closeDrawer('视频评测详情');
  await page.reload();
  await page.getByText('video-fixture-v1', { exact: true }).waitFor();
  failList = true;
  await page.reload();
  await page.getByText('评测历史加载失败，请检查连接后重试。').waitFor();
  failList = false;
  await page.getByRole('button', { name: /^重\s*试$/ }).click();
  await page.getByText('video-fixture-v1', { exact: true }).waitFor();
  permissions = ['ai-video:task:query'];
  await page.reload();
  await page.getByText('video-fixture-v1', { exact: true }).waitFor();
  assert.equal(
    await page.getByRole('button', { name: '记录评测', exact: true }).count(),
    0,
  );
  permissions = [];
  await page.reload();
  await page.getByText('需要任务查询权限才能查看评测记录。').waitFor();
  assert.equal(
    requests.filter(
      (request) =>
        request.path.includes('/algorithm/') && request.method !== 'GET',
    ).length,
    0,
  );
  assert.deepEqual(errors, []);
  console.log(
    'PASS: isolated Vben UI quickstart, empty, save retry/idempotency, failed metrics, snapshots/export, history, error recovery and permissions',
  );
} catch (error) {
  await page.screenshot({
    path: '../output/developer-foundation/evaluation-error.png',
    fullPage: true,
  });
  console.log((await page.locator('body').innerText()).slice(-7000));
  console.log(errors);
  throw error;
} finally {
  await browser.close();
}
