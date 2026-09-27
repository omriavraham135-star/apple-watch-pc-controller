/**
 * Every API call from the dashboard carries the device's pairing token, and a
 * refusal sends the browser to the pairing page.
 *
 * Requires the server on 127.0.0.1:8000.
 */

import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';

import { Browser } from './cdp.mjs';

const BASE = 'http://127.0.0.1:8000';
let browser;
let page;

before(async () => {
  const res = await fetch(`${BASE}/api/status`).catch(() => null);
  if (!res || !res.ok) throw new Error(`server not reachable at ${BASE} — start it before running these tests`);
  browser = await Browser.launch();
  page = await browser.newPage(BASE);
  await page.waitFor("typeof window.pcFetch === 'function'");
});

after(async () => {
  if (page) await page.close();
  if (browser) browser.close();
});

test('the stored token rides along in the Authorization header', async () => {
  const seen = await page.evaluate(`
    localStorage.setItem('pcToken', 'tok-123');
    const real = window.fetch;
    let headers = null;
    window.fetch = (url, opts) => { headers = opts.headers; return Promise.resolve(new Response('{}', { status: 200 })); };
    return window.pcFetch('/api/stats').then(() => { window.fetch = real; return headers; });
  `);
  assert.equal(seen.Authorization, 'Bearer tok-123');
});

test('without a token no Authorization header is sent', async () => {
  const seen = await page.evaluate(`
    localStorage.removeItem('pcToken');
    const real = window.fetch;
    let headers = null;
    window.fetch = (url, opts) => { headers = opts.headers; return Promise.resolve(new Response('{}', { status: 200 })); };
    return window.pcFetch('/api/stats').then(() => { window.fetch = real; return headers; });
  `);
  assert.equal(seen.Authorization, undefined);
});

test('401 sends the browser to the pairing page', async () => {
  const went = await page.evaluate(`
    const real = window.fetch, realGo = window.pcGoPair;
    let redirected = false;
    window.pcGoPair = () => { redirected = true; };
    window.fetch = () => Promise.resolve(new Response('{}', { status: 401 }));
    return window.pcFetch('/api/stats').then(() => { window.fetch = real; window.pcGoPair = realGo; return redirected; });
  `);
  assert.equal(went, true);
});

test('the pairing page on the PC offers a code', async () => {
  const p = await browser.newPage(`${BASE}/pair`);
  await p.waitFor("document.querySelector('#mint') !== null");
  const mode = await p.evaluate(`return document.body.dataset.mode`);
  assert.equal(mode, 'pc');
  await p.close();
});
