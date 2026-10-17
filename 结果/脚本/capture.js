// 用法: node capture.js <卡片目录> <输出帧目录> <fps> <名单json>
const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');
const [, , cardDir, outDir, fpsArg, listJson] = process.argv;
const fps = Number(fpsArg);
const list = JSON.parse(fs.readFileSync(listJson, 'utf8'));

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/Applications/Chromium.app/Contents/MacOS/Chromium',
    headless: 'new',
    args: ['--hide-scrollbars', '--disable-gpu'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });
  const durs = {};
  for (const [i, name] of list.entries()) {
    const dir = path.join(outDir, String(i).padStart(2, '0'));
    fs.mkdirSync(dir, { recursive: true });
    const url = 'file://' + path.join(cardDir, name + '.html').split(path.sep).map(encodeURIComponent).join('/') + '?anim';
    await page.goto(url, { waitUntil: 'load' });
    await page.evaluate(() => document.fonts.ready);
    const dur = await page.evaluate(() => window.__dur);
    const n = Math.ceil(((dur + 250) / 1000) * fps);
    for (let f = 0; f < n; f++) {
      await page.evaluate(ms => window.__seek(ms), (f * 1000) / fps);
      await page.screenshot({ path: path.join(dir, `f${String(f).padStart(4, '0')}.jpg`), type: 'jpeg', quality: 92 });
    }
    durs[name] = n / fps;
    console.log(i, name, (n / fps).toFixed(2) + 's', n, 'frames');
  }
  fs.writeFileSync(path.join(outDir, 'durs.json'), JSON.stringify(durs));
  await browser.close();
})();
