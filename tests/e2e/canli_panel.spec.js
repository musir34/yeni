const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');

function buildCards(count = 120) {
  return Array.from({ length: count }, (_, i) => {
    const size = 35 + (i % 7);
    const gross = (i % 4) + 1;
    const returned = i % 9 === 0 ? 1 : 0;
    return {
      model: `${String(i + 1).padStart(3, '0')}-MODEL`,
      renk: i === 0 ? '<img src=x onerror="window.__xss=1">' : `RENK-${i + 1}`,
      image: '/static/logo/gullu.png',
      toplam_siparis_bugun: gross,
      toplam_iade: returned,
      toplam_net_satis: Math.max(0, gross - returned),
      toplam_stok: 20 - (i % 10),
      ortalama_fiyat: 100 + i,
      dusuk_stok: false,
      iade_uyari: false,
      tedarikci_kodu: i % 2 ? 'TED-002' : 'TED-001',
      tedarikci_kodlari: [i % 2 ? 'TED-002' : 'TED-001'],
      detay: [{ beden: String(size), siparis: gross, iade: returned, net: Math.max(0, gross - returned), stok: 5 }],
    };
  });
}

function renderPanelHtml() {
  let html = fs.readFileSync(path.join(ROOT, 'templates', 'canli_panel.html'), 'utf8');
  const shell = fs.readFileSync(path.join(ROOT, 'static', 'js', 'app-shell.js'), 'utf8');
  html = html
    .replace('{% if is_admin %}', '')
    .replace('{% endif %}', '')
    .replace("{{ 'true' if is_admin else 'false' }}", 'true')
    .replace('<script src="{{ url_for(\'static\', filename=\'js/app-shell.js\') }}"></script>', `<script>${shell}</script>`)
    .replace("{% include 'includes/notification_popup.html' ignore missing %}", '')
    .replace('<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"></script>', `
      <script>
        class FakeChart {
          static register() {}
          constructor(ctx, config) { this.data = config.data; this.options = config.options; }
          update() {}
        }
        window.Chart = FakeChart;
      </script>`);

  const bootstrap = `
    <script>
      window.__requests = [];
      window.__sseUrls = [];
      window.__sseClosed = 0;
      window.__submissions = [];
      window.__cards = ${JSON.stringify(buildCards())};
      window.__summaryFor = function(rawUrl) {
        const u = new URL(rawUrl, location.origin);
        const model = (u.searchParams.get('model') || '').toLowerCase();
        const source = u.searchParams.get('source') || 'all';
        let cards = window.__cards.filter(k => !model || k.model.toLowerCase().includes(model));
        if (source === 'shopify') cards = cards.slice(0, 3).map(k => ({...k, model: 'SHOP-' + k.model}));
        if (source === 'trendyol') cards = cards.slice(3);
        return {
          guncellendi: '05/08/2026 12:00',
          toplam_net_satis: cards.reduce((a, k) => a + k.toplam_net_satis, 0),
          toplam_siparis_sayisi: cards.length,
          genel_ortalama_fiyat: 150,
          toplam_ciro: cards.reduce((a, k) => a + k.toplam_net_satis * k.ortalama_fiyat, 0),
          kartlar: cards,
        };
      };
      window.fetch = async function(rawUrl, options = {}) {
        const url = String(rawUrl);
        window.__requests.push({url, method: options.method || 'GET'});
        if (url.startsWith('/api/tedarikcilar')) {
          return {ok:true, status:200, json:async()=>[
            {kod:'TED-001', adi:'Bir'}, {kod:'TED-002', adi:'İki'}
          ]};
        }
        if (url.startsWith('/api/canli/ozet')) {
          return {ok:true, status:200, json:async()=>window.__summaryFor(url)};
        }
        if (url.startsWith('/siparis_fisi/tedarik_olustur')) {
          const payload = JSON.parse(options.body);
          window.__submissions.push(payload);
          return {ok:true, status:200, json:async()=>({success:true, message:'Tamam', redirect_url:'/siparis_fisi/1'})};
        }
        throw new Error('Unexpected fetch: ' + url);
      };
      class FakeEventSource {
        constructor(url) {
          this.url = url;
          this.closed = false;
          window.__sseUrls.push(url);
          setTimeout(() => {
            if (!this.closed && this.onmessage) this.onmessage({data: JSON.stringify(window.__summaryFor(url))});
          }, 5);
        }
        close() {
          if (!this.closed) window.__sseClosed += 1;
          this.closed = true;
        }
      }
      window.EventSource = FakeEventSource;
    </script>`;
  return html.replace('<head>', '<head><base href="https://panel.test/">' + bootstrap);
}

async function openPanel(page, viewport = { width: 1280, height: 900 }) {
  await page.setViewportSize(viewport);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.route('https://panel.test/canli-panel', route => route.fulfill({
    contentType: 'text/html',
    body: renderPanelHtml(),
  }));
  await page.route('https://panel.test/static/**', route => route.fulfill({status: 204}));
  await page.goto('https://panel.test/canli-panel', { waitUntil: 'load' });
  await expect(page.locator('#zaman')).toContainText('Güncellendi');
  return errors;
}

test('loads, paginates, escapes data and applies every filter type', async ({ page }) => {
  const errors = await openPanel(page);
  await expect(page.locator('.card')).toHaveCount(50);
  await expect(page.locator('#paginationInfo')).toContainText('1–50 / 120');
  expect(await page.evaluate(() => window.__xss || 0)).toBe(0);

  await page.locator('[data-source="shopify"]').click();
  await page.locator('#uygulaBtn').click();
  await expect(page.locator('.card')).toHaveCount(3);
  expect(await page.evaluate(() => window.__sseUrls.at(-1))).toContain('source=shopify');

  await page.locator('[data-source="all"]').click();
  await page.locator('#filtreModel').fill('099');
  await page.locator('#uygulaBtn').click();
  await expect(page.locator('.card')).toHaveCount(1);
  expect(await page.evaluate(() => window.__requests.filter(r => r.url.includes('/api/canli/ozet')).at(-1).url)).toContain('model=099');

  await page.locator('[data-preset="custom"]').click();
  await page.locator('#start').fill('2026-08-05');
  await page.locator('#end').fill('2026-08-04');
  const before = await page.evaluate(() => window.__requests.length);
  await page.locator('#uygulaBtn').click();
  expect(await page.evaluate(() => window.__requests.length)).toBe(before);
  expect(errors).toEqual([]);
});

test('keeps selections across pages and submits each card with its own quantity', async ({ page }) => {
  const errors = await openPanel(page);
  await page.locator('.card').nth(1).locator('.tedarik-cb-wrap').click();
  await page.locator('#paginationControls').getByRole('button', { name: '2', exact: true }).click();
  await page.locator('.card').first().locator('.tedarik-cb-wrap').click();
  await expect(page.locator('#tedarikCount')).toHaveText('2');

  await page.locator('#tedarikBtn').click();
  await page.locator('#modalApproveAll').click();
  await expect.poll(() => page.evaluate(() => window.__submissions.length)).toBe(1);
  const payload = await page.evaluate(() => window.__submissions[0]);
  expect(payload.kartlar).toHaveLength(2);
  expect(payload.kartlar[0].model).not.toBe(payload.kartlar[1].model);
  expect(payload.kartlar[0].detay[0].net).toBe(2);
  expect(payload.kartlar[1].detay[0].net).toBe(3);

  await page.locator('#modalSkip').click();
  await page.locator('.card').first().locator('.tedarik-cb-wrap').click();
  await page.locator('#tedarikBtn').click();
  await page.locator('#modalNext').click();
  await expect.poll(() => page.evaluate(() => window.__submissions.length)).toBe(2);
  expect(errors).toEqual([]);
});

test('last-card skip stays skipped and modal can be reused', async ({ page }) => {
  const errors = await openPanel(page);
  await page.locator('.card').nth(1).locator('.tedarik-cb-wrap').click();
  await page.locator('#tedarikBtn').click();
  await page.locator('#modalSkip').click();
  await expect(page.locator('#modalBody')).toContainText('Hiçbir üründe adet girilmedi');
  expect(await page.evaluate(() => window.__submissions.length)).toBe(0);
  await page.locator('#modalSkip').click();

  await page.locator('#tedarikBtn').click();
  await expect(page.locator('#modalNext')).toBeVisible();
  await page.locator('#modalNext').click();
  await expect.poll(() => page.evaluate(() => window.__submissions.length)).toBe(1);
  expect(errors).toEqual([]);
});

test('mobile layout has no horizontal page overflow', async ({ page }) => {
  const errors = await openPanel(page, { width: 375, height: 812 });
  const metrics = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    chartColumns: getComputedStyle(document.querySelector('.twocol')).gridTemplateColumns.split(' ').length,
    cardWidth: document.querySelector('.card').getBoundingClientRect().width,
  }));
  expect(metrics.documentWidth).toBeLessThanOrEqual(metrics.viewport);
  expect(metrics.chartColumns).toBe(1);
  expect(metrics.cardWidth).toBeLessThanOrEqual(metrics.viewport - 24);
  expect(errors).toEqual([]);
});

test('preset, custom, supplier, page-size, refresh and live controls work together', async ({ page }) => {
  const errors = await openPanel(page);

  for (const preset of ['today', 'yesterday', 'this_week', 'last_7d', 'this_month', 'last_30d']) {
    await page.locator(`[data-preset="${preset}"]`).click();
    await page.locator('#uygulaBtn').click();
    await expect.poll(() => page.evaluate(() => window.__requests.filter(r => r.url.includes('/api/canli/ozet')).at(-1).url))
      .toContain(`preset=${preset}`);
  }

  await page.locator('[data-preset="custom"]').click();
  await page.locator('#start').fill('2026-07-01');
  await page.locator('#end').fill('2026-07-31');
  await page.locator('[data-source="trendyol"]').click();
  await page.locator('#uygulaBtn').click();
  const customUrl = await page.evaluate(() => window.__requests.filter(r => r.url.includes('/api/canli/ozet')).at(-1).url);
  expect(customUrl).toContain('start=2026-07-01');
  expect(customUrl).toContain('end=2026-07-31');
  expect(customUrl).toContain('source=trendyol');

  await page.locator('[data-source="all"]').click();
  await page.locator('#uygulaBtn').click();
  await expect.poll(() => page.evaluate(() => window.__requests.filter(r => r.url.includes('/api/canli/ozet')).at(-1).url))
    .not.toContain('source=trendyol');
  await page.locator('#filtreTedarikci').selectOption('TED-001');
  await expect(page.locator('.card')).toHaveCount(50);
  await expect(page.locator('#paginationInfo')).toContainText('1–50 / 60');
  await expect(page.locator('#kpiOrders')).toHaveText('—');
  expect(await page.locator('.card .head-left .chip:first-child').evaluateAll(chips =>
    chips.every(chip => Number(chip.textContent.split('-')[0]) % 2 === 1)
  )).toBe(true);

  await page.locator('#pageSize').selectOption('100');
  await expect(page.locator('.card')).toHaveCount(60);
  await expect(page.locator('#paginationInfo')).toContainText('1–60 / 60');

  const beforeRefresh = await page.evaluate(() => ({
    requests: window.__requests.filter(r => r.url.includes('/api/canli/ozet')).length,
    streams: window.__sseUrls.length,
    closed: window.__sseClosed,
  }));
  await page.locator('#yenileBtn').click();
  await expect.poll(() => page.evaluate(() => window.__requests.filter(r => r.url.includes('/api/canli/ozet')).length))
    .toBe(beforeRefresh.requests + 1);
  await expect.poll(() => page.evaluate(() => window.__sseUrls.length)).toBe(beforeRefresh.streams + 1);
  expect(await page.evaluate(() => window.__sseClosed)).toBeGreaterThan(beforeRefresh.closed);

  const beforeOff = await page.evaluate(() => ({streams: window.__sseUrls.length, closed: window.__sseClosed}));
  await page.locator('#liveToggle').uncheck();
  expect(await page.evaluate(() => window.__sseClosed)).toBeGreaterThan(beforeOff.closed);
  await page.locator('#liveToggle').check();
  await expect.poll(() => page.evaluate(() => window.__sseUrls.length)).toBe(beforeOff.streams + 1);
  expect(errors).toEqual([]);
});
