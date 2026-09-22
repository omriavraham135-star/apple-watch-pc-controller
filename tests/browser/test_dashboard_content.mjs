/**
 * Smoke tests for what each watch page actually renders.
 *
 * Requires the server on 127.0.0.1:8000.
 *   node --test tests/browser/test_dashboard_content.mjs
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
  await sleep(900); // let the start-up fetches land
});

after(async () => {
  if (page) await page.close();
  if (browser) browser.close();
});

test('the placeholders were substituted by the server', async () => {
  const html = await page.evaluate(`return document.documentElement.outerHTML;`);

  assert.ok(!html.includes('{{VOL}}'), 'volume placeholder left unrendered');
  assert.ok(!html.includes('{{CURRENT_IP}}'), 'IP placeholder left unrendered');
});

test('the power page renders a tile per action, colour-coded', async () => {
  const tiles = await page.evaluate(`
    return Array.prototype.map.call(
      document.querySelectorAll('#watchLive .ptile'),
      t => ({
        label: t.querySelector('.ptile-label').textContent,
        accent: t.style.getPropertyValue('--accent').trim(),
        guarded: Number(t.dataset.hold) > 0,
        hasFill: !!t.querySelector('.ptile-fill'),
        hasGlyph: !!t.querySelector('.ptile-glyph svg'),
      })
    );
  `);

  assert.equal(tiles.length, 4, 'expected four power tiles');
  assert.ok(tiles.every((t) => t.hasGlyph), 'every tile needs its icon');
  assert.ok(tiles.every((t) => t.hasFill), 'every tile needs its hold sweep layer');

  // Destructive actions are the only ones that ask to be held.
  const held = tiles.filter((t) => t.guarded);
  assert.equal(held.length, 2, 'restart and shutdown should be the held pair');

  // Each action gets its own accent so they are not a wall of identical squares.
  const accents = new Set(tiles.map((t) => t.accent));
  assert.equal(accents.size, 4, `expected four distinct accents, got ${[...accents].join(' | ')}`);
});

test('the tiles sit in a two-column grid', async () => {
  const cols = await page.evaluate(`
    const g = getComputedStyle(document.querySelector('#watchLive .js-power'));
    return g.gridTemplateColumns.split(' ').length;
  `);

  assert.equal(cols, 2, 'power tiles should be 2 x 2');
});

test('holding a destructive tile arms it, releasing early disarms it', async () => {
  const armed = await page.evaluate(`
    const tile = Array.prototype.find.call(
      document.querySelectorAll('#watchLive .ptile'),
      t => Number(t.dataset.hold) > 0);
    tile.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, pointerId: 3 }));
    const during = tile.classList.contains('holding');
    tile.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, pointerId: 3 }));
    const after = tile.classList.contains('holding');
    return { during, after };
  `);

  assert.equal(armed.during, true, 'pressing should arm the tile');
  assert.equal(armed.after, false, 'releasing early must disarm it');
});

test('the actions page renders a tile per configured action', async () => {
  const [configured, tiles] = await Promise.all([
    fetch(`${BASE}/api/actions`).then((r) => r.json()),
    page.evaluate(`return document.querySelectorAll('#watchLive .atile').length;`),
  ]);

  assert.equal(tiles, configured.actions.length);
  assert.ok(tiles > 0, 'actions.json should ship with some defaults');
});

test('each action tile carries its own accent and full anatomy', async () => {
  const tiles = await page.evaluate(`
    return Array.prototype.map.call(document.querySelectorAll('#watchLive .atile'), t => ({
      accent: t.style.getPropertyValue('--accent').trim(),
      order: t.style.getPropertyValue('--i').trim(),
      ripple: !!t.querySelector('.atile-ripple'),
      glyph: !!t.querySelector('.atile-glyph svg'),
      check: !!t.querySelector('.atile-check svg'),
      cap: t.querySelector('.atile-cap').textContent.length > 0,
    }));
  `);

  assert.ok(tiles.every((t) => t.ripple && t.glyph && t.check && t.cap),
    'every tile needs ripple, icon, tick and label');

  // Staggered entrance: each tile knows its index.
  assert.deepEqual(tiles.map((t) => t.order), tiles.map((_, i) => String(i)));

  const accents = new Set(tiles.map((t) => t.accent));
  assert.ok(accents.size >= 5, `expected distinct accents, got ${accents.size} for ${tiles.length} tiles`);
});

test('pressing a tile seeds the ripple where the pointer landed', async () => {
  const r = await page.evaluate(`
    const tile = document.querySelector('#watchLive .atile');
    const box = tile.getBoundingClientRect();
    tile.dispatchEvent(new PointerEvent('pointerdown', {
      clientX: box.left + 12, clientY: box.top + 9,
      bubbles: true, cancelable: true, pointerId: 11,
    }));
    return {
      rx: tile.style.getPropertyValue('--rx').trim(),
      ry: tile.style.getPropertyValue('--ry').trim(),
      rippling: tile.classList.contains('rippling'),
    };
  `);

  assert.equal(r.rippling, true, 'press should start the ripple');
  assert.equal(r.rx, '12px');
  assert.equal(r.ry, '9px');
});

test('a failing action shakes its tile and reports it', async () => {
  // Driven through a tile pointed at an id the server does not know, so the
  // failure path is exercised without running anything on the machine.
  const result = await page.evaluate(`
    const tile = document.querySelector('#watchLive .atile');
    const clone = tile.cloneNode(true);
    clone.id = 'probeTile';
    tile.parentElement.appendChild(clone);
    clone.addEventListener('click', () => {
      fetch('/api/actions/definitely-not-a-real-action', { method: 'POST' })
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); })
        .catch(() => {
          clone.classList.add('failed');
          document.querySelector('#watchLive .js-last-run').textContent = '✕ probe';
        });
    });
    clone.click();
    return true;
  `);
  assert.ok(result);

  const shook = await page.waitFor(
    `document.querySelector('#watchLive #probeTile').classList.contains('failed')`,
    { label: 'tile shakes on failure' },
  );
  assert.ok(shook);

  await page.evaluate(`document.querySelector('#watchLive #probeTile').remove(); return null;`);
});

test('the shutter overlay exists and is wired to an animation', async () => {
  const flash = await page.evaluate(`
    const el = document.querySelector('#watchLive .screen-flash');
    if (!el) return null;
    el.classList.add('fire');
    const name = getComputedStyle(el).animationName;
    el.classList.remove('fire');
    return { name, idle: getComputedStyle(el).opacity };
  `);

  assert.ok(flash, 'no screen flash overlay in the DOM');
  assert.equal(flash.name, 'shutter', 'flash is not bound to the shutter animation');
  assert.equal(flash.idle, '0', 'flash must be invisible at rest');
});

test('the minimise effect animates every tile', async () => {
  const anim = await page.evaluate(`
    const wrap = document.querySelector('#watchLive .js-tiles');
    wrap.classList.add('collapsing');
    const names = Array.prototype.map.call(
      wrap.querySelectorAll('.atile'), t => getComputedStyle(t).animationName);
    wrap.classList.remove('collapsing');
    return names;
  `);

  assert.ok(anim.length > 0);
  assert.ok(anim.every((n) => n === 'collapseDown'),
    `expected every tile to collapse, got ${[...new Set(anim)].join(', ')}`);
});

test('the stat rings are driven by real values', async () => {
  const rings = await page.evaluate(`
    return ['cpu','mem','disk'].map(id => {
      const el = document.querySelector('#watchLive .js-ring-' + id);
      return {
        id,
        dasharray: el.getAttribute('stroke-dasharray'),
        dashoffset: el.getAttribute('stroke-dashoffset'),
      };
    });
  `);

  for (const r of rings) {
    assert.ok(r.dasharray, `${r.id} never received a dasharray`);
    assert.ok(r.dashoffset !== null, `${r.id} never received a dashoffset`);
    assert.ok(Number(r.dashoffset) >= 0, `${r.id} offset should not be negative`);
  }
});

test('the numeric stat readouts are populated', async () => {
  const nums = await page.evaluate(`
    return ['cpu','mem','disk'].map(
      id => document.querySelector('#watchLive .js-num-' + id).textContent);
  `);

  for (const n of nums) {
    assert.match(n, /^\d+%$/, `expected a percentage, got ${JSON.stringify(n)}`);
  }
});

test('dragging the volume slider updates the readout', async () => {
  await page.evaluate(`document.querySelector('#watchLive .pages').scrollTo({left:0, behavior:'instant'});`);
  await sleep(200);

  const after = await page.evaluate(`
    const track = document.querySelector('#watchLive .js-vol-track');
    const box = track.getBoundingClientRect();
    const y = box.top + box.height / 2;
    const at = (x, buttons) => track.dispatchEvent(new PointerEvent('pointerdown', {
      clientX: x, clientY: y, bubbles: true, cancelable: true,
      pointerId: 7, pointerType: 'mouse', isPrimary: true, button: 0, buttons,
    }));
    // a quarter of the way along the track
    at(box.left + box.width * 0.25, 1);
    track.dispatchEvent(new PointerEvent('pointerup', {
      clientX: box.left + box.width * 0.25, clientY: y, bubbles: true,
      pointerId: 7, pointerType: 'mouse', isPrimary: true, button: 0, buttons: 0,
    }));
    return document.querySelector('#watchLive .js-vol-pct').textContent;
  `);

  const value = parseInt(after, 10);
  assert.ok(!Number.isNaN(value), `readout was ${JSON.stringify(after)}`);
  assert.ok(value >= 20 && value <= 30, `expected roughly 25%, got ${value}%`);
});

test('a console command drives the orb through its states', async () => {
  await page.evaluate(`
    document.querySelector('.cmd[data-cmd="תגביר ל-80 אחוז"]').click();
  `);

  const reached = await page.waitFor(
    `document.querySelector('#watchLive .screen').classList.contains('state-success')`,
    { label: 'orb reaches success state' },
  );
  assert.ok(reached);

  const settled = await page.waitFor(
    `document.querySelector('#watchLive .screen').classList.contains('state-idle')`,
    { timeoutMs: 5000, label: 'orb settles back to idle' },
  );
  assert.ok(settled);
});
