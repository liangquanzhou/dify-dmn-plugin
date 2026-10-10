/* Verify the packaged HTML without relying on a Vite asset server. */
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const root = path.resolve(__dirname, '../..');
const html = fs.readFileSync(path.join(root, 'dist/dmn-decision-matrix-0.7.0-candidate-offline.html'));
const server = http.createServer((_req, res) => {
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.end(html);
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE || chromium.executablePath(),
    headless: true,
    chromiumSandbox: true,
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1480, height: 1000 } });
    const errors = [];
    const requests = [];
    const checks = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => requests.push(request.url()));
    const check = (name, value) => { assert(value, name); checks.push(name); };
    const url = `http://127.0.0.1:${server.address().port}/offline.html`;
    await page.goto(url);
    check('self-contained HTML renders the FIRST matrix', await page.getByRole('columnheader', { name: '"会员"', exact: true }).isVisible());
    check('no separate asset or external requests', requests.length === 1 && requests[0] === url);
    await page.getByRole('button', { name: '02 COLLECT · 嵌套条件' }).click();
    check('COLLECT logic works in packaged HTML', await page.getByText('(A 或 (B 且 C))', { exact: true }).isVisible());
    await page.getByRole('button', { name: '展开大表 ↗', exact: true }).click();
    check('packaged dialog opens', await page.locator('dialog').evaluate(dialog => dialog.open));
    await page.keyboard.press('Escape');
    await page.locator('dialog table').waitFor({ state: 'detached' });
    check('packaged dialog closes and unmounts', await page.locator('table').count() === 1);
    await page.getByRole('button', { name: '04 UNIQUE · 唯一配送' }).click();
    check('UNIQUE renders all original rules in packaged HTML', await page.locator('tbody tr').count() === 3);
    check('UNIQUE conflict and unknown guidance visible offline', await page.getByLabel('UNIQUE 策略说明').isVisible() && (await page.getByLabel('UNIQUE 策略说明').textContent()).includes('waiting_input'));
    await page.getByRole('button', { name: '展开大表 ↗', exact: true }).click();
    check('UNIQUE guidance remains available in expanded offline view', await page.locator('dialog').getByLabel('UNIQUE 策略说明').isVisible());
    await page.keyboard.press('Escape');
    await page.locator('dialog table').waitFor({ state: 'detached' });
    await page.getByRole('button', { name: '05 其他 Tool 节点' }).click();
    check('unrelated tool has no UNIQUE matrix', await page.locator('table').count() === 0);
    check('UNIQUE preview makes no execution or asset requests', requests.length === 1);
    check('no JavaScript errors', errors.length === 0);
    fs.writeFileSync(path.join(root, 'evidence/offline-check.json'), JSON.stringify({ checks, errors, assetRequests: requests.length - 1, executionNotIncluded: true }, null, 2));
    console.log(JSON.stringify({ passed: checks.length, checks }));
  }
  finally {
    await browser.close();
    server.close();
  }
})().catch(error => { console.error(error); server.close(); process.exit(1); });
