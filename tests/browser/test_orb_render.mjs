/**
 * Tests that the orb actually paints, and that its states are visually distinct.
 *
 * The orb is the centrepiece and it renders to a canvas, so "it loaded without
 * errors" proves nothing. These read pixels back.
 *
 * Requires the server on 127.0.0.1:8000.
 */

import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';

import { Browser, sleep } from './cdp.mjs';

const BASE = 'http://127.0.0.1:8000';

let browser;
let page;

/** Mean RGB of the canvas, ignoring fully transparent pixels. */
const SAMPLE = `
  const c = document.querySelector('#watchLive .orb-canvas');
  const g = c.getContext('2d');
  const d = g.getImageData(0, 0, c.width, c.height).data;
  let r = 0, gr = 0, b = 0, n = 0, opaque = 0;
  for (let i = 0; i < d.length; i += 4) {
    if (d[i + 3] === 0) continue;
    opaque++;
    r += d[i]; gr += d[i + 1]; b += d[i + 2]; n++;
  }
  return n === 0
    ? { empty: true, opaque: 0, total: d.length / 4 }
    : { empty: false, r: r / n, g: gr / n, b: b / n, opaque, total: d.length / 4 };
`;

before(async () => {
  const res = await fetch(`${BASE}/api/status`).catch(() => null);
  if (!res || !res.ok) {
    throw new Error(`server not reachable at ${BASE} — start it before running these tests`);
  }
  browser = await Browser.launch();
  page = await browser.newPage(BASE);
  await page.waitFor("typeof window.Orb === 'function'");
  await page.waitFor("typeof window.__watch === 'object' && !!window.__watch.demo");
  await sleep(900);
});

after(async () => {
  if (page) await page.close();
  if (browser) browser.close();
});

test('the orb renderer is served and loaded', async () => {
  const res = await fetch(`${BASE}/orb.js`);

  assert.equal(res.status, 200);
  assert.match(res.headers.get('content-type'), /javascript/);

  const isClass = await page.evaluate(`return typeof window.Orb === 'function';`);
  assert.ok(isClass, 'Orb class did not reach the page');
});

test('the canvas is backed by real pixels at device resolution', async () => {
  // Compared against the layout size, not the bounding rect: an ancestor
  // breathing scale makes the rect fluctuate, which is why sizing off it was
  // a bug in the first place.
  const dims = await page.evaluate(`
    const c = document.querySelector('#watchLive .orb-canvas');
    return { w: c.width, h: c.height, layoutW: c.offsetWidth, dpr: window.devicePixelRatio };
  `);

  assert.ok(dims.w >= 100, `canvas buffer too small: ${dims.w}`);
  assert.equal(dims.w, dims.h, 'orb canvas should be square');
  assert.ok(
    dims.w >= dims.layoutW * dims.dpr,
    `buffer ${dims.w} should cover layout ${dims.layoutW} at dpr ${dims.dpr}`,
  );
});

test('the orb paints something', async () => {
  const s = await page.evaluate(SAMPLE);

  assert.equal(s.empty, false, 'canvas is entirely transparent — nothing rendered');
  // Clipped to a circle, so roughly pi/4 of the square should be painted.
  assert.ok(s.opaque / s.total > 0.5, `only ${(s.opaque / s.total * 100).toFixed(1)}% painted`);
  assert.ok(s.r + s.g + s.b > 30, 'rendered but essentially black');
});

test('the orb animates between frames', async () => {
  const first = await page.evaluate(SAMPLE);
  await sleep(500);
  const second = await page.evaluate(SAMPLE);

  const delta =
    Math.abs(first.r - second.r) + Math.abs(first.g - second.g) + Math.abs(first.b - second.b);
  assert.ok(delta > 0.05, `frames look identical (delta ${delta.toFixed(4)}) — is it animating?`);
});

test('each state renders a visibly distinct orb', async () => {
  const samples = {};

  for (const state of ['idle', 'listening', 'thinking', 'success', 'error']) {
    await page.evaluate(`window.__orb.setState('${state}'); return null;`);
    await sleep(850); // the palette cross-fade is 700ms
    samples[state] = await page.evaluate(SAMPLE);
  }

  for (const [state, s] of Object.entries(samples)) {
    assert.equal(s.empty, false, `${state} produced an empty canvas`);
  }

  // Each palette should read as its own hue.
  assert.ok(samples.idle.b > samples.idle.r, 'idle should read blue');
  assert.ok(samples.listening.b > samples.listening.r, 'listening should read cyan-blue');
  assert.ok(samples.success.g > samples.success.r, 'success should read green');
  assert.ok(samples.error.r > samples.error.g, 'error should read red');
  assert.ok(samples.thinking.r > samples.success.r, 'thinking should be warmer than success');

  // And no two states should be near-identical.
  const names = Object.keys(samples);
  for (let i = 0; i < names.length; i++) {
    for (let j = i + 1; j < names.length; j++) {
      const a = samples[names[i]];
      const b = samples[names[j]];
      const dist = Math.abs(a.r - b.r) + Math.abs(a.g - b.g) + Math.abs(a.b - b.b);
      assert.ok(dist > 6, `${names[i]} and ${names[j]} look the same (distance ${dist.toFixed(1)})`);
    }
  }
});

test('a real command drives the orb to a green success palette', async () => {
  await page.evaluate(`
    document.querySelector('#watchLive .pages').scrollTo({ left: 0, behavior: 'instant' });
    document.querySelector('.cmd[data-cmd="תגביר ל-80 אחוז"]').click();
    return null;
  `);

  await page.waitFor(
    `document.querySelector('#watchLive .screen').classList.contains('state-success')`,
    { label: 'success state' },
  );
  // let the palette cross-fade land
  await sleep(750);
  const success = await page.evaluate(SAMPLE);

  assert.ok(
    success.g > success.r && success.g > success.b,
    `success orb should read green, got rgb(${success.r.toFixed(0)}, ${success.g.toFixed(0)}, ${success.b.toFixed(0)})`,
  );
});

test('no errors were logged while rendering', async () => {
  const errors = await page.evaluate(`return window.__orbErrors || [];`);
  assert.deepEqual(errors, []);
});
