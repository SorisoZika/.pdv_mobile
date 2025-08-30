const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();

  await page.goto('http://172.23.128.102:9898/normal.html');
  await new Promise(resolve => setTimeout(resolve, 1000));

  await page.keyboard.type('112');
  await page.keyboard.press('Tab');

  await browser.close();
})();
