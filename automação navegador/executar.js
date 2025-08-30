const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();

  await page.goto('http://172.23.128.102:9898/normal.html');
  await new Promise(resolve => setTimeout(resolve, 300));

  await page.keyboard.type('112');
  await page.keyboard.press('Tab');

  await page.reload();
  await new Promise(resolve => setTimeout(resolve, 1000));
  await page.evaluate(() => document.body.focus());

  await page.keyboard.type('377316'); // fiscal
  await page.keyboard.type('1829');   // senha

  await new Promise(resolve => setTimeout(resolve, 300));
  await browser.close();
})();
