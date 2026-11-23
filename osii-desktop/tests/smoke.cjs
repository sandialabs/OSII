/* Run against a source shell or set OSII_DESKTOP_EXECUTABLE to a packaged app. */
'use strict';
const { _electron } = require('playwright-core');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

function windowsProcessMemory(rootId) {
  // Measure the installed desktop and its descendants, excluding the test driver.
  const script = `$owned = @(${Number(rootId)}); $all = Get-CimInstance Win32_Process; do { $next = @($all | Where-Object { $_.ParentProcessId -in $owned -and $_.ProcessId -notin $owned } | ForEach-Object { [int]$_.ProcessId }); $owned += $next } while ($next.Count); $processes = @(Get-Process -Id $owned -ErrorAction SilentlyContinue); @{ processCount = $processes.Count; workingSetBytes = ($processes | Measure-Object WorkingSet64 -Sum).Sum; privateBytes = ($processes | Measure-Object PrivateMemorySize64 -Sum).Sum } | ConvertTo-Json -Compress`;
  const powershell = path.join(process.env.SystemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
  return JSON.parse(execFileSync(powershell, ['-NoProfile', '-NonInteractive', '-Command', script],
    { encoding: 'utf8', windowsHide: true, timeout: 30_000 }));
}

async function main() {
  const useEmbeddingGemma = Boolean(process.env.OSII_DESKTOP_EXECUTABLE || process.env.OSII_SMOKE_BUNDLED_EMBEDDING);
  const semanticQuery = 'How do I keep perishables cold on the road?';
  function assertSemanticMatch(results) {
    assert.equal(results.retrieval_mode_used, 'semantic', JSON.stringify(results));
    assert.equal(results.results[0]?.filename, 'evidence.txt', JSON.stringify(results));
  }
  const temporary = process.env.OSII_SMOKE_DIRECTORY || await fs.mkdtemp(path.join(os.tmpdir(), 'OSII smoke — '));
  await fs.mkdir(temporary, { recursive: true });
  const documents = path.join(temporary, 'Documents with spaces');
  await fs.mkdir(documents, { recursive: true });
  try { await fs.writeFile(path.join(documents, 'evidence.txt'), 'Portable evidence survives restart. The calibration result was measured twice. A portable insulated chest filled with frozen gel packs preserves sandwiches during travel.', { flag: 'wx' }); }
  catch (error) { if (error.code !== 'EEXIST') throw error; }
  if (useEmbeddingGemma) {
    await fs.writeFile(path.join(documents, 'telescope.txt'), 'Telescopes collect starlight with aligned mirrors.');
  }
  let saved = false;
  try { saved = (await fs.readdir(path.join(temporary, 'application', 'profiles'))).length > 0; } catch { /* First installation. */ }
  const errors = [];
  const options = {
    env: { ...process.env, PYTHONIOENCODING: 'cp1252', OSII_DESKTOP_DATA_DIR: path.join(temporary, 'application') },
    timeout: 90_000,
  };
  if (process.env.OSII_DESKTOP_EXECUTABLE) options.executablePath = process.env.OSII_DESKTOP_EXECUTABLE;
  else options.args = [path.resolve(__dirname, '..')];
  let application;
  const metrics = { platform: process.platform, packaged: Boolean(process.env.OSII_DESKTOP_EXECUTABLE) };
  try {
    const started = Date.now();
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
    if (process.env.OSII_SMOKE_BLOCK_EXTERNAL === '1') {
      const online = await application.evaluate(async ({ net }) => {
        try {
          await net.fetch('https://github.com/robots.txt', { cache: 'no-store', signal: AbortSignal.timeout(5000) });
          return true;
        } catch { return false; }
      });
      assert.equal(online, false, 'The installed application must have no external HTTPS access during this test');
    }
    const api = async (route, method = 'GET', body) => page.evaluate(async ({ route, method, body }) => {
      const response = await fetch(route, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
      const value = await response.json();
      if (!response.ok) throw new Error(`${route}: ${response.status} ${JSON.stringify(value)}`);
      return value;
    }, { route, method, body });
    assert.equal((await api('/health')).status, 'ok');
    assert.equal((await api('/api/runtime')).user_authentication, false);
    const assetDirectory = process.env.OSII_DESKTOP_EXECUTABLE
      ? path.join(path.dirname(process.env.OSII_DESKTOP_EXECUTABLE), 'resources/runtime/_internal/dashboard/assets')
      : path.resolve(__dirname, '../resources/dashboard/assets');
    const assetFiles = await fs.readdir(assetDirectory);
    const mathWorker = assetFiles.find(name => name.startsWith('mathpix.worker-'));
    const mathBundle = assetFiles.find(name => name.startsWith('bundle-') && name.endsWith('.js'));
    assert.ok(mathWorker && mathBundle, 'Math rendering assets must be bundled');
    const mathematics = await page.evaluate(({ worker, bundle }) => new Promise((resolve, reject) => {
      const renderer = new Worker('/assets/' + worker);
      const timeout = setTimeout(() => { renderer.terminate(); reject(new Error('Offline mathematics timed out')); }, 15_000);
      renderer.onmessage = event => { clearTimeout(timeout); renderer.terminate(); resolve(event.data); };
      renderer.onerror = () => { clearTimeout(timeout); renderer.terminate(); reject(new Error('Offline mathematics worker failed')); };
      renderer.postMessage({ text: 'Calibration $E=mc^2$', bundleUrl: location.origin + '/assets/' + bundle });
    }), { worker: mathWorker, bundle: mathBundle });
    assert.ok(mathematics.html?.includes('Calibration'), JSON.stringify(mathematics));
    const setup = await api('/api/admin/setup');
    assert.equal(setup.extraction_ready, true);
    assert.equal(setup.ai_ready, false);
    if (useEmbeddingGemma) {
      assert.equal(setup.methods.embedder.model, 'embeddinggemma-2-text-256-v1', JSON.stringify(setup.methods));
      assert.equal(setup.methods.embedder.available, true);
      if (saved) assertSemanticMatch(await api('/api/search', 'POST', { query: semanticQuery, mode: 'semantic' }));
    }
    assert.ok(setup.services.some(service => service.id === 'ocr' && service.ownership === 'osii'));
    metrics.dashboardReadySeconds = (Date.now() - started) / 1000;
    if (process.platform === 'win32') metrics.idleMemory = windowsProcessMemory(application.process().pid);
    const noToken = await fetch(new URL('/health', page.url()));
    assert.equal(noToken.status, 403, 'The API must reject requests outside the Electron session');
    await page.goto(new URL('/intake', page.url()).href);
    const flow = useEmbeddingGemma ? 'Text, keywords and semantic search' : 'Text and keywords (offline)';
    await page.getByRole('combobox', { name: 'Processing flow' }).getByText(flow).waitFor();
    await page.getByRole('button', { name: 'Browse files', exact: true }).click();
    const browser = page.getByRole('dialog');
    await browser.getByLabel('Folder path').fill(documents);
    await browser.getByRole('button', { name: 'Go', exact: true }).click();
    await browser.getByText('evidence.txt', { exact: true }).click();
    if (useEmbeddingGemma) await browser.getByText('telescope.txt', { exact: true }).click();
    const files = useEmbeddingGemma ? '2 files' : '1 file';
    await browser.getByRole('button', { name: `Use ${files}`, exact: true }).click();
    const queued = page.waitForResponse(response => new URL(response.url()).pathname === '/api/runs'
      && response.request().method() === 'POST');
    await page.getByRole('button', { name: `Queue ${files}`, exact: true }).click();
    const run = await (await queued).json();
    const identifier = run.run_id || run.id;
    assert.ok(identifier, JSON.stringify(run));
    let finished;
    for (let attempts = 0; attempts < 100; attempts++) {
      finished = await api('/api/runs/' + identifier);
      if (['done', 'error', 'partial'].includes(finished.status)) break;
      await new Promise(resolve => setTimeout(resolve, 300));
    }
    assert.equal(finished.status, 'done', JSON.stringify(finished));
    const home = await api('/api/workbench/home');
    assert.equal(home.tools.chat.enabled, true, 'Offline chat must be reachable in the dashboard');
    assert.equal(home.tools.research.enabled, false, 'Model-backed reports still require a model');
    const search = await api('/api/search', 'POST', { query: 'calibration', mode: 'lexical' });
    assert.ok(search.results.length > 0, JSON.stringify(search));
    if (useEmbeddingGemma) {
      const matched = page.waitForResponse(response => new URL(response.url()).pathname === '/api/search'
        && response.request().method() === 'POST');
      const searchPage = new URL('/search', page.url());
      searchPage.searchParams.set('q', semanticQuery);
      searchPage.searchParams.set('mode', 'semantic');
      await page.goto(searchPage.href);
      assertSemanticMatch(await (await matched).json());
      await page.getByText('evidence.txt', { exact: true }).first().waitFor();
    }
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
    if (useEmbeddingGemma) {
      assertSemanticMatch(await api('/api/search', 'POST', { query: semanticQuery, mode: 'semantic' }));
    }
    assert.deepEqual(errors, []);
    await fs.writeFile(path.join(output, 'standalone-metrics.json'), JSON.stringify(metrics, null, 2) + '\n');
    console.log(JSON.stringify({ metrics }));
    console.log(JSON.stringify({ status: 'ok', checks: ['first-run', 'private-session', 'offline-mathematics', 'intake', 'preview', 'enrichment', 'keyword-search', 'offline-chat', 'spa-reload', 'ipc-boundary', 'restart',
      ...(useEmbeddingGemma ? ['bundled-cpu-semantic-search-after-restart'] : []),
      ...(process.env.OSII_SMOKE_BLOCK_EXTERNAL === '1' ? ['external-https-blocked'] : [])] }));
  } catch (error) {
    const page = application?.windows()[0];
    if (page && !page.isClosed()) {
      const output = path.resolve(__dirname, '../../output/playwright');
      await fs.mkdir(output, { recursive: true });
      await page.screenshot({ path: path.join(output, 'standalone-failure.png'), fullPage: true }).catch(() => {});
      const detail = await page.locator('#error').textContent({ timeout: 1000 }).catch(() => '');
      if (detail) error.message += '\nDesktop status: ' + detail;
    }
    throw error;
  } finally {
    if (application) await application.close();
    if (!process.env.OSII_SMOKE_DIRECTORY) await fs.rm(temporary, { recursive: true, force: true });
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
