import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { join } from 'node:path';

const [work, evidence] = process.argv.slice(2);
const { chromium } = createRequire(join(work, 'package.json'))('playwright-core');
const frontend = 'http://127.0.0.1:5173';
const api = 'http://127.0.0.1:8080';
const session = await readFile(join(work, 'fixture/session.json'), 'utf8');
const seed = JSON.parse(await readFile(join(work, 'seed.json'), 'utf8'));
const browser = await chromium.launch({
  executablePath: process.env.CHROME_BIN,
  args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'],
});

try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    locale: 'en-US',
    timezoneId: 'UTC',
    serviceWorkers: 'block',
  });
  const blocked = [];
  await context.route('**/*', (route) => {
    const url = new URL(route.request().url());
    if ([frontend, api].includes(url.origin)) return route.continue();
    blocked.push(url.origin);
    return route.abort();
  });
  await context.addInitScript(({ frontend, key, session }) => {
    if (location.origin === frontend) sessionStorage.setItem(key, session);
  }, {
    frontend,
    key: `spry.oidc.user.user:${process.env.COGNITO_ISSUER}:${process.env.COGNITO_CLIENT_ID}`,
    session,
  });

  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  const [read, document] = await Promise.all([
    page.waitForResponse((response) =>
      response.url() === `${api}/api/meetings` && response.request().method() === 'GET'),
    page.goto(frontend, { waitUntil: 'load' }),
  ]);
  assert.equal(document.status(), 200);
  assert.equal(read.status(), 200);
  const rows = await read.json();
  assert.deepEqual(rows.map(({ id, title, attendee_count }) => ({ id, title, attendee_count })), [seed]);
  await page.getByRole('heading', { name: seed.title, exact: true }).waitFor({ state: 'visible' });
  assert.deepEqual(pageErrors, []);
  assert.deepEqual(blocked, []);
  await page.screenshot({ path: join(evidence, 'spry-local.png'), fullPage: true });
  await writeFile(join(evidence, 'browser-api-read.json'), JSON.stringify({
    frontend: { url: document.url(), status: document.status(), visibleMeeting: seed.title },
    request: { method: read.request().method(), url: read.url(), status: read.status() },
    response: rows,
    auth: 'Ephemeral local JWT; browser session preloaded (no hosted sign-in)',
    browser: `Chromium ${browser.version()}`,
    blockedExternalRequests: blocked,
  }, null, 2) + '\n');
  console.log(`Browser loaded ${document.url()} (HTTP 200); GET /api/meetings returned and rendered PostgreSQL row ${seed.id}.`);
} finally {
  await browser.close();
}
