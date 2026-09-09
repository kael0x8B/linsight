// Real browser / real Vben components; only node business calls are isolated fixtures.
// No SSH connection, host power action, or node deletion is issued to a real device.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
const origin = process.env.LINSIGHT_E2E_URL || 'http://127.0.0.1:5666';
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const node = { id: 991, code: 'e2e-edge', name: 'E2E 隔离边缘节点', ipAddress: 'edge.test', status: 0, onlineStatus: 1, agentVersion: 'v1',
  resourceSnapshot: JSON.stringify({ runtimeStatus: 'UP', activationGuard: 'v1', agentRollbackAvailable: true }), taskCount: 0, modelCount: 0 };
const envelope = data => ({ code: 0, msg: '', data });
let polls = 0, created, logCalls = [], historyCalls = [], failPreflight = false;
const deployment = { id: 9991, host: 'edge.test', port: 22, username: 'linaro', nodeCode: node.code, nodeName: node.name, operationType: 'REDEPLOY',
  targetVersion: 'source-e2e123456789', previousVersion: 'v1',
  createTime: Date.now(), updateTime: Date.now(), logStatus: 'COLLECTING', logTruncated: false, stage: 'INSTALLING', progress: 55, status: 'RUNNING' };
await page.route('**/admin-api/ai-video/node/**', async route => {
  const path = new URL(route.request().url()).pathname;
  let data;
  if (path.endsWith('/node/list')) data = [node];
  else if (path.endsWith('/deployment/preflight')) {
    if (failPreflight) return route.fulfill({ json: { code: 1020006042, msg: '测试预检失败，可重新输入' } });
    data = { hostKey: 'test-key', hostKeyType: 'ssh-ed25519', hostKeyFingerprint: 'SHA256:test-fixture',
      architecture: 'aarch64', osSummary: 'Ubuntu 24.04', pythonVersion: '3.12.3', pythonSupported: true, sudoAvailable: true, ffmpegInstalled: true,
      memoryMb: 4096, memoryAvailableMb: 2048, diskAvailableMb: 8192, supported: true, warnings: [], existingNodeId: node.id,
      existingNodeCode: node.code, existingNodeName: node.name, controlPlaneUrl: 'http://control.test:48888', currentVersion: 'v1' };
  } else if (path.endsWith('/deployment/create')) { created = route.request().postDataJSON(); data = deployment.id; }
  else if (path.endsWith('/deployment/get')) {
    polls++;
    data = { ...deployment, status: polls >= 3 ? 'SUCCEEDED' : 'RUNNING', stage: polls >= 3 ? 'COMPLETED' : 'INSTALLING',
      progress: polls >= 3 ? 100 : 55 + polls * 10, logStatus: polls >= 3 ? 'COMPLETE' : 'COLLECTING', outputLog: '[SSH] 安装输出 ' + polls + '\n' };
  } else if (path.endsWith('/deployment/page')) {
    historyCalls.push(Object.fromEntries(new URL(route.request().url()).searchParams));
    data = { list: Array.from({ length: 50 }, (_, index) => ({ ...deployment, id: deployment.id - index, status: 'SUCCEEDED', logStatus: 'COMPLETE' })), total: 80 };
  }
  else if (path.endsWith('/command/list') || path.endsWith('/upgrade/list')) data = [];
  else return route.continue();
  return route.fulfill({ json: envelope(data) });
});
await page.route('**/admin-api/ai-video/node-log/**', async route => {
  const url = new URL(route.request().url());
  if (url.pathname.endsWith('/snapshot')) return route.fulfill({ json: envelope(100) });
  if (!url.pathname.endsWith('/page')) return route.continue();
  logCalls.push(Object.fromEntries(url.searchParams));
  const after = url.searchParams.get('afterId');
  const pageNo = Number(url.searchParams.get('pageNo') || 1);
  const list = after ? [{ id: 101, nodeId: 991, level: 'INFO', component: 'agent', loggedAt: Date.now(), message: '新增日志 101' }]
    : Array.from({ length: 20 }, (_, index) => ({ id: 101 - pageNo * 20 + 19 - index, nodeId: 991, level: 'INFO', component: 'agent',
      loggedAt: Date.now() - index * 1000, message: '历史日志 ' + pageNo + '-' + index }));
  return route.fulfill({ json: envelope({ list, total: after ? list.length : 60 }) });
});
try {
  await page.goto(origin);
  await page.getByPlaceholder('请输入用户名').fill(process.env.LINSIGHT_E2E_USER || 'admin');
  await page.getByPlaceholder('请输入密码').fill(process.env.LINSIGHT_E2E_PASSWORD || 'admin123');
  await page.getByRole('button', { name: 'login', exact: true }).click();
  await page.waitForURL(url => !url.pathname.includes('/auth'), { timeout: 20000 });
  console.log('Login completed:', page.url());
  await page.goto(origin + '/ai-video/node');
  await page.getByText(node.name, { exact: true }).first().waitFor();
  console.log('Node fixture loaded');
  await page.getByRole('button', { name: '部署新节点', exact: true }).first().click();
  await page.getByPlaceholder('例如 192.168.2.17').fill('edge.test');
  await page.getByPlaceholder('例如 linaro').fill('linaro');
  await page.getByPlaceholder('仅用于本次预检和部署，不会保存').fill('e2e-not-a-real-password');
  await page.getByRole('button', { name: '检测连接', exact: true }).click();
  await page.getByText('环境满足自动部署基线', { exact: true }).waitFor({ timeout: 5000 });
  await page.getByRole('button', { name: '开始在线升级', exact: true }).waitFor({ state: 'visible' });
  await page.getByText('我已确认这是目标网关的主机指纹', { exact: true }).click();
  await page.getByRole('button', { name: '开始在线升级', exact: true }).click();
  await page.getByText('[SSH] 安装输出 1', { exact: false }).waitFor({ timeout: 6000 });
  assert.equal(created.nodeId, 991);
  assert.ok(created.requestId);
  await page.getByText('[SSH] 安装输出 3', { exact: false }).waitFor({ timeout: 7000 });
  await page.screenshot({ path: '../artifacts/node-module-wizard-20260906.png', fullPage: true });
  await page.getByRole('button', { name: /完\s*成/, exact: true }).click();
  console.log('PASS: real Vben wizard preflight -> configuration -> live SSH output -> terminal state; target identity and request ID retained');
  await page.getByRole('button', { name: '部署记录', exact: true }).click();
  await page.getByText('最新 50 条部署记录', { exact: true }).waitFor();
  assert.equal(await page.locator('.deployment-record').count(), 50);
  assert.equal(historyCalls.at(-1).pageSize, '50');
  assert.equal(historyCalls.at(-1).pageNo, '1');
  await page.screenshot({ path: '../artifacts/node-deployment-cards-20260906.png', fullPage: true, animations: 'disabled' });
  await page.locator('.deployment-record').first().click();
  await page.getByText('[SSH] 安装输出', { exact: false }).waitFor();
  console.log('PASS: reopening persisted deployment details renders SSH output');
  await page.goto(origin + '/ai-video/node/991/logs');
  await page.getByText('历史日志 1-0', { exact: true }).waitFor();
  await page.clock.install();
  const before = logCalls.length;
  await page.clock.runFor(11000);
  await page.getByText('新增日志 101', { exact: true }).waitFor();
  assert.equal(logCalls.length, before + 1);
  assert.equal(logCalls.at(-1).afterId, '100');
  await page.locator('.vxe-pager--next-btn').click();
  await page.getByText('历史日志 2-0', { exact: true }).waitFor();
  const historicalCalls = logCalls.length;
  await page.clock.runFor(30000);
  assert.equal(logCalls.length, historicalCalls);
  assert.ok(logCalls.at(-1).snapshotMaxId);
  await page.screenshot({ path: '../artifacts/node-module-logs-20260906.png', fullPage: true });
  console.log('PASS: latest logs use one incremental request; historical page remains frozen across three poll periods');
  assert.deepEqual(errors, []);
} catch (error) {
  console.error('Browser state:', page.url(), (await page.locator('body').innerText()).slice(0, 3500));
  await page.screenshot({ path: '../artifacts/node-module-e2e-failure.png', fullPage: true });
  throw error;
} finally { await page.clock.resume().catch(() => {}); await browser.close(); }
