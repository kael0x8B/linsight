import assert from 'node:assert/strict';
import { chromium } from 'playwright';

// Use only an isolated environment restored by platform-snapshot-roundtrip.py.
const origin = process.env.LINSIGHT_E2E_URL || 'http://127.0.0.1:5681';
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
try {
  await page.goto(origin);
  await page.getByPlaceholder('请输入用户名').fill('admin');
  await page.getByPlaceholder('请输入密码').fill('admin123');
  await page.getByRole('button', { name: 'login', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.includes('/auth'), { timeout: 30_000 });
  await page.goto(`${origin}/ai-video/model`);
  const modelsReady = page.waitForResponse((r) => r.url().includes('/ai-video/model/executable-options') && r.ok());
  await page.getByRole('button', { name: '查看可部署模型', exact: true }).click();
  const models = await (await modelsReady).json();
  assert.equal(models.code, 0);
  assert.equal(models.data.length, 15);
  assert.equal(await page.getByText('暂无符合条件的可部署模型', { exact: false }).count(), 0);
  console.log('PASS: model center has 15 deployable versions');

  await page.goto(`${origin}/ai-video/algorithm`);
  await page.getByText('共 24 个算法', { exact: true }).waitFor();
  for (const [route, total] of [['rule', 18], ['task', 9]]) {
    const responseReady = page.waitForResponse((r) => r.url().includes(`/ai-video/${route}/page?`) && r.ok());
    await page.goto(`${origin}/ai-video/${route}`);
    const response = await (await responseReady).json();
    assert.equal(response.code, 0);
    assert.equal(response.data.total, total);
  }
  console.log('PASS: 24 algorithms, 18 rules, 9 AI tasks');

  await page.goto(`${origin}/ai-video/node`);
  const configurationReady = page.waitForResponse((r) => r.url().includes('/application-release/configuration') && r.ok());
  await page.getByRole('button', { name: '盒子升级包', exact: true }).click();
  const configuration = await (await configurationReady).json();
  assert.equal(configuration.data.ready, true);
  await page.getByRole('button', { name: '生成升级包', exact: true }).click();
  const version = `snapshot-check-${Date.now()}`;
  await page.getByPlaceholder('1.0.6').fill(version);
  await page.locator('textarea').fill('业务快照交付验证：中文说明、中文及空格目录、离线依赖。');
  const created = page.waitForResponse((r) => r.url().includes('/application-release/create') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '生成升级包', exact: true }).last().click();
  const result = await (await created).json();
  assert.equal(result.code, 0);
  await page.getByText('已完成', { exact: true }).first().waitFor({ timeout: 180_000 });
  await page.getByRole('button', { name: '下载升级包', exact: true }).first().waitFor();
  if (process.env.LINSIGHT_E2E_SCREENSHOT) await page.screenshot({ path: process.env.LINSIGHT_E2E_SCREENSHOT, fullPage: true });
  assert.deepEqual(errors, []);
  console.log(`PASS: upgrade package ${version} generated successfully from UI; record=${result.data}`);
} finally {
  await browser.close();
}
