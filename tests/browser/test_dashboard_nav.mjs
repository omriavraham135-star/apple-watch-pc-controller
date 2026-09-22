/**
 * UI regression tests for the watch simulator's page navigation.
 *
 * Requires the server to be running on 127.0.0.1:8000.
 *   py -m uvicorn watch_pc_controller.server:app --port 8000
 *   node --test tests/browser/
 *
 * These exist because page navigation silently did nothing: the document is
 * RTL, where scrollLeft runs 0 → negative, while the navigation maths assumed
 * 0 → positive. Every scrollTo was clamped back to 0.
 */

import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';

import { Browser, sleep } from './cdp.mjs';

const BASE = 'http://127.0.0.1:8000';

let browser;
let page;

before(async () => {
  const res = await fetch(`${BASE}/api/status`).catch(() => null);
  if (!res || !res.ok) {
    throw new Error(`server not reachable at ${BASE} — start it before running these tests`);
  }
  browser = await Browser.launch();
  page = await browser.newPage(BASE);
  await page.waitFor("typeof window.__watch === 'object' && !!window.__watch.demo");
  // let the start-up fetches settle
  await sleep(600);
});

after(async () => {
  if (page) await page.close();
  if (browser) browser.close();
});

const activeDot = `Array.prototype.findIndex.call(
  document.querySelector('#watchLive .dots').children, d => d.classList.contains('on'))`;

const scrollState = `(() => {
  const p = document.querySelector('#watchLive .pages');
  return { left: p.scrollLeft, cw: p.clientWidth, sw: p.scrollWidth };
})()`;

test('the pages container is actually scrollable', async () => {
  const s = await page.evaluate(`return ${scrollState};`);

  assert.ok(s.cw > 0, 'container has no width');
  assert.equal(s.sw, s.cw * 4, 'expected exactly four pages side by side');
});

test('scrollLeft uses a positive coordinate range', async () => {
  // The root cause of the original bug: an RTL container reports 0 → -N,
  // so every positive scrollTo target is clamped to 0 and nothing moves.
  const max = await page.evaluate(`
    const p = document.querySelector('#watchLive .pages');
    const before = p.scrollLeft;
    p.scrollTo({ left: 99999, behavior: 'instant' });
    const after = p.scrollLeft;
    p.scrollTo({ left: 0, behavior: 'instant' });
    return { before, after };
  `);

  assert.equal(max.before, 0, 'should start at the first page');
  assert.ok(max.after > 0, `scrollLeft must grow positively, got ${max.after}`);
});

test('the next button advances one page at a time', async () => {
  await page.evaluate(`document.querySelector('#watchLive .pages').scrollTo({left:0, behavior:'instant'});`);
  await sleep(150);

  for (const expected of [1, 2, 3]) {
    await page.evaluate(`document.querySelector('#watchLive .js-next').click();`);
    const got = await page.waitFor(`${activeDot} === ${expected}`, {
      label: `dot ${expected} active`,
    });
    assert.ok(got, `did not reach page ${expected}`);
  }
});

test('the next button stops at the last page', async () => {
  await page.evaluate(`document.querySelector('#watchLive .js-next').click();`);
  await sleep(400);

  const i = await page.evaluate(`return ${activeDot};`);
  assert.equal(i, 3, 'should clamp at the final page');
});

test('the previous button walks back to the first page', async () => {
  for (const expected of [2, 1, 0]) {
    await page.evaluate(`document.querySelector('#watchLive .js-prev').click();`);
    const got = await page.waitFor(`${activeDot} === ${expected}`, {
      label: `dot ${expected} active`,
    });
    assert.ok(got, `did not return to page ${expected}`);
  }
});

test('the page name label tracks the active page', async () => {
  await page.evaluate(`document.querySelector('#watchLive .js-next').click();`);
  await page.waitFor(`${activeDot} === 1`);

  const name = await page.evaluate(`return document.querySelector('#watchLive .js-page-name').textContent;`);
  assert.equal(name, 'חשמל');
});

test('arrow keys move between pages', async () => {
  await page.evaluate(`document.querySelector('#watchLive .pages').scrollTo({left:0, behavior:'instant'});`);
  await sleep(200);

  // In an RTL layout the left arrow advances, matching the visual direction.
  await page.evaluate(`
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
  `);
  const ok = await page.waitFor(`${activeDot} === 1`, { label: 'ArrowLeft advances' });
  assert.ok(ok);

  await page.evaluate(`
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  `);
  assert.ok(await page.waitFor(`${activeDot} === 0`, { label: 'ArrowRight goes back' }));
});

test('dragging the screen swipes between pages', async () => {
  await page.evaluate(`document.querySelector('#watchLive .pages').scrollTo({left:0, behavior:'instant'});`);
  await sleep(200);

  // A mouse drag is the only "swipe" available on a desktop: the scrollbar is
  // hidden, so without drag support the simulator cannot be navigated by hand.
  await page.evaluate(`
    const el = document.querySelector('#watchLive .pages');
    const box = el.getBoundingClientRect();
    const y = box.top + box.height / 2;
    const send = (type, x, extra) => el.dispatchEvent(new PointerEvent(type, {
      clientX: x, clientY: y, bubbles: true, cancelable: true,
      pointerId: 1, pointerType: 'mouse', isPrimary: true, button: 0, buttons: extra ? 1 : 0,
    }));
    send('pointerdown', box.left + box.width - 30, true);
    for (let x = box.width - 30; x > 30; x -= 20) send('pointermove', box.left + x, true);
    send('pointerup', box.left + 30, false);
  `);

  const ok = await page.waitFor(`${activeDot} >= 1`, { label: 'drag moved a page' });
  assert.ok(ok, 'dragging did not change page');
});
