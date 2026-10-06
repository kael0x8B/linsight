import assert from 'node:assert/strict';
import { chromium } from 'playwright';

// Run against the isolated database initialized by model-assets-roundtrip.sh.
const origin = process.env.LINSIGHT_E2E_URL || 'http://127.0.0.1:5667';
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
  const responseReady = page.waitForResponse((response) =>
    response.url().includes('/ai-video/model/page?') && response.ok());
  await page.goto(`${origin}/ai-video/model`);
  const response = await (await responseReady).json();
  assert.equal(response.code, 0);
  assert.ok(response.data.list.length > 0, 'fresh database must show imported model assets');
  const firstModel = response.data.list[0].name;
  await page.getByText(firstModel, { exact: true }).first().waitFor();
  await page.getByRole('button', { name: '查看可部署模型', exact: true }).click();
  await page.getByText('暂无符合条件的可部署模型，可到模型资产与历史版本上传、测试和发布', { exact: true }).waitFor();
  await page.getByRole('button', { name: '模型资产与历史版本', exact: true }).click();
  await page.getByText(firstModel, { exact: true }).first().waitFor();
  if (process.env.LINSIGHT_E2E_SCREENSHOT) {
    await page.screenshot({ path: process.env.LINSIGHT_E2E_SCREENSHOT, fullPage: true });
  }
  assert.deepEqual(errors, []);
  console.log('PASS: fresh model assets are visible by default; execution evidence stays local to the target environment');
} finally {
  await browser.close();
}
