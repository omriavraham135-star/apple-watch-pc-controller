/**
 * The accidental-touch guard on destructive power actions.
 *
 * This is a touchscreen strapped to a wrist. A stray brush against "shutdown"
 * must not cost someone their unsaved work, so the guard is the safety-critical
 * part of the interface and gets tested as such.
 *
 * Every test here drives the DEMO watch, which runs the entire interaction —
 * ring, countdown, haptics, commit — while never sending anything to the PC.
 * Nothing in this file can turn the machine off.
 *
 * Requires the server on 127.0.0.1:8000.
 */

import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';

import { Browser, sleep } from './cdp.mjs';

const BASE = 'http://127.0.0.1:8000';

let browser;
let page;

/** Record every fetch the page makes, so "sent nothing" is provable. */
const INSTALL_FETCH_SPY = `
  if (!window.__calls) {
    window.__calls = [];
    const real = window.fetch;
    window.fetch = function (url, opts) {
      window.__calls.push({ url: String(url), method: (opts && opts.method) || 'GET' });
      return real.apply(this, arguments);
    };
  }
  window.__calls.length = 0;
  return true;
`;

const tile = (watch, action) =>
  `document.querySelector('#${watch} .ptile[data-action="${action}"]')`;

const press = (sel) => `
  const t = ${sel};
  t.dispatchEvent(new PointerEvent('pointerdown', {
    bubbles: true, cancelable: true, pointerId: 5, pointerType: 'touch', isPrimary: true,
  }));
  return true;
`;

const release = (sel) => `
  const t = ${sel};
  t.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, pointerId: 5 }));
  return true;
`;

before(async () => {
  const res = await fetch(`${BASE}/api/status`).catch(() => null);
  if (!res || !res.ok) {
    throw new Error(`server not reachable at ${BASE} — start it before running these tests`);
  }
  browser = await Browser.launch();
  page = await browser.newPage(BASE);
  await page.waitFor("typeof window.__watch === 'object' && !!window.__watch.demo");
  await page.waitFor(`${tile('watchDemo', 'shutdown')} !== null`);
  await sleep(400);
});

after(async () => {
  if (page) await page.close();
  if (browser) browser.close();
});

test('harmless actions are a single tap, destructive ones are guarded', async () => {
  const tiles = await page.evaluate(`
    return Array.prototype.map.call(
      document.querySelectorAll('#watchDemo .ptile'),
      t => ({
        action: t.dataset.action,
        hold: Number(t.dataset.hold),
        guarded: t.classList.contains('guarded'),
        hasRing: !!t.querySelector('.hold-ring'),
        hasCount: !!t.querySelector('.ptile-count'),
      })
    );
  `);

  const by = Object.fromEntries(tiles.map((t) => [t.action, t]));

  assert.equal(by.lock.hold, 0, 'a lock should not need holding');
  assert.equal(by.sleep.hold, 0, 'a sleep should not need holding');
  assert.ok(by.restart.hold >= 2, 'restart must be held');
  assert.ok(by.shutdown.hold > by.restart.hold, 'shutdown must be the hardest to trigger');

  assert.ok(by.shutdown.guarded && by.shutdown.hasRing && by.shutdown.hasCount);
  assert.ok(!by.lock.hasRing, 'an unguarded tile needs no ring');
});

test('a plain click on a guarded tile does nothing at all', async () => {
  await page.evaluate(INSTALL_FETCH_SPY);
  await page.evaluate(`${tile('watchDemo', 'shutdown')}.click(); return true;`);
  await sleep(400);

  const state = await page.evaluate(`
    const t = ${tile('watchDemo', 'shutdown')};
    return {
      committed: t.classList.contains('committed'),
      holding: t.classList.contains('holding'),
      calls: window.__calls.filter(c => c.url.includes('/api/power')).length,
    };
  `);

  assert.equal(state.committed, false, 'a click must never commit a guarded action');
  assert.equal(state.holding, false);
  assert.equal(state.calls, 0, 'a click must not reach the server');
});

test('pressing arms the guard and starts closing the ring', async () => {
  await page.evaluate(press(tile('watchDemo', 'shutdown')));
  await sleep(450);

  const mid = await page.evaluate(`
    const t = ${tile('watchDemo', 'shutdown')};
    const ring = t.querySelector('.hold-ring-val');
    return {
      holding: t.classList.contains('holding'),
      offset: parseFloat(ring.style.strokeDashoffset),
      total: parseFloat(ring.style.strokeDasharray),
      countdown: t.querySelector('.ptile-count').textContent,
      fill: t.querySelector('.ptile-fill').style.transform,
    };
  `);

  assert.equal(mid.holding, true, 'press should arm the tile');
  assert.ok(mid.offset < mid.total, 'the ring should have started closing');
  assert.ok(mid.offset > 0, 'the ring should not be complete yet');
  assert.match(mid.countdown, /^[123]$/, `countdown should be ticking, got "${mid.countdown}"`);
  assert.match(mid.fill, /scaleY/, 'the accent should be rising');

  await page.evaluate(release(tile('watchDemo', 'shutdown')));
});

test('releasing early cancels everything and commits nothing', async () => {
  await page.evaluate(INSTALL_FETCH_SPY);

  await page.evaluate(press(tile('watchDemo', 'shutdown')));
  await sleep(600);
  await page.evaluate(release(tile('watchDemo', 'shutdown')));
  await sleep(450);

  const after = await page.evaluate(`
    const t = ${tile('watchDemo', 'shutdown')};
    const ring = t.querySelector('.hold-ring-val');
    return {
      holding: t.classList.contains('holding'),
      committed: t.classList.contains('committed'),
      offset: parseFloat(ring.style.strokeDashoffset),
      total: parseFloat(ring.style.strokeDasharray),
      countdown: t.querySelector('.ptile-count').textContent,
      calls: window.__calls.filter(c => c.url.includes('/api/power')).length,
    };
  `);

  assert.equal(after.holding, false, 'release must disarm');
  assert.equal(after.committed, false, 'an interrupted hold must not commit');
  assert.equal(after.offset, after.total, 'the ring should have unwound fully');
  assert.equal(after.countdown, '', 'the countdown should be cleared');
  assert.equal(after.calls, 0, 'nothing should have been sent');
});

test('the guard cannot be beaten by a hold that is too short', async () => {
  await page.evaluate(INSTALL_FETCH_SPY);

  // 3s guard, released at 2.4s — close, but not enough.
  await page.evaluate(press(tile('watchDemo', 'shutdown')));
  await sleep(2400);
  await page.evaluate(release(tile('watchDemo', 'shutdown')));
  await sleep(300);

  const committed = await page.evaluate(`
    return {
      committed: ${tile('watchDemo', 'shutdown')}.classList.contains('committed'),
      calls: window.__calls.filter(c => c.url.includes('/api/power')).length,
    };
  `);

  assert.equal(committed.committed, false, '2.4s must not satisfy a 3s guard');
  assert.equal(committed.calls, 0);
});

test('holding for the full duration commits', async () => {
  await page.evaluate(press(tile('watchDemo', 'restart')));

  // restart is a 2s guard; give it a little margin.
  const fired = await page.waitFor(
    `${tile('watchDemo', 'restart')}.classList.contains('committed')`,
    { timeoutMs: 4000, label: 'restart commits after a full hold' },
  );
  assert.ok(fired, 'a completed hold should commit');

  await page.evaluate(release(tile('watchDemo', 'restart')));
});

test('the demo watch never sends a power command, even when committed', async () => {
  // The whole point of the second watch: rehearse the most destructive gesture
  // in the interface with no possibility of it reaching the machine.
  await page.evaluate(INSTALL_FETCH_SPY);

  await page.evaluate(press(tile('watchDemo', 'shutdown')));
  await page.waitFor(
    `${tile('watchDemo', 'shutdown')}.classList.contains('committed')`,
    { timeoutMs: 5000, label: 'demo shutdown commits' },
  );
  await page.evaluate(release(tile('watchDemo', 'shutdown')));
  await sleep(400);

  const calls = await page.evaluate(`return window.__calls.filter(c => c.method === 'POST');`);

  assert.deepEqual(calls, [], `demo watch must send nothing, but sent ${JSON.stringify(calls)}`);
});

test('the live watch is wired to the real endpoint', async () => {
  // Asserted through configuration rather than by firing it: this watch is
  // connected to the actual machine.
  const wired = await page.evaluate(`
    return {
      live: window.__watch.live.live,
      demo: window.__watch.demo.live,
      sameMarkup:
        document.querySelectorAll('#watchLive .ptile').length ===
        document.querySelectorAll('#watchDemo .ptile').length,
    };
  `);

  assert.equal(wired.live, true, 'the left watch should be live');
  assert.equal(wired.demo, false, 'the right watch must not be live');
  assert.ok(wired.sameMarkup, 'both watches should render the same interface');
});


// ------------------------------------------------------------ ring geometry

test('guarded tiles are square', async () => {
  const dims = await page.evaluate(`
    return Array.prototype.map.call(
      document.querySelectorAll('#watchDemo .ptile'),
      t => ({ action: t.dataset.action, w: Math.round(t.offsetWidth), h: Math.round(t.offsetHeight) })
    );
  `);

  for (const d of dims) {
    assert.equal(d.w, d.h, `${d.action} is ${d.w}x${d.h}, not square`);
  }
});

test('the ring traces the tile outline with even margins on all sides', async () => {
  // A fixed circle inside a rounded rectangle gets letterboxed: it leaves gaps
  // at the sides and clips at the bottom. The ring is a measured path instead.
  for (const action of ['restart', 'shutdown']) {
    const gap = await page.evaluate(`
      const t = ${tile('watchDemo', action)};
      const r = t.querySelector('.hold-ring-val').getBoundingClientRect();
      const b = t.getBoundingClientRect();
      return {
        left: +(r.left - b.left).toFixed(2),
        right: +(b.right - r.right).toFixed(2),
        top: +(r.top - b.top).toFixed(2),
        bottom: +(b.bottom - r.bottom).toFixed(2),
      };
    `);

    const sides = Object.values(gap);
    const spread = Math.max(...sides) - Math.min(...sides);
    assert.ok(spread < 0.6, `${action} ring margins uneven: ${JSON.stringify(gap)}`);
    assert.ok(Math.min(...sides) >= 0, `${action} ring escapes the tile: ${JSON.stringify(gap)}`);
  }
});

test('the dash length matches the real path length', async () => {
  // If these disagree the ring finishes early or leaves a sliver at the top.
  for (const action of ['restart', 'shutdown']) {
    const m = await page.evaluate(`
      const v = ${tile('watchDemo', action)}.querySelector('.hold-ring-val');
      return { declared: parseFloat(v.style.strokeDasharray), actual: v.getTotalLength() };
    `);

    assert.ok(m.declared > 0, `${action} has no dasharray`);
    assert.ok(
      Math.abs(m.declared - m.actual) < 0.5,
      `${action}: dasharray ${m.declared} vs path ${m.actual.toFixed(2)}`,
    );
  }
});

test('the ring opens at rest, closes fully during the hold, then rewinds', async () => {
  const read = () => page.evaluate(`
    const v = ${tile('watchDemo', 'restart')}.querySelector('.hold-ring-val');
    return { offset: parseFloat(v.style.strokeDashoffset), total: parseFloat(v.style.strokeDasharray) };
  `);

  const rest = await read();
  assert.ok(Math.abs(rest.offset - rest.total) < 0.5,
    `the ring should sit fully open, was ${rest.offset} of ${rest.total}`);

  // Sample every frame: the ring is wound back the instant it commits, so the
  // closure has to be caught while the hold is still running.
  await page.evaluate(`
    window.__minOffset = Infinity;
    const v = ${tile('watchDemo', 'restart')}.querySelector('.hold-ring-val');
    const tick = () => {
      const o = parseFloat(v.style.strokeDashoffset);
      if (!isNaN(o)) window.__minOffset = Math.min(window.__minOffset, o);
      window.__sampling = requestAnimationFrame(tick);
    };
    tick();
    return true;
  `);

  await page.evaluate(press(tile('watchDemo', 'restart')));
  await page.waitFor(
    `${tile('watchDemo', 'restart')}.classList.contains('committed')`,
    { timeoutMs: 4000, label: 'restart commits' },
  );
  await page.evaluate(release(tile('watchDemo', 'restart')));

  const min = await page.evaluate(`
    cancelAnimationFrame(window.__sampling);
    return window.__minOffset;
  `);
  assert.ok(min < 2, `the ring should close completely, closest it got was ${min}`);

  // The rewind is deliberately deferred until the 700ms confirmation flash ends.
  await sleep(950);
  const after = await read();
  assert.ok(Math.abs(after.offset - after.total) < 0.5,
    'the ring should rewind after the flash, so the next press does not start closed');
});
