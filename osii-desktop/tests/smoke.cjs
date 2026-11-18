/* Run against a source shell or set OSII_DESKTOP_EXECUTABLE to a packaged app. */
'use strict';
const { _electron } = require('playwright-core');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');

async function main() {
  const temporary = process.env.OSII_SMOKE_DIRECTORY || await fs.mkdtemp(path.join(os.tmpdir(), 'OSII smoke — '));
  await fs.mkdir(temporary, { recursive: true });
  const documents = path.join(temporary, 'Documents with spaces');
  await fs.mkdir(documents, { recursive: true });
  try { await fs.writeFile(path.join(documents, 'evidence.txt'), 'Portable evidence survives restart. The calibration result was measured twice.', { flag: 'wx' }); }
  catch (error) { if (error.code !== 'EEXIST') throw error; }
  let saved = false;
  try { saved = (await fs.readdir(path.join(temporary, 'application', 'profiles'))).length > 0; } catch { /* First installation. */ }
  const errors = [];
  const options = {
    env: { ...process.env, OSII_DESKTOP_DATA_DIR: path.join(temporary, 'application') },
    timeout: 90_000,
  };
  if (process.env.OSII_DESKTOP_EXECUTABLE) options.executablePath = process.env.OSII_DESKTOP_EXECUTABLE;
  else options.args = [path.resolve(__dirname, '..')];
  let application;
  try {
    application = await _electron.launch(options);
    let page = await application.firstWindow();
    page.on('pageerror', error => errors.push(error.message));
    if (saved) {
      await page.getByRole('button', { name: /Smoke library/ }).click({ timeout: 30_000 });
    } else {
      await page.getByLabel('Library name', { exact: true }).fill('Smoke library');
      await page.getByLabel('Document folder', { exact: true }).fill(documents);
      await page.getByRole('button', { name: 'Create and open library', exact: true }).click();
    }
    await page.waitForURL(/^http:\/\/127\.0\.0\.1:\d+/, { timeout: 150_000 });
    await page.locator('#root').waitFor({ state: 'visible' });
    const api = async (route, method = 'GET', body) => page.evaluate(async ({ route, method, body }) => {
      const response = await fetch(route, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
      const value = await response.json();
      if (!response.ok) throw new Error(`${route}: ${response.status} ${JSON.stringify(value)}`);
      return value;
    }, { route, method, body });
    assert.equal((await api('/health')).status, 'ok');
    assert.equal((await api('/api/runtime')).user_authentication, false);
    const setup = await api('/api/admin/setup');
    assert.equal(setup.extraction_ready, true);
    assert.equal(setup.ai_ready, false);
    assert.ok(setup.services.some(service => service.id === 'ocr' && service.ownership === 'osii'));
    const noToken = await fetch(new URL('/health', page.url()));
    assert.equal(noToken.status, 403, 'The API must reject requests outside the Electron session');
    const run = await api('/api/runs', 'POST', { queue_paths: [documents], run_extraction: true,
      synthesizer_name: 'local.extractive-preview', enricher_name: 'local.stats-keywords', build_embeddings: false });
    const identifier = run.run_id || run.id;
    assert.ok(identifier, JSON.stringify(run));
    let finished;
    for (let attempts = 0; attempts < 100; attempts++) {
      finished = await api('/api/runs/' + identifier);
      if (['done', 'error', 'partial'].includes(finished.status)) break;
      await new Promise(resolve => setTimeout(resolve, 300));
    }
    assert.equal(finished.status, 'done', JSON.stringify(finished));
    const search = await api('/api/search', 'POST', { query: 'calibration', mode: 'lexical' });
    assert.ok(search.results.length > 0, JSON.stringify(search));
    const chat = await api('/api/chat', 'POST', { query: 'What calibration result was measured?', scope: { scope_type: 'root' } });
    assert.ok(JSON.stringify(chat).includes('calibration'), 'Offline chat must contain grounded evidence');
    await page.goto(new URL('/research', page.url()).href);
    await page.locator('#root').waitFor({ state: 'visible' });
    const output = path.resolve(__dirname, '../../output/playwright');
    await fs.mkdir(output, { recursive: true });
    await page.screenshot({ path: path.join(output, 'standalone.png'), fullPage: true });
    // Browser content cannot invoke privileged desktop operations.
    const rejected = await page.evaluate(async () => {
      try { await window.osiiDesktop.chooseFolder(); return false; } catch { return true; }
    });
    assert.equal(rejected, true);
    await application.close();
    application = undefined;
    // Reopen through the actual saved-library screen, preserving its data.
    application = await _electron.launch(options);
    page = await application.firstWindow();
    await page.getByRole('button', { name: /Smoke library/ }).click({ timeout: 30_000 });
    await page.waitForURL(/^http:\/\/127\.0\.0\.1:\d+/, { timeout: 150_000 });
    const reopened = await page.evaluate(async () => (await fetch('/api/search', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: 'calibration', mode: 'lexical' }) })).json());
    assert.ok(reopened.results.length > 0, JSON.stringify(reopened));
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ status: 'ok', checks: ['first-run', 'private-session', 'intake', 'preview', 'enrichment', 'keyword-search', 'offline-chat', 'spa-reload', 'ipc-boundary', 'restart'] }));
  } finally {
    if (application) await application.close();
    if (!process.env.OSII_SMOKE_DIRECTORY) await fs.rm(temporary, { recursive: true, force: true });
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
