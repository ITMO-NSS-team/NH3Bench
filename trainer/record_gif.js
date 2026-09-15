// Запись кадров тренажёра для GIF: сценарий доводится до аварии,
// карта установки снимается покадрово (несколько кадров на состояние,
// чтобы сохранилась анимация потоков, маячков и газового облака).
const { chromium } = require('playwright');
const { pathToFileURL } = require('url');
const fs = require('fs');
const path = require('path');

// Путь считается от самого скрипта: абсолютный путь с чужой машины
// здесь не работал.
const HTML = path.join(__dirname, 'nh3bench-demo.html');
const SID_INDEX = Number(process.env.SID_INDEX ?? 1);   // 0=S1, 1=S2, ...
const OUTDIR = process.env.OUTDIR || 'frames_s2';
// План прогона: [секунды ожидания, кадров снять]. null => отправить наряд.
const PLAN = JSON.parse(process.env.PLAN || '[]');

async function waitIdle(page) {
  await page.waitForFunction(() => {
    const b = document.querySelector('#busy');
    return b && b.style.display !== 'block';
  }, null, { timeout: 300000 });
  await page.waitForTimeout(250);
}

(async () => {
  fs.rmSync(OUTDIR, { recursive: true, force: true });
  fs.mkdirSync(OUTDIR, { recursive: true });
  const meta = [];
  let n = 0;

  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({
    viewport: { width: 1400, height: 1000 },
    deviceScaleFactor: 1,
  });
  page.on('pageerror', e => console.log('[pageerror]', String(e).slice(0, 200)));

  const shoot = async (k = 3, gap = 110) => {
    // показания щита пишутся вместе с кадром: подписи к GIF должны
    // опираться на то, что реально было на приборах, а не на пересказ
    const gauges = await page.evaluate(() => {
      const out = {};
      document.querySelectorAll('#gauges .gr').forEach(r => {
        const s = r.querySelector('span'), b = r.querySelector('b');
        if (s && b) out[s.textContent.trim()] = b.textContent.trim();
      });
      return out;
    }).catch(() => ({}));
    const pick = (name) => gauges[name] || '';
    for (let i = 0; i < k; i++) {
      const clock = await page.locator('#clock').textContent();
      const file = path.join(OUTDIR, String(n).padStart(4, '0') + '.png');
      await page.locator('#pix').screenshot({ path: file });
      meta.push({
        file: path.basename(file), clock: clock.trim(), kind: 'map',
        lvl: pick('Уровень ЦР-НД'), nh3: pick('NH₃ машзал'),
      });
      n++;
      if (i < k - 1) await page.waitForTimeout(gap);
    }
  };

  await page.goto(pathToFileURL(HTML).href);
  await page.waitForSelector('#scr-menu', { state: 'visible', timeout: 300000 });
  await page.locator('#scenlist .scbtn').nth(SID_INDEX).click();
  await page.waitForSelector('#scr-brief', { state: 'visible' });
  const title = await page.locator('#btitle').textContent();
  console.log('сценарий:', title.trim());
  await page.locator('#acceptb').click();
  await page.waitForSelector('#scr-play', { state: 'visible', timeout: 300000 });
  await waitIdle(page);
  console.log('смена принята');

  await shoot(3);

  for (const step of PLAN) {
    if (step === null) {
      // наряд на ручной замер уровня — показать работу с персоналом
      const grp = page.locator('.agh', { hasText: 'Наряды: замеры' });
      await grp.click();
      await page.waitForTimeout(200);
      const btn = page.locator('.ag', { has: grp }).locator('.ab:enabled').first();
      if (await btn.count()) {
        console.log('наряд:', (await btn.textContent()).trim().slice(0, 50));
        await btn.click();
        await waitIdle(page);
        await shoot(3);
      }
      await grp.click();           // свернуть группу обратно
      continue;
    }
    const [sec, frames] = step;
    const sel = `.wb[data-w="${sec}"]`;
    if (!(await page.locator(sel).isVisible().catch(() => false))) break;
    await page.locator(sel).click();
    try {
      await waitIdle(page);
    } catch (e) {
      console.log('эпизод завершён во время ожидания');
      break;
    }
    if (!(await page.locator('#scr-play').isVisible())) {
      console.log('эпизод завершён (переход на итог)');
      break;
    }
    await shoot(frames);
    const alarms = (await page.locator('#alarms').innerText()).replace(/\n/g, ' | ');
    console.log(`t=${await page.locator('#clock').textContent()} +${sec}s  ${alarms.slice(0, 110)}`);
  }

  // журнал смены целиком: из него берутся фактические доклады обходчиков
  const log = await page.locator('#log').innerText().catch(() => '');
  fs.writeFileSync(path.join(OUTDIR, 'log.txt'), log, 'utf-8');
  console.log('--- доклады из журнала:');
  log.split('\n').filter(l => l.includes('ДОКЛАД')).forEach(l => console.log('   ', l));

  // финальный экран: вердикт
  if (await page.locator('#scr-final').isVisible().catch(() => false)) {
    const verdict = await page.locator('#fverdict').innerText();
    console.log('ИТОГ:', verdict.trim());
    for (let i = 0; i < 2; i++) {
      const file = path.join(OUTDIR, String(n).padStart(4, '0') + '.png');
      await page.locator('#scr-final').screenshot({ path: file, clip: undefined });
      meta.push({ file: path.basename(file), clock: verdict.trim(), kind: 'final' });
      n++;
    }
  }

  fs.writeFileSync(path.join(OUTDIR, 'meta.json'),
                   JSON.stringify(meta, null, 1), 'utf-8');
  console.log('кадров:', n);
  await browser.close();
})().catch(e => { console.error('FAIL', e); process.exit(1); });
