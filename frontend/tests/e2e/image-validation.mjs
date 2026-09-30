import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import fs from 'node:fs/promises';

// Isolated Runtime with a real ONNX contract model on port 18903; no deployed node is changed.
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const errors = [];
const setName = `现场图片回归集-${Date.now()}`;
page.on('pageerror', error => errors.push(error.message));
await page.route('**/gateway-api/**', async route => {
  if (route.request().url().endsWith('/session')) return route.fulfill({ json: { ok: true } });
  if (!route.request().url().endsWith('/rpc')) return route.fulfill({ json: { ok: true } });
  const payload = route.request().postDataJSON();
  if (payload.action === 'events') return route.fulfill({ json: { ok: true, data: { list: [], total: 0 } } });
  if (!payload.action.startsWith('validation.') && payload.action !== 'snapshot') return route.fulfill({ json: { ok: true, data: [] } });
  const response = await fetch('http://127.0.0.1:18903/v1/gateway/rpc', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  await route.fulfill({ status: response.status, contentType: 'application/json', body: await response.text() });
});
try {
  await page.goto('http://localhost:5666/gateway.html');
  await page.getByRole('button', { name: '图片识别', exact: true }).click();
  await page.getByRole('button', { name: '算法验证集', exact: true }).click();
  await page.getByRole('button', { name: '新建验证集', exact: true }).click();
  await page.getByLabel('验证集名称').fill(setName);
  await page.getByRole('button', { name: '确 认', exact: true }).click();
  await page.waitForTimeout(300);
  await page.screenshot({ path: '../output/image-validation/initial.png', fullPage: true });
  const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAUAAAAC0CAIAAABqhmJGAAACKUlEQVR4nO3TMQ0AIQDAQHgNzMz4V/geWEiTOwVdOtc+A2j6XgcA9wwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBobR9QN0qQHCEjMpeAAAAABJRU5ErkJggg==', 'base64');
  await page.locator('input[type=file]').last().setInputFiles([
    { name: '应有人.png', mimeType: 'image/png', buffer: image },
    { name: '不应有人.png', mimeType: 'image/png', buffer: image },
  ]);
  await page.getByText('不应有人.png', { exact: true }).waitFor();
  await page.getByRole('button', { name: '编辑期望', exact: true }).first().click();
  await page.getByLabel('期望类别', { exact: true }).fill('person');
  await page.getByRole('spinbutton').first().fill('1');
  await page.getByLabel('备注', { exact: true }).fill('应检出一个人员');
  await page.getByRole('button', { name: '确 认', exact: true }).click();
  await page.getByRole('button', { name: '运行验证集', exact: true }).click();
  await page.getByText('2 / 2', { exact: true }).waitFor();
  assert.equal(await page.getByText('通过 1', { exact: true }).count(), 1);
  assert.equal(await page.getByText('失败 1', { exact: true }).count(), 1);
  await page.getByRole('button', { name: '查看', exact: true }).first().click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: '../output/image-validation/results.png', fullPage: true });
  const downloadReady = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出验证报告', exact: true }).click();
  const download = await downloadReady;
  await download.saveAs('../output/image-validation/report.html');
  const report = await fs.readFile('../output/image-validation/report.html', 'utf8');
  assert.match(report, /ONNX/);
  assert.match(report, /通过: 1/);
  assert.match(report, /失败: 1/);
  assert.match(report, /<rect/);
  await page.reload();
  await page.getByRole('button', { name: '图片识别', exact: true }).click();
  await page.getByRole('button', { name: '算法验证集', exact: true }).click();
  await page.locator('[aria-label="选择验证集"]').click();
  await page.getByText(setName, { exact: true }).click();
  await page.locator('[aria-label="历史运行"]').click();
  await page.locator('.ant-select-dropdown:visible .ant-select-item-option-content').filter({ hasText: '版本 4' }).click();
  await page.getByText('通过 1', { exact: true }).waitFor();
  await page.getByRole('button', { name: '查看', exact: true }).first().click();
  await page.waitForTimeout(300);
  assert.deepEqual(errors, []);
  console.log('PASS: real Vben UI, batch upload, expectation edit, real ONNX pass/fail, overlay and report download');
} catch (error) {
  await page.screenshot({ path: '../output/image-validation/error.png', fullPage: true });
  console.log((await page.locator('body').innerText()).slice(-9000));
  console.log(errors);
  throw error;
} finally { await browser.close(); }
