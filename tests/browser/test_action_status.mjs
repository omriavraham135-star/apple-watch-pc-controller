/**
 * Action tiles that know whether their app is already open.
 *
 * The state is pushed in directly for most of these, so the assertions do not
 * depend on which programs happen to be running on the machine. One test does
 * go against the real endpoint, to prove the wiring end to end.
 *
 * Requires the server on 127.0.0.1:8000.
 */

import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';

import { Browser, sleep } from './cdp.mjs';

const BASE = 'http://127.0.0.1:8000';

let browser;
let page;

const atile = (id) => `document.querySelector('#watchLive .atile[data-action="${id}"]')`;

before(async () => {
  const res = await fetch(`${BASE}/api/status`).catch(() => null);
  if (!res || !res.ok) {
    throw new Error(`server not reachable at ${BASE} — start it before running these tests`);
  }
  browser = await Browser.launch();
  page = await browser.newPage(BASE);
  await page.waitFor("typeof window.__watch === 'object' && !!window.__watch.demo");
  await page.waitFor(`${atile('chrome')} !== null`);
  await sleep(500);
});

after(async () => {
  if (page) await page.close();
  if (browser) browser.close();
});

test('the server reports a running state for every action', async () => {
  const body = await fetch(`${BASE}/api/actions/status`).then((r) => r.json());
  const list = await fetch(`${BASE}/api/actions`).then((r) => r.json());

  assert.ok(body.statuses, 'no statuses in the response');
  for (const action of list.actions) {
    const st = body.statuses[action.id];
    assert.ok(st, `no status for ${action.id}`);
    assert.equal(typeof st.running, 'boolean');
  }
});

test('only actions that watch a process can ever be live', async () => {
  const shape = await page.evaluate(`
    return Array.prototype.map.call(document.querySelectorAll('#watchLive .atile'), t => ({
      id: t.dataset.action,
      hasPip: !!t.querySelector('.atile-live'),
    }));
  `);

  const list = await fetch(`${BASE}/api/actions`).then((r) => r.json());
  const watched = new Set(list.actions.filter((a) => a.process).map((a) => a.id));

  for (const t of shape) {
    assert.equal(t.hasPip, watched.has(t.id),
      `${t.id}: pip presence should follow whether it watches a process`);
  }
});

test('a running app lights its tile', async () => {
  await page.evaluate(`
    window.__watch.live.setActionStatuses({ chrome: { running: true, pid: 42 } });
    return null;
  `);

  const lit = await page.evaluate(`return ${atile('chrome')}.classList.contains('live');`);
  assert.equal(lit, true);
});

test('the lit state is visibly different, not just a class', async () => {
  await page.evaluate(`
    window.__watch.live.setActionStatuses({ chrome: { running: false, pid: null } });
    return null;
  `);
  await sleep(450);
  const off = await page.evaluate(`
    const g = ${atile('chrome')}.querySelector('.atile-glyph');
    return { bg: getComputedStyle(g).backgroundImage, pip: getComputedStyle(
      ${atile('chrome')}.querySelector('.atile-live')).opacity };
  `);

  await page.evaluate(`
    window.__watch.live.setActionStatuses({ chrome: { running: true, pid: 42 } });
    return null;
  `);
  await sleep(450);
  const on = await page.evaluate(`
    const g = ${atile('chrome')}.querySelector('.atile-glyph');
    return { bg: getComputedStyle(g).backgroundImage, pip: getComputedStyle(
      ${atile('chrome')}.querySelector('.atile-live')).opacity };
  `);

  assert.notEqual(on.bg, off.bg, 'the icon should fill when the app is open');
  assert.ok(Number(on.pip) > Number(off.pip), 'the pip should appear when the app is open');
});

test('closing an app puts its tile back to rest', async () => {
  await page.evaluate(`
    window.__watch.live.setActionStatuses({ chrome: { running: true, pid: 42 } });
    return null;
  `);
  await page.evaluate(`
    window.__watch.live.setActionStatuses({ chrome: { running: false, pid: null } });
    return null;
  `);

  const lit = await page.evaluate(`return ${atile('chrome')}.classList.contains('live');`);
  assert.equal(lit, false);
});

test('both watches reflect the same running state', async () => {
  await sleep(4200); // let one poll cycle reach both

  const [live, demo] = await page.evaluate(`
    const read = (host) => Array.prototype.map.call(
      document.querySelectorAll(host + ' .atile'),
      t => t.dataset.action + ':' + t.classList.contains('live'));
    return [read('#watchLive'), read('#watchDemo')];
  `);

  assert.deepEqual(live, demo, 'the demo watch should mirror what the live one shows');
});

test('tapping an open app raises it instead of launching a copy', async () => {
  // Driven on the demo watch, which mirrors the decision without touching the PC.
  await page.evaluate(`
    window.__watch.demo.setActionStatuses({ chrome: { running: true, pid: 42 } });
    document.querySelector('#watchDemo .atile[data-action="chrome"]').click();
    return null;
  `);

  const raised = await page.waitFor(
    `document.querySelector('#watchDemo .atile[data-action="chrome"]').classList.contains('raised')`,
    { label: 'tile plays the raise animation' },
  );
  assert.ok(raised);

  const note = await page.evaluate(
    `return document.querySelector('#watchDemo .js-last-run').textContent;`);
  assert.match(note, /חזית/, `expected a "brought to front" note, got "${note}"`);
});

test('tapping a closed app still reports it as launched', async () => {
  await page.evaluate(`
    window.__watch.demo.setActionStatuses({ chrome: { running: false, pid: null } });
    document.querySelector('#watchDemo .atile[data-action="chrome"]').click();
    return null;
  `);

  const done = await page.waitFor(
    `document.querySelector('#watchDemo .atile[data-action="chrome"]').classList.contains('done')`,
    { label: 'tile plays the launch confirmation' },
  );
  assert.ok(done);
});
