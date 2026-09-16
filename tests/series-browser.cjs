// Real Firefox composer; Paperless/file APIs are fixtures. No live upload.
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { firefox } = require(path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, 'playwright'));
(async () => {
  const browser = await firefox.launch({ headless: true, timeout: 20000,
    ...(process.env.PAPERLESS_TEST_DISABLE_BROWSER_SANDBOX === '1'
      ? { firefoxUserPrefs: { 'security.sandbox.content.level': 0 } } : {}) });
  try {
    const context = await browser.newContext({ viewport: { width: 720, height: 950 } });
    const remembered = { enabled: false, inherit: true, assignment: null }, accepted = [], errors = [];
    await context.exposeBinding('seriesState', () => structuredClone(remembered));
    await context.exposeBinding('seriesOptions', (_, options) => Object.assign(remembered, options));
    await context.exposeBinding('seriesStart', (_, metadata) => {
      accepted.push(structuredClone(metadata));
      const { tags, correspondent, document_type, storage_path, custom_fields, created, complete_tagging } = metadata;
      remembered.assignment = structuredClone({ tags, correspondent, document_type, storage_path, custom_fields, created, complete_tagging });
      return 'job-' + accepted.length;
    });
    await context.addInitScript(({ version }) => {
      let sequence = 0;
      const base = 'https://archive.test/';
      const file = name => ({ id: 'file-' + ++sequence, name, size: 1234, kind: 'picker', canDelete: false });
      const P = {
        state: async () => ({ config: { base, profiles: [], theme: 'light' }, unlocked: true, helperAllowed: false,
          previewRevision: 1, series: await window.seriesState() }),
        saveSeriesOptions: options => window.seriesOptions(options),
        jobs: () => [], titleHistory: async () => [], rememberTitle: async () => {}, assignmentSuggestions: async () => [],
        intent: async () => ({ url: base + 'Akte.pdf' }), sourceURL: async () => file('Akte.pdf'), chooseFile: async item => file(item.name), removeSource: async () => {},
        precheckSource: async () => ({ state: 'clear', matches: [] }),
        metadata: async () => ({ tags: [{ id: 1, name: 'Akte' }, { id: 2, name: 'Zusatzkontext' }],
          correspondents: [{ id: 3, name: 'Amtsgericht' }], document_types: [{ id: 4, name: 'Beschluss' }], storage_paths: [{ id: 5, name: 'Akten' }],
          custom_fields: [{ id: 10, name: 'Aktenzeichen', data_type: 'string' }, { id: 11, name: 'Betrag', data_type: 'monetary' }, { id: 12, name: 'Erledigt', data_type: 'boolean' }], warnings: [] }),
        beginBatch: async () => 'batch', sealBatch: async () => {}, start: async (_, metadata) => window.seriesStart(metadata)
      };
      window.browser = { runtime: { getManifest: () => ({ version }), getBackgroundPage: async () => ({ Paperless: P }) },
        storage: { session: { get: async () => ({}), set: async () => {} } } };
    }, { version: require('../extension/manifest.json').version });
    const url = pathToFileURL(path.resolve(__dirname, '../extension/app.html')).href + '?compact=1&intent=fixture';
    async function openComposer() {
      const page = await context.newPage(); page.setDefaultTimeout(10000); page.on('pageerror', e => errors.push(e.message));
      await page.goto(url); await page.locator('#send').waitFor();
      await page.waitForFunction(() => !document.getElementById('send').disabled);
      return page;
    }
    async function choose(page, id, text) { await page.locator('#' + id).fill(text); await page.locator('#' + id).press('Enter'); }
    const page = await openComposer();
    await page.locator('#series-mode').check();
    assert.equal(await page.locator('#series-inherit').isChecked(), true);
    await page.locator('#file-input').setInputFiles({ name: 'Verfügung.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n%%EOF') });
    await choose(page, 'tag-search', 'Akte'); await choose(page, 'correspondent-search', 'Amtsgericht'); await choose(page, 'document_type-search', 'Beschluss');
    await page.locator('#storage_path').selectOption('5'); await page.locator('#created').fill('220826'); await page.locator('#created').press('Tab');
    for (const name of ['Aktenzeichen', 'Betrag', 'Erledigt']) { const input = page.locator('#custom-fields input[type="search"]'); await input.fill(name); await input.press('Enter'); }
    await page.locator('#custom-field-10').fill('99 C 35/26'); await page.locator('#custom-field-11').fill('EUR1489'); await page.locator('#custom-field-11').press('Tab');
    await page.locator('#custom-field-12').selectOption('false'); await page.locator('#complete-tagging').check(); await page.locator('#title').fill('Erster Beschluss');
    await page.locator('#send').click(); await page.waitForFunction(() => document.getElementById('title').value === '' && !document.getElementById('send').disabled);
    assert.equal(accepted.length, 1); assert.equal(accepted[0].custom_fields[11], 'EUR14.89');
    assert.equal(await page.locator('#custom-field-10').inputValue(), '99 C 35/26'); assert.equal(await page.locator('#custom-field-12').inputValue(), 'false');
    assert.equal(await page.locator('#created').inputValue(), '22.08.2026'); assert.equal(await page.locator('#correspondent').inputValue(), '3');
    await choose(page, 'tag-search', 'Zusatzkontext'); await page.locator('#custom-field-10').fill('99 C 36/26'); await page.locator('#title').fill('Weitere Verfügung');
    await page.locator('#send').click(); await page.waitForFunction(() => document.getElementById('files').children.length === 0);
    assert.equal(accepted.length, 2); assert.deepEqual(accepted[1].tags, [1, 2]); await page.close();
    const next = await openComposer();
    await next.waitForFunction(() => document.getElementById('custom-field-10').value === '99 C 36/26');
    assert.equal(await next.locator('#series-mode').isChecked(), true); assert.equal(await next.locator('#selected-tags .tag-chip').count(), 2);
    assert.equal(await next.locator('#title').inputValue(), ''); assert.equal(await next.locator('#custom-field-11').inputValue(), 'EUR14.89');
    assert.equal(await next.locator('#custom-field-12').inputValue(), 'false'); assert.equal(await next.locator('#created-picker').inputValue(), '2026-08-22');
    assert.equal(await next.locator('#complete-tagging').isChecked(), true); assert.equal(await next.locator('#share-enabled').isChecked(), false);
    await next.evaluate(() => window.scrollTo(0, 0));
    if (process.env.PAPERLESS_TEST_SCREENSHOT) await next.screenshot({ path: process.env.PAPERLESS_TEST_SCREENSHOT, fullPage: true });
    await next.locator('#series-inherit').uncheck(); await next.close();
    const fresh = await openComposer();
    assert.equal(await fresh.locator('#series-inherit').isChecked(), false); assert.equal(await fresh.locator('#correspondent').inputValue(), '');
    assert.equal(await fresh.locator('#custom-field-10').inputValue(), '');
    assert.deepEqual(errors, []);
    console.log('Firefox PASS: series queue, date/calendar, typed custom values, editable inheritance, latest assignment across windows, opt-out, no console errors.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
