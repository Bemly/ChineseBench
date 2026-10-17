// 用法: node shot.js <列表json: [[html, png], ...]>
const puppeteer = require('puppeteer');
const fs = require('fs');
(async () => {
  const list = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const browser = await puppeteer.launch({
    executablePath: '/Applications/Chromium.app/Contents/MacOS/Chromium', headless: 'new',
    args: ['--hide-scrollbars', '--disable-gpu'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1920 });
  for (const [html, png, width] of list) {
    await page.setViewport({ width: width || 1080, height: width ? 600 : 1920 });
    await page.goto('file://' + html.split('/').map(encodeURIComponent).join('/'), { waitUntil: 'load' });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: png, omitBackground: false, fullPage: !!width });
  }
  await browser.close();
})();
