import assert from 'node:assert/strict';
import { Buffer } from 'node:buffer';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

import { chromium } from 'playwright';

// Read-only local UI regression. All AI-video writes are blocked, including accidental clicks.
assert.equal(process.env.LINSIGHT_UI_E2E, '1', 'Set LINSIGHT_UI_E2E=1');
assert.ok(
  process.env.LINSIGHT_E2E_PASSWORD,
  'Provide the local login password',
);
const origin = process.env.LINSIGHT_E2E_URL || 'http://127.0.0.1:5666';
assert.ok(['127.0.0.1', 'localhost'].includes(new URL(origin).hostname));
const output = path.resolve(
  process.env.LINSIGHT_UI_OUTPUT || '../output/ui-ux',
);
await fs.mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(20_000);
page.setDefaultNavigationTimeout(30_000);
const checks = [];
const errors = [];
const blockedWrites = [];
let token;
page.on('pageerror', (error) => errors.push(error.message));
await page.route('**/admin-api/ai-video/**', async (route) => {
  if (route.request().method() !== 'GET') {
    blockedWrites.push(new URL(route.request().url()).pathname);
    await route.abort('blockedbyclient');
  } else await route.continue();
});

async function visit(route) {
  await page.goto(`${origin}/ai-video/${route}`);
  await page.locator('.ai-page').first().waitFor();
}

async function inspectDialog(dialog, name) {
  name = name.replaceAll('/', '-');
  await dialog.waitFor();
  // Screenshot fast-forwards popup transitions before collecting geometry.
  await dialog.screenshot({
    path: path.join(output, `${name}.png`),
    animations: 'disabled',
  });
  const geometry = await dialog.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const body = element.querySelector('.ai-dialog-content');
    const footer = element.querySelector('.ai-dialog-footer');
    const selects = [...element.querySelectorAll('form .ant-select')]
      .filter((select) => select.getBoundingClientRect().width > 0)
      .map((select) => ({
        width: select.clientWidth,
        parentWidth: select.parentElement.clientWidth,
      }));
    return {
      width: rect.width,
      withinViewport: rect.left >= -1 && rect.right <= window.innerWidth + 1,
      bodyOverflow: body ? body.scrollWidth - body.clientWidth : 0,
      footerVisible:
        !footer ||
        footer.getBoundingClientRect().bottom <= window.innerHeight + 1,
      selects,
    };
  });
  assert.equal(
    geometry.withinViewport,
    true,
    `${name}: dialog exceeds viewport`,
  );
  assert.ok(geometry.bodyOverflow <= 1, `${name}: horizontal overflow`);
  assert.equal(geometry.footerVisible, true, `${name}: footer is clipped`);
  for (const select of geometry.selects)
    assert.ok(
      select.width >= select.parentWidth - 4,
      `${name}: narrow form select`,
    );
  checks.push({ name, ...geometry });
  console.log(`Passed: ${name}`);
}

async function closeDialog(dialog) {
  const cancel = dialog.getByRole('button', { name: /^取\s*消$/ });
  if (await cancel.count()) await cancel.click();
  else await dialog.locator('[data-slot="sheet-close"]').click();
  await dialog.waitFor({ state: 'hidden' });
}

try {
  await page.goto(origin);
  await page
    .getByPlaceholder('请输入用户名')
    .fill(process.env.LINSIGHT_E2E_USER || 'admin');
  await page
    .getByPlaceholder('请输入密码')
    .fill(process.env.LINSIGHT_E2E_PASSWORD);
  const loginResponse = page.waitForResponse((response) =>
    response.url().endsWith('/system/auth/login'),
  );
  await page.getByRole('button', { name: 'login', exact: true }).click();
  const login = await (await loginResponse).json();
  assert.equal(login.code, 0);
  token = login.data.accessToken;
  await page.waitForURL((url) => !url.pathname.includes('/auth/'));

  await visit('camera');
  await page.getByText('全部摄像头', { exact: true }).last().waitFor();
  assert.equal(
    await page
      .locator('.vxe-header--column')
      .filter({ hasText: '识别能力' })
      .count(),
    0,
  );
  await page.getByRole('button', { name: '新增摄像头', exact: true }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('摄像头名称').waitFor();
  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 1366, height: 768 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await inspectDialog(dialog, `camera-${viewport.width}`);
  }
  await dialog.getByRole('button', { name: /^确\s*认$/ }).click();
  assert.ok(
    (await dialog.locator('[data-slot="form-message"]').count()) > 0,
    'Required-field errors remain visible',
  );
  await closeDialog(dialog);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByText('卡片', { exact: true }).click();
  await page.locator('.camera-card').first().waitFor();
  assert.equal(
    await page
      .locator('.camera-card')
      .filter({ hasText: '项识别能力' })
      .count(),
    0,
  );
  checks.push({
    name: 'camera-capabilities-removed-and-validation-retained',
    passed: true,
  });

  await visit('model');
  await page.getByText('版本与部署', { exact: true }).first().click();
  await page.getByRole('button', { name: '上传新版本', exact: true }).click();
  dialog = page.getByRole('dialog').filter({ hasText: '上传模型版本' });
  await dialog.getByLabel('版本标识').fill('ui-layout-check');
  await inspectDialog(dialog, 'model-upload-file');
  const dropzone = await dialog.locator('.ant-upload-drag').boundingBox();
  assert.ok(dropzone.width > 600, 'Upload area fills the drawer');
  await dialog.locator('input[type=file]').setInputFiles({
    name: 'layout-only.onnx',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('UI-only fixture; never uploaded'),
  });
  await dialog.getByRole('button', { name: '下一步', exact: true }).click();
  await dialog.getByLabel('来源仓库').waitFor();
  await inspectDialog(dialog, 'model-upload-metadata');
  await page.setViewportSize({ width: 390, height: 844 });
  await inspectDialog(dialog, 'model-upload-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await dialog.getByRole('button', { name: '上一步', exact: true }).click();
  await dialog.locator('.ant-upload-list-item-actions button').click();
  await dialog.getByRole('button', { name: '下一步', exact: true }).click();
  await dialog.getByLabel('版本标识').waitFor();
  assert.ok(
    (await dialog.locator('[data-slot="form-message"]').count()) > 0,
    'Removed upload must not remain in form state',
  );
  await closeDialog(dialog);

  await visit('algorithm');
  await page
    .locator('article')
    .filter({
      has: page.getByRole('heading', { name: '人员闯入', exact: true }),
    })
    .getByRole('button', { name: '配置识别', exact: true })
    .click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('配置名称').waitFor();
  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await inspectDialog(dialog, `algorithm-${viewport.width}`);
  }
  await closeDialog(dialog);
  await page.setViewportSize({ width: 1440, height: 1000 });

  for (const [route, button, title] of [
    ['rule', '新建模板', '创建规则'],
    ['integration/webhook', '新增端点', '新增 Webhook'],
    ['algorithm-validation', '记录评测', '记录视频评测'],
  ]) {
    await visit(route);
    await page.getByRole('button', { name: button, exact: true }).click();
    dialog = page.getByRole('dialog').filter({ hasText: title });
    await inspectDialog(dialog, route);
    await page.setViewportSize({ width: 390, height: 844 });
    await inspectDialog(dialog, `${route}-mobile`);
    await closeDialog(dialog);
    await page.setViewportSize({ width: 1440, height: 1000 });
  }

  await visit('node');
  await page.getByRole('button', { name: '注册令牌', exact: true }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByText('令牌仅显示一次。', { exact: false }).waitFor();
  await inspectDialog(dialog, 'node-token-warning');
  const warningGap = await dialog.evaluate((element) => {
    const alert = element.querySelector('.ant-alert').getBoundingClientRect();
    const form = element.querySelector('form').getBoundingClientRect();
    return form.top - alert.bottom;
  });
  assert.ok(
    warningGap >= 12,
    'Required warning must have spacing before the form',
  );
  checks.push({ name: 'required-warning-retained-with-spacing', warningGap });
  await closeDialog(dialog);
  await page.getByRole('button', { name: '添加网关', exact: true }).click();
  dialog = page.getByRole('dialog');
  await inspectDialog(dialog, 'node-deployment');
  await closeDialog(dialog);

  await visit('model-test');
  await page.getByText('测试参数', { exact: true }).waitFor();
  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 1366, height: 768 },
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.getByText('测试参数', { exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({
      path: path.join(output, `model-test-${viewport.width}.png`),
      animations: 'disabled',
    });
    const overflow = await page
      .locator('.model-test-layout')
      .evaluate((element) => element.scrollWidth - element.clientWidth);
    assert.ok(overflow <= 1, `Model test overflows at ${viewport.width}px`);
    checks.push({ name: `model-test-${viewport.width}`, overflow });
    await page.getByText('识别结果', { exact: true }).scrollIntoViewIfNeeded();
    const result = await page
      .getByText('识别结果', { exact: true })
      .boundingBox();
    assert.ok(
      result.y >= 0 && result.y + result.height <= viewport.height,
      'Results remain reachable by scrolling',
    );
    checks.push({
      name: `model-test-results-reachable-${viewport.width}`,
      passed: true,
    });
  }

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.route('**/ai-video/camera/page?**', (route) =>
    route.fulfill({
      json: { code: 500, msg: 'UI layout error-state fixture' },
    }),
  );
  await visit('camera');
  await page.locator('.ai-page .ant-alert-error').waitFor();
  await page.screenshot({
    path: path.join(output, 'camera-load-error.png'),
    animations: 'disabled',
  });
  await page.unroute('**/ai-video/camera/page?**');
  await page
    .locator('.ai-page .ant-alert-error')
    .getByRole('button', { name: /^重\s*试$/ })
    .click();
  await page.locator('.ai-page .ant-alert-error').waitFor({ state: 'hidden' });
  checks.push({ name: 'load-error-visible-and-retry-recovers', passed: true });

  assert.deepEqual(blockedWrites, [], 'No AI-video write was attempted');
  assert.deepEqual(errors, [], 'No browser runtime errors');
  await fs.writeFile(
    path.join(output, 'results.json'),
    JSON.stringify(
      { checkedAt: new Date().toISOString(), checks, errors, blockedWrites },
      null,
      2,
    ),
  );
  console.log(
    `UI layout regression passed: ${checks.length} checks; no AI-video writes or browser errors.`,
  );
} finally {
  try {
    if (token)
      await page.request.post(`${origin}/admin-api/system/auth/logout`, {
        headers: { Authorization: `Bearer ${token}`, 'tenant-id': '1' },
        timeout: 10_000,
      });
  } finally {
    await browser.close();
  }
}
